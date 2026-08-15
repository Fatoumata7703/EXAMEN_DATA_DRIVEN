"""Test de signal exploratoire — mesure ce que la base actuelle permet réellement.

    python scripts/test_signal.py

Backtest de baselines simples (h=30, 6 fenêtres glissantes) et diagnostic de la
variation tarifaire exploitable. **Exploratoire** : aucun modèle produit ici
n'est un livrable, et aucun n'est présenté comme définitif.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config.settings import PROJECT_ROOT  # noqa: E402
from src.evaluation.metrics import compute_all_metrics, naive_scale  # noqa: E402

OUT = io.StringIO()
H = 30
N_WINDOWS = 6


def say(text: str = "") -> None:
    print(text)
    OUT.write(text + "\n")


# ---------------------------------------------------------------------------
# Baselines — chacune n'utilise QUE l'entraînement
# ---------------------------------------------------------------------------
def baseline_predictions(train: pd.DataFrame, test: pd.DataFrame) -> dict[str, pd.Series]:
    """Prédictions alignées sur l'index de `test`."""
    preds: dict[str, pd.Series] = {}
    idx = test.index

    # 1. Zéro (référence absolue)
    preds["Zero"] = pd.Series(0.0, index=idx)

    # 2. Moyenne globale
    preds["MoyenneGlobale"] = pd.Series(train["y"].mean(), index=idx)

    # 3. Moyenne par produit
    mp = train.groupby("unique_id")["y"].mean()
    preds["MoyenneProduit"] = test["unique_id"].map(mp).fillna(train["y"].mean()).to_numpy()
    preds["MoyenneProduit"] = pd.Series(preds["MoyenneProduit"], index=idx)

    # 4. Moyenne produit x jour de semaine
    tr = train.assign(dow=train["ds"].dt.dayofweek)
    mpd = tr.groupby(["unique_id", "dow"])["y"].mean()
    key = list(zip(test["unique_id"], test["ds"].dt.dayofweek))
    preds["MoyenneProduitJour"] = pd.Series(
        [mpd.get(k, np.nan) for k in key], index=idx
    ).fillna(test["unique_id"].map(mp)).fillna(train["y"].mean())

    # 5. Moyenne produit sur les 28 derniers jours
    cutoff = train["ds"].max() - pd.Timedelta(days=27)
    recent = train[train["ds"] >= cutoff]
    mr = recent.groupby("unique_id")["y"].mean()
    preds["Moyenne28j"] = pd.Series(
        test["unique_id"].map(mr).fillna(train["y"].mean()).to_numpy(), index=idx
    )

    # 6. Naive : dernière valeur observée
    last = train.sort_values("ds").groupby("unique_id")["y"].last()
    preds["Naive"] = pd.Series(
        test["unique_id"].map(last).fillna(0.0).to_numpy(), index=idx
    )

    # 7. Seasonal Naive : même jour de la semaine précédente
    last_week = train[train["ds"] > train["ds"].max() - pd.Timedelta(days=7)]
    sn = last_week.set_index(["unique_id", last_week["ds"].dt.dayofweek])["y"]
    preds["SeasonalNaive7"] = pd.Series(
        [sn.get(k, np.nan) for k in key], index=idx
    ).fillna(test["unique_id"].map(mp)).fillna(0.0)

    # 8. Moyenne produit x jour de semaine, ajustée de l'effet promotion
    if "en_promotion" in train.columns:
        base = tr[tr["en_promotion"] == 0]["y"].mean()
        promo = tr[tr["en_promotion"] == 1]["y"].mean()
        uplift = promo / base if base > 0 else 1.0
        factor = np.where(test["en_promotion"] == 1, uplift, 1.0)
        preds["MoyenneProduitJour+Promo"] = preds["MoyenneProduitJour"] * factor
    return preds


