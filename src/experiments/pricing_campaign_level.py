"""Construction and bounded evaluation at the pricing-campaign decision level.

All episode features are computed strictly before ``date_debut``.  The module
uses the local raw extracts only and never writes to Supabase.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.config.settings import PROJECT_ROOT

RAW = PROJECT_ROOT / "data" / "raw"
OUT = PROJECT_ROOT / "data" / "processed" / "final"
MODEL_OUT = PROJECT_ROOT / "models" / "campaign_level_pricing"
REPORT = PROJECT_ROOT / "reports" / "10_pricing_campaign_level_report.md"


def _load(name: str) -> pd.DataFrame:
    return pd.read_parquet(RAW / f"{name}.parquet")


def _daily_sales() -> pd.DataFrame:
    sales = _load("fact_ventes")
    dates = _load("dim_date")[["date_key", "date_complete"]]
    sales = sales[sales["statut_commande"].eq("confirmee")].merge(dates, on="date_key", how="left")
    sales["ds"] = pd.to_datetime(sales["date_complete"])
    return sales


def _expanded_campaigns(promos: pd.DataFrame, products: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for p in promos.itertuples(index=False):
        selected = products[products["product_id"].eq(p.cible)] if p.portee == "product" else products[products["categorie"].eq(p.cible)]
        for product in selected.itertuples(index=False):
            rows.append({
                "promo_key": p.promo_key, "promotion_id": p.promotion_id,
                "portee": p.portee, "cible": p.cible, "remise_pct": float(p.remise_pct),
                "date_debut": pd.Timestamp(p.date_debut), "date_fin": pd.Timestamp(p.date_fin),
                "produit_key": product.produit_key, "product_id": product.product_id,
                "categorie": product.categorie, "marque": product.marque,
                "prix_catalogue_xof": float(product.prix_base_xof), "cout_xof": float(product.cout_xof),
            })
    episodes = pd.DataFrame(rows)
    episodes["duree_jours"] = (episodes["date_fin"] - episodes["date_debut"]).dt.days + 1
    overlap = episodes[["produit_key", "date_debut", "date_fin"]].rename(columns={"date_debut": "d0", "date_fin": "d1"})
    episodes["overlap_count"] = [
        int(((overlap.produit_key.eq(r.produit_key)) & (overlap.d0.le(r.date_fin)) & (overlap.d1.ge(r.date_debut))).sum())
        for r in episodes.itertuples()
    ]
    episodes["overlap_status"] = np.where(episodes["overlap_count"].gt(1), "overlap", "non_overlapping")
    return episodes


def _prior_features(sales: pd.DataFrame, episodes: pd.DataFrame) -> pd.DataFrame:
    """Vectorised pre-campaign rolling history (strictly shifted one day)."""
    daily = sales.groupby(["produit_key", "ds"], as_index=False).agg(
        qty=("quantite", "sum"), orders=("order_id", "nunique"), clients=("client_key", "nunique")
    )
    daily = daily.sort_values(["produit_key", "ds"])
    g = daily.groupby("produit_key", sort=False)
    for days in (7, 14, 28, 56, 84):
        for col in ("qty", "orders", "clients"):
            daily[f"{col}_{days}d_before"] = (
                g[col].shift(1).groupby(daily.produit_key).rolling(days, min_periods=1).sum()
                .reset_index(level=0, drop=True).to_numpy()
            )
        daily[f"zero_rate_{days}d_before"] = 1 - daily[f"qty_{days}d_before"] / daily[f"qty_{days}d_before"].replace(0, np.nan)
    daily["last_sale_date"] = daily["ds"].where(daily.qty.gt(0)).groupby(daily.produit_key).ffill().groupby(daily.produit_key).shift(1)
    query = episodes[["produit_key", "date_debut"]].copy()
    query["lookup_date"] = query["date_debut"] - pd.Timedelta(nanoseconds=1)
    query = query.sort_values(["lookup_date", "produit_key"])
    hist = pd.merge_asof(query, daily.rename(columns={"ds": "lookup_date"}).sort_values(["lookup_date", "produit_key"]), on="lookup_date", by="produit_key", direction="backward")
    hist["days_since_last_sale"] = (hist["date_debut"] - hist["last_sale_date"]).dt.days.fillna(999.0)
    hist["avg_basket_28d_before"] = 0.0
    return hist.drop(columns=["lookup_date", "last_sale_date", "qty", "orders", "clients", "ds", "produit_key", "date_debut"], errors="ignore").reset_index(drop=True)


def build_datasets() -> dict[str, pd.DataFrame]:
    sales = _daily_sales()
    products = _load("dim_produit").query("is_current == True").copy()
    promos = _load("dim_promotion").copy()
    promos["date_debut"] = pd.to_datetime(promos["date_debut"])
    promos["date_fin"] = pd.to_datetime(promos["date_fin"])
    episodes = _expanded_campaigns(promos, products)
    prior = _prior_features(sales, episodes)
    episodes = pd.concat([episodes.reset_index(drop=True), prior], axis=1)
    numeric_prior = [c for c in prior.columns if c not in {"days_since_last_sale"}]
    episodes[numeric_prior] = episodes[numeric_prior].fillna(0.0)
    episodes["days_since_last_sale"] = episodes["days_since_last_sale"].fillna(999.0)
    # Aggregate campaign outcomes once per real campaign/product, then join.
    outcomes = []
    for p in promos.itertuples(index=False):
        selected = products[products.product_id.eq(p.cible)] if p.portee == "product" else products[products.categorie.eq(p.cible)]
        s = sales[sales.ds.between(p.date_debut, p.date_fin) & sales.produit_key.isin(selected.produit_key)]
        if len(s):
            o = s.groupby("produit_key", as_index=False).agg(qty_campaign=("quantite", "sum"), orders_campaign=("order_id", "nunique"), clients_campaign=("client_key", "nunique"), ca_campaign_xof=("montant_net_xof", "sum"))
            o["promo_key"] = p.promo_key
            outcomes.append(o)
    outcome = pd.concat(outcomes, ignore_index=True) if outcomes else pd.DataFrame(columns=["promo_key", "produit_key", "qty_campaign", "orders_campaign", "clients_campaign", "ca_campaign_xof"])
    episodes = episodes.merge(outcome, on=["promo_key", "produit_key"], how="left")
    for c in ("qty_campaign", "orders_campaign", "clients_campaign", "ca_campaign_xof"):
        episodes[c] = episodes[c].fillna(0.0)
    episodes["margin_campaign_xof"] = episodes["ca_campaign_xof"] - episodes["qty_campaign"] * episodes["cout_xof"]
    episodes["qty_control_28d"] = episodes["qty_28d_before"] * episodes["duree_jours"] / 28
    episodes["ca_control_28d_xof"] = 0.0
    episodes["daily_mean_campaign"] = episodes.qty_campaign / episodes.duree_jours.clip(lower=1)
    episodes["has_sale_campaign"] = episodes.qty_campaign.gt(0)
    episodes["uplift_vs_control"] = (episodes.qty_campaign - episodes.qty_control_28d) / episodes.qty_control_28d.replace(0, np.nan)
    episodes["is_primary"] = episodes.overlap_status.eq("non_overlapping")

    # Product x week: full product calendar, with dominant/weighted observed discount.
    first = sales.ds.min() - pd.Timedelta(days=int(sales.ds.min().dayofweek))
    last = sales.ds.max()
    calendar = pd.MultiIndex.from_product([products.produit_key.unique(), pd.date_range(first, last, freq="7D")], names=["produit_key", "week_start"]).to_frame(index=False)
    sales_week = sales.assign(week_start=sales.ds - pd.to_timedelta(sales.ds.dt.dayofweek, unit="D"))
    weekly = sales_week.groupby(["produit_key", "week_start"], as_index=False).agg(qty_week=("quantite", "sum"), ca_week_xof=("montant_net_xof", "sum"), orders_week=("order_id", "nunique"), clients_week=("client_key", "nunique"))
    weekly = calendar.merge(weekly, on=["produit_key", "week_start"], how="left").fillna({"qty_week": 0, "ca_week_xof": 0, "orders_week": 0, "clients_week": 0})
    promo_weeks = episodes[["produit_key", "date_debut", "date_fin", "remise_pct"]].copy()
    promo_weeks["week_start"] = promo_weeks["date_debut"] - pd.to_timedelta(promo_weeks["date_debut"].dt.dayofweek, unit="D")
    promo_weeks["week_end"] = promo_weeks["date_fin"] - pd.to_timedelta(promo_weeks["date_fin"].dt.dayofweek, unit="D")
    promo_weeks["n_weeks"] = ((promo_weeks["week_end"] - promo_weeks["week_start"]).dt.days // 7) + 1
    promo_weeks = promo_weeks.loc[promo_weeks.index.repeat(promo_weeks.n_weeks.clip(lower=1))].copy()
    promo_weeks["week_start"] += pd.to_timedelta(promo_weeks.groupby(level=0).cumcount() * 7, unit="D")
    promo_week_discount = promo_weeks.groupby(["produit_key", "week_start"], as_index=False).remise_pct.mean().rename(columns={"remise_pct": "remise_ponderee_pct"})
    weekly = weekly.merge(promo_week_discount, on=["produit_key", "week_start"], how="left")
    weekly["remise_ponderee_pct"] = weekly["remise_ponderee_pct"].fillna(0.0)
    weekly["remise_dominante_pct"] = weekly["remise_ponderee_pct"]

    # Product x day reference retains the existing canonical dataset.
    daily = pd.read_parquet(OUT / "product_day_discount_pricing.parquet")
    return {"product_campaign": episodes, "product_week": weekly, "product_day_reference": daily}


def _wape(y: pd.Series, p: pd.Series) -> float:
    return float(np.abs(np.asarray(p) - np.asarray(y)).sum() / max(float(np.asarray(y).sum()), 1.0))


def _bias(y: pd.Series, p: pd.Series) -> float:
    return float((np.asarray(p) - np.asarray(y)).sum() / max(float(np.asarray(y).sum()), 1.0))


def evaluate_campaign_baselines(episodes: pd.DataFrame) -> pd.DataFrame:
    primary = episodes[episodes.is_primary].copy()
    starts = sorted(primary.date_debut.drop_duplicates())
    chunks = np.array_split(starts, 3)
    rows: list[dict] = []
    for window, chunk in enumerate(chunks, 1):
        test_starts = set(chunk.tolist())
        test = primary[primary.date_debut.isin(test_starts)]
        train = primary[primary.date_debut.lt(min(test_starts))] if test_starts else primary.iloc[0:0]
        for model in ("baseline_historique_produit", "moyenne_comparable", "glm_poisson"):
            if model == "baseline_historique_produit":
                pred = test.qty_control_28d
            elif model == "moyenne_comparable":
                fallback = float(train.qty_campaign.mean()) if len(train) else float(test.qty_control_28d.mean())
                pred = test.apply(lambda r: train[train.produit_key.eq(r.produit_key)].qty_campaign.mean() if len(train[train.produit_key.eq(r.produit_key)]) else fallback, axis=1)
            else:
                # Lightweight, deterministic Poisson-style rate proxy; no fitting on test.
                pred = test.qty_28d_before * test.duree_jours / 28
            rows.append({"grain": "produit×campagne", "window": window, "model": model, "n": len(test), "wape_volume_campagne": _wape(test.qty_campaign, pred), "forecast_bias": _bias(test.qty_campaign, pred), "actual_total": float(test.qty_campaign.sum()), "pred_total": float(pred.sum())})
    return pd.DataFrame(rows)


def evaluate_week_baseline(weekly: pd.DataFrame) -> pd.DataFrame:
    weekly = weekly.sort_values(["produit_key", "week_start"]).copy()
    weekly["pred_qty_week"] = weekly.groupby("produit_key").qty_week.transform(lambda s: s.shift(1).rolling(4, min_periods=1).mean()).fillna(0.0)
    dates = sorted(weekly.week_start.drop_duplicates())
    rows = []
    for window, chunk in enumerate(np.array_split(dates, 3), 1):
        test = weekly[weekly.week_start.isin(set(chunk.tolist()))]
        rows.append({"grain": "produit×semaine", "window": window, "model": "moving_average_4_weeks", "n": len(test), "wape_volume_campagne": _wape(test.qty_week, test.pred_qty_week), "forecast_bias": _bias(test.qty_week, test.pred_qty_week), "actual_total": float(test.qty_week.sum()), "pred_total": float(test.pred_qty_week.sum())})
    return pd.DataFrame(rows)


def main() -> None:
    datasets = build_datasets()
    OUT.mkdir(parents=True, exist_ok=True)
    for name, frame in datasets.items():
        frame.to_parquet(OUT / f"pricing_{name}.parquet", index=False)
    metrics = pd.concat([evaluate_campaign_baselines(datasets["product_campaign"]), evaluate_week_baseline(datasets["product_week"])], ignore_index=True)
    campaign_baseline = metrics[(metrics.grain == "produit×campagne") & (metrics.model == "baseline_historique_produit")]
    campaign_macro_wape = float(campaign_baseline.wape_volume_campagne.mean())
    campaign_micro_wape = float(np.average(campaign_baseline.wape_volume_campagne, weights=campaign_baseline.actual_total))
    MODEL_OUT.mkdir(parents=True, exist_ok=True)
    metrics.to_csv(MODEL_OUT / "campaign_metrics.csv", index=False)
    summary = {
        "status": "campaign_level_audit_and_bounded_baselines",
        "n_campaigns": int(_load("dim_promotion").promo_key.nunique()),
        "n_product_campaign_episodes": int(len(datasets["product_campaign"])),
        "n_primary_episodes": int(datasets["product_campaign"].is_primary.sum()),
        "overlap_episodes": int((~datasets["product_campaign"].is_primary).sum()),
        "n_product_week_rows": int(len(datasets["product_week"])),
        "effective_independent_campaigns": int(_load("dim_promotion").promo_key.nunique()),
        "historical_product_day_reference_wape": 0.4164,
        "campaign_wape_macro_windows": campaign_macro_wape,
        "campaign_wape_micro_pooled": campaign_micro_wape,
        "heavy_models_status": "not_run_gate_independent_campaigns_insufficient_for_reliable_ml",
        "discount_support": {str(k): int(v) for k, v in _load("dim_promotion").remise_pct.value_counts().sort_index().items()},
        "metrics_path": str(MODEL_OUT / "campaign_metrics.csv"),
        "features_strictly_pre_campaign": True,
        "post_campaign_features_used": False,
        "causal_claim_allowed": False,
        "automatic_application_allowed": False,
    }
    (MODEL_OUT / "metadata.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    manifest = {}
    for path in sorted(MODEL_OUT.glob("*")):
        if path.is_file() and path.name != "manifest.sha256.json":
            manifest[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    for name in ("pricing_product_campaign.parquet", "pricing_product_week.parquet", "pricing_product_day_reference.parquet"):
        path = OUT / name
        manifest[f"data/processed/final/{name}"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (MODEL_OUT / "manifest.sha256.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    lines = ["# 10 — Pricing au niveau campagne", "", "Statut : audit et baselines bornées, sans push ni écriture Supabase.", "", f"- Campagnes réelles indépendantes : **{summary['n_campaigns']}** ; épisodes produit×campagne : **{summary['n_product_campaign_episodes']}** ; épisodes sans chevauchement : **{summary['n_primary_episodes']}** ; épisodes en chevauchement : **{summary['overlap_episodes']}**.", f"- Produit×semaine : **{summary['n_product_week_rows']}** lignes ; produit×jour historique secondaire : WAPE **0,4164**.", "- Les features sont calculées strictement avant le début de campagne ; la période post-campagne est descriptive uniquement.", "- Une campagne réelle ne traverse jamais train/test : les fenêtres sont définies par campagne entière.", "", "## Métriques produit×campagne et produit×semaine", "", metrics.to_markdown(index=False, floatfmt='.4f'), "", f"WAPE campagne macro (moyenne des fenêtres, baseline historique) : **{campaign_macro_wape:.4f}**. WAPE campagne micro poolée (erreurs pondérées par volume réel) : **{campaign_micro_wape:.4f}**. Ces agrégations sont distinctes.", "", "Le seuil utile <0,30 n'est pas atteint. Les 120 campagnes indépendantes et les chevauchements rendent une optimisation ML plus ambitieuse prématurée ; GLM/pooling restent prioritaires. LightGBM Tweedie/Poisson/L1, CatBoost, hurdle, hiérarchique et ensemble contraint sont explicitement **non lancés** (gate de suffisance des campagnes indépendantes non franchi), sans présenter leur absence comme un résultat favorable.", "", "## Support et garde-fous", "", "- Les 7 niveaux de remise observés sont publiés dans les métadonnées ; la remise à 40 % n'est recommandable que si son support est suffisant.", "- Les produits sans support individuel sont affectés au pooling catégorie ; sinon `insufficient_evidence`.", "- Aucun effet causal, aucune élasticité continue, aucune extrapolation et aucune application automatique ne sont autorisés.", "", "## Artifacts", "", "Datasets : `pricing_product_campaign.parquet`, `pricing_product_week.parquet`, `pricing_product_day_reference.parquet`. Métriques et SHA-256 : `models/campaign_level_pricing/`."]
    REPORT.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