def run_backtest(table: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    dmax = table["ds"].max()
    rows, per_window = [], []
    for w in range(N_WINDOWS, 0, -1):
        cutoff = dmax - pd.Timedelta(days=H * w)
        train = table[table["ds"] <= cutoff]
        test = table[(table["ds"] > cutoff) & (table["ds"] <= cutoff + pd.Timedelta(days=H))]
        if train.empty or test.empty:
            continue
        scales = train.groupby("unique_id")["y"].apply(lambda s: naive_scale(s.to_numpy(), 7))
        for name, pred in baseline_predictions(train, test).items():
            met = compute_all_metrics(test["y"], pred)
            s = test["unique_id"].map(scales)
            valid = s.notna() & (s > 1e-9)
            met["MASE"] = float(
                ((test["y"] - pred).abs()[valid] / s[valid]).mean()
            ) if valid.any() else np.nan
            met.update({"modele": name, "fenetre": N_WINDOWS - w + 1,
                        "debut_test": test["ds"].min().date()})
            rows.append(met)
        per_window.append({"fenetre": N_WINDOWS - w + 1, "n_train": len(train),
                           "n_test": len(test), "cutoff": cutoff.date()})
    detail = pd.DataFrame(rows)
    resume = (
        detail.groupby("modele")
        .agg(WAPE=("WAPE", "mean"), WAPE_ecart=("WAPE", "std"), MAE=("MAE", "mean"),
             RMSE=("RMSE", "mean"), MASE=("MASE", "mean"), biais=("biais", "mean"),
             sous_prev=("taux_sous_prevision", "mean"))
        .sort_values("WAPE")
        .reset_index()
    )
    return resume, detail


def main() -> int:
    table = pd.read_parquet(PROJECT_ROOT / "data" / "processed" / "table_analytique.parquet")
    table["ds"] = pd.to_datetime(table["ds"])
    table = table.sort_values(["unique_id", "ds"]).reset_index(drop=True)

    say("=" * 78)
    say("TEST DE SIGNAL — FORECASTING (exploratoire, h=30, 6 fenêtres)")
    say("=" * 78)
    resume, detail = run_backtest(table)
    say("")
    say("  Baselines, moyennes sur les 6 fenêtres :")
    say("")
    say(f"  {'modèle':<26} {'WAPE':>7} {'±écart':>7} {'MAE':>7} {'RMSE':>7} {'MASE':>7} {'biais':>8}")
    for _, r in resume.iterrows():
        say(f"  {r['modele']:<26} {r['WAPE']:>7.4f} {r['WAPE_ecart']:>7.4f} {r['MAE']:>7.4f} "
            f"{r['RMSE']:>7.4f} {r['MASE']:>7.3f} {r['biais']:>8.4f}")

    best = resume.iloc[0]
    zero = resume[resume["modele"] == "Zero"].iloc[0]
    say("")
    say(f"  Meilleure baseline : {best['modele']} (WAPE {best['WAPE']:.4f})")
    say(f"  Stabilité entre fenêtres : écart-type WAPE = {best['WAPE_ecart']:.4f} "
        f"({100*best['WAPE_ecart']/best['WAPE']:.1f} % de la moyenne)")
    say("")
    say("  --- Décomposition de la variance de y (sur tout l'historique) ---")
    tot = table["y"].var()
    for label, keys in (
        ("niveau produit", ["unique_id"]),
        ("jour de semaine", [table["ds"].dt.dayofweek]),
        ("mois", [table["ds"].dt.month]),
        ("promotion", ["en_promotion"]),
        ("produit x jour de semaine", ["unique_id", table["ds"].dt.dayofweek]),
        ("produit x mois", ["unique_id", table["ds"].dt.month]),
    ):
        grp = table.groupby(keys)["y"]
        explique = 1 - grp.transform(lambda s: s - s.mean()).var() / tot
        say(f"    {label:<28} part de variance expliquée : {explique:6.2%}")

    say("")
    say("  --- Effets moyens ---")
    dow = table.groupby(table["ds"].dt.dayofweek)["y"].mean()
    say(f"    semaine {dow.loc[0:4].mean():.3f} vs week-end {dow.loc[5:6].mean():.3f} "
        f"-> +{100*(dow.loc[5:6].mean()/dow.loc[0:4].mean()-1):.1f} %")
    mois = table.groupby(table["ds"].dt.month)["y"].mean()
    say(f"    mois le plus fort {mois.idxmax()} ({mois.max():.3f}) vs plus faible "
        f"{mois.idxmin()} ({mois.min():.3f}) -> facteur {mois.max()/mois.min():.2f}")
    pr = table.groupby("en_promotion")["y"].mean()
    say(f"    hors promo {pr[0]:.3f} vs promo {pr[1]:.3f} -> +{100*(pr[1]/pr[0]-1):.1f} %")
    say(f"    part de zéros : {(table['y'] == 0).mean():.2%}")

    # ------------------------------------------------------------------
    say("")
    say("=" * 78)
    say("TEST DE SIGNAL — PRICING")
    say("=" * 78)
    v = pd.read_parquet(PROJECT_ROOT / "data" / "raw" / "fact_ventes.parquet")
    p = pd.read_parquet(PROJECT_ROOT / "data" / "raw" / "dim_produit.parquet")
    promo = pd.read_parquet(PROJECT_ROOT / "data" / "raw" / "dim_promotion.parquet")
    v["ds"] = pd.to_datetime(v["date_key"], format="%Y%m%d")
    m = v.merge(p[["produit_key", "prix_base_xof", "cout_xof", "categorie"]], on="produit_key")
    m = m.merge(promo[["promo_key", "remise_pct"]], on="promo_key", how="left")
    m["remise"] = m["remise_pct"].fillna(0)
    m["pu"] = m["montant_net_xof"] / m["quantite"]
    m["marge_u"] = m["pu"] - m["cout_xof"]
    m["taux_marge"] = m["marge_u"] / m["pu"]

    jour = table.copy()
    niveaux = jour.groupby("unique_id")["remise_pct"].nunique()
    say(f"  niveaux de remise par produit : médiane {niveaux.median():.0f}, "
        f"min {niveaux.min()}, max {niveaux.max()}")
    say(f"  produits exposés à >= 2 niveaux : {int((niveaux >= 2).sum())} / {len(niveaux)}")
    say(f"  produits exposés à >= 3 niveaux : {int((niveaux >= 3).sum())} / {len(niveaux)}")
    say(f"  campagnes promotionnelles        : {len(promo)}")
    say(f"  durée des campagnes (jours)      : médiane {(promo['end_date'] - promo['start_date']).dt.days.median() + 1:.0f}")
    say(f"  produit-jours en promotion       : {int(jour['en_promotion'].sum()):,} "
        f"({jour['en_promotion'].mean():.1%})")
    say(f"  produit-jours hors promotion     : {int((jour['en_promotion'] == 0).sum()):,}")
    say(f"  promotions concurrentes (>1)     : {int((jour['n_promotions'] > 1).sum()):,} produit-jours")

    say("")
    say("  --- Support commun : ventes observées par niveau de remise ---")
    sup = jour.groupby("remise_pct").agg(
        produit_jours=("y", "size"), y_moyen=("y", "mean"),
        produits=("unique_id", "nunique")
    )
    say(f"    {'remise':>7} {'produit-jours':>14} {'produits':>9} {'y moyen':>9}")
    for r, row in sup.iterrows():
        say(f"    {r:>6.0f}% {row['produit_jours']:>14,} {row['produits']:>9.0f} {row['y_moyen']:>9.3f}")

    say("")
    say("  --- Variation du prix payé ---")
    say(f"    produits dont le prix CATALOGUE varie : {int((p.groupby('product_id')['prix_base_xof'].nunique() > 1).sum())} / {len(p)}")
    ratio = m.groupby("produit_key")["pu"].agg(lambda s: s.max() / s.min())
    say(f"    amplitude prix payé max/min : médiane {ratio.median():.3f}, p95 {ratio.quantile(.95):.3f}")
    hors = m[m["promo_key"].isna()]
    r2 = hors.groupby("produit_key")["pu"].agg(lambda s: s.max() / s.min())
    say(f"    amplitude HORS promo (bruit seul) : médiane {r2.median():.4f}")

    say("")
    say("  --- Marges ---")
    say(f"    taux de marge : médiane {m['taux_marge'].median():.1%}, "
        f"p5 {m['taux_marge'].quantile(.05):.1%}, p95 {m['taux_marge'].quantile(.95):.1%}")
    say(f"    lignes à marge négative : {int((m['marge_u'] < 0).sum()):,} "
        f"({(m['marge_u'] < 0).mean():.2%})")
    neg = m[m["marge_u"] < 0]
    if len(neg):
        say(f"    remise médiane sur ces lignes : {neg['remise'].median():.0f} %")
        say(f"    produits concernés : {neg['produit_key'].nunique()} / {m['produit_key'].nunique()}")
        say(f"    par catégorie : {neg.groupby('categorie').size().sort_values(ascending=False).head(3).to_dict()}")

    # Élasticité exploratoire intra-produit sur la seule variation promo
    say("")
    say("  --- Élasticité exploratoire (intra-produit, variation promo uniquement) ---")
    d = jour[jour["y"] > 0].copy()
    d["lp"] = np.log(d["prix_attendu"])
    d["lq"] = np.log(d["y"])
    d["lp_c"] = d["lp"] - d.groupby("unique_id")["lp"].transform("mean")
    d["lq_c"] = d["lq"] - d.groupby("unique_id")["lq"].transform("mean")
    beta = np.polyfit(d["lp_c"], d["lq_c"], 1)[0]
    say(f"    pente log-log intra-produit : {beta:+.3f}  (n={len(d):,} produit-jours avec vente)")
    say("    ATTENTION : estimation naïve, sans contrôle du calendrier ni de la")
    say("    sélection des campagnes. Indicative du signal disponible, PAS un")
    say("    résultat publiable.")

    (PROJECT_ROOT / "reports" / "10_test_signal.md").write_text(
        "# 10 — Test de signal (exploratoire)\n\n"
        "_Sortie de `python scripts/test_signal.py`. Aucun modèle présenté ici "
        "n'est un livrable._\n\n```\n" + OUT.getvalue() + "```\n",
        encoding="utf-8",
    )
    detail.to_csv(PROJECT_ROOT / "reports" / "10_backtest_baselines.csv", index=False)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
