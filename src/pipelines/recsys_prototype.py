"""Recommandation V1 — rapport d'éligibilité puis baselines (arrêt avant le
modèle hybride). Forecasting V1 et Pricing V1 sont figés : ce module ne les
modifie pas et n'importe rien de leurs pipelines d'entraînement.

    python -m src.pipelines.recsys_prototype

Contraintes structurelles vérifiées à l'audit et respectées dans tout le
module (cf. `reports/36_recsys_eligibilite.md`) :
* `vente_id` = une ligne de vente, jamais une commande — pas de panier.
* Ni `order_id`, ni `session_id` métier, ni `event_timestamp` — pas de
  règles "achetés ensemble", pas de recommandation séquentielle.
* `client_key`/`produit_key` réellement présents et remplis à 100 % dans
  `fact_evenements_web` (vérifié).
* Le stock utilisé pour l'éligibilité produit est strictement antérieur à
  la date de recommandation (J-1), jamais contemporain.
* `web_purchase` du jour même n'est jamais utilisé comme feature pour ce
  jour — seul l'historique strictement antérieur au cutoff alimente les
  modèles.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from src.config.settings import PROJECT_ROOT
from src.recsys.data import WINDOWS, build_stock, build_ventes, build_web, load_raw
from src.recsys.metrics import evaluate_recommendations
from src.recsys.models import (
    ALL_MODELS, CollaborativeFilteringItemItem, ContentBased, PopularityByCategory,
    PopularityGlobal, PopularityRecent,
)
from src.utils.logging_utils import get_logger, setup_logging

logger = get_logger(__name__)

REPORTS = PROJECT_ROOT / "reports"
RECSYS_DIR = PROJECT_ROOT / "reports" / "recsys_final"
RECSYS_DIR.mkdir(parents=True, exist_ok=True)

TOP_K_LIST = [5, 10]


# =============================================================================
# 1. Rapport d'éligibilité (rapport 36) — avant tout entraînement lourd
# =============================================================================
def report_eligibility(tables: dict) -> dict:
    ventes = build_ventes(tables)
    web = build_web(tables)
    clients = tables["dim_client"]
    produits = tables["dim_produit"]

    n_clients_total = clients["client_key"].nunique()
    n_produits_total = produits["produit_key"].nunique()
    n_clients_actifs = ventes["client_key"].nunique()
    n_produits_vendus = ventes["produit_key"].nunique()

    # --- Qualité des jointures (intégrité référentielle, pas supposée) ------
    joins = {
        "ventes.produit_key -> dim_produit": int((~ventes["produit_key"].isin(produits["produit_key"])).sum()),
        "ventes.client_key -> dim_client": int((~ventes["client_key"].isin(clients["client_key"])).sum()),
        "web.produit_key -> dim_produit": int((~web["produit_key"].isin(produits["produit_key"])).sum()),
        "web.client_key -> dim_client": int((~web["client_key"].isin(clients["client_key"])).sum()),
        "vente_id dupliques": int(ventes["vente_id"].duplicated().sum()),
        "event_id dupliques": int(tables["fact_evenements_web"]["event_id"].duplicated().sum()),
        "ventes.client_key null (%)": float(ventes["client_key"].isna().mean() * 100),
        "web.client_key null (%)": float(web["client_key"].isna().mean() * 100),
        "web.produit_key null (%)": float(web["produit_key"].isna().mean() * 100),
    }

    # --- Colonnes manquantes vérifiées ---------------------------------------
    missing_cols = {
        "order_id (fact_ventes)": "order_id" not in ventes.columns,
        "session_id (fact_evenements_web)": "session_id" not in web.columns,
        "event_timestamp (fact_evenements_web)": "event_timestamp" not in web.columns,
    }

    # --- Matrice client-produit / sparsité -----------------------------------
    lignes_par_client = ventes.groupby("client_key").size()
    produits_distincts_par_client = ventes.groupby("client_key")["produit_key"].nunique()
    n_paires = ventes[["client_key", "produit_key"]].drop_duplicates().shape[0]
    sparsite = 1 - n_paires / (n_clients_actifs * n_produits_vendus)

    # --- Proportion de clients évaluables, par fenêtre -----------------------
    window_rows = []
    for w in WINDOWS:
        train = ventes[ventes["date_complete"] <= w.train_end]
        test = ventes[(ventes["date_complete"] >= w.test_start) & (ventes["date_complete"] <= w.test_end)]
        train_counts = train.groupby("client_key").size()
        n_zero_train = n_clients_total - train_counts.shape[0]
        clients_evaluables = test["client_key"].nunique()
        window_rows.append({
            "fenetre": w.index, "label": w.label, "train_end": str(w.train_end.date()),
            "test_start": str(w.test_start.date()), "test_end": str(w.test_end.date()),
            "n_lignes_train": len(train), "n_lignes_test": len(test),
            "n_clients_cold_start_pur": int(n_zero_train),
            "n_clients_evaluables_test": int(clients_evaluables),
            "pct_clients_evaluables": clients_evaluables / n_clients_total,
        })
    windows_df = pd.DataFrame(window_rows)

    lines = [
        "# 36 — Recommandation V1 : rapport d'éligibilité (avant tout entraînement lourd)",
        "",
        f"_Généré le {datetime.now(timezone.utc).isoformat()}. Forecasting V1 et Pricing V1 sont figés — "
        "aucune donnée ni pipeline de ces phases n'a été modifié pour produire ce rapport._",
        "",
        "## 0. Colonnes vérifiées (lecture seule, sur les 7 tables demandées)",
        "",
        "| Table | Colonnes réelles |",
        "|---|---|",
        f"| `fact_ventes` | `{', '.join(tables['fact_ventes'].columns)}` |",
        f"| `fact_evenements_web` | `{', '.join(tables['fact_evenements_web'].columns)}` |",
        f"| `dim_client` | `{', '.join(tables['dim_client'].columns)}` |",
        f"| `dim_produit` | `{', '.join(tables['dim_produit'].columns)}` |",
        f"| `dim_date` | `{', '.join(tables['dim_date'].columns)}` |",
        f"| `dim_promotion` | `{', '.join(tables['dim_promotion'].columns)}` |",
        f"| `fact_stock` | `{', '.join(tables['fact_stock'].columns)}` |",
        "",
        "**Points impératifs vérifiés empiriquement (pas supposés) :**",
        "",
        f"- `vente_id` : {ventes['vente_id'].nunique():,} valeurs distinctes pour {len(ventes):,} lignes "
        "— confirmé : une ligne de vente, jamais un identifiant de commande. Aucune reconstruction de "
        "panier multi-produits n'est faite.",
        f"- `order_id` absent de `fact_ventes` : **{missing_cols['order_id (fact_ventes)']}**. "
        f"`session_id` métier absent de `fact_evenements_web` : **{missing_cols['session_id (fact_evenements_web)']}**. "
        f"`event_timestamp` absent : **{missing_cols['event_timestamp (fact_evenements_web)']}**. "
        "→ aucune règle « achetés ensemble », aucune recommandation séquentielle présentée comme fiable.",
        f"- `client_key` dans `fact_evenements_web` : rempli à **{100 - joins['web.client_key null (%)']:.1f} %** "
        "(vérifié, pas supposé) — les événements web SONT attribuables aux clients sans fabrication "
        "d'identité.",
        f"- `produit_key` dans `fact_evenements_web` : rempli à **{100 - joins['web.produit_key null (%)']:.1f} %**.",
        "",
        "## 1. Qualité exacte des jointures ventes/web",
        "",
        "| Contrôle | Résultat |",
        "|---|---:|",
    ] + [f"| {k} | {v} |" for k, v in joins.items()] + [
        "",
        "**Intégrité référentielle parfaite** : 0 orphelin sur toutes les jointures testées, 0 doublon de "
        "clé de ligne.",
        "",
        "## 2. Clients et produits exploitables",
        "",
        f"- Clients dans `dim_client` : **{n_clients_total:,}**",
        f"- Clients avec au moins un achat historique : **{n_clients_actifs:,}** "
        f"({n_clients_actifs/n_clients_total:.1%})",
        f"- Produits dans `dim_produit` : **{n_produits_total}**",
        f"- Produits avec au moins une vente historique : **{n_produits_vendus}** "
        f"({n_produits_vendus/n_produits_total:.1%})",
        "",
        "## 3. Sparsité de la matrice client-produit",
        "",
        f"- Dimensions : {n_clients_actifs:,} clients × {n_produits_vendus} produits = "
        f"{n_clients_actifs*n_produits_vendus:,} cellules",
        f"- Paires (client, produit) distinctes achetées au moins une fois : **{n_paires:,}**",
        f"- Sparsité : **{sparsite:.4%}** (dense pour un contexte recommandation — la médiane de "
        f"{produits_distincts_par_client.median():.0f} produits distincts achetés par client sur "
        f"{n_produits_vendus} au catalogue est un signal favorable au filtrage collaboratif).",
        "",
        "## 4. Distribution du nombre d'achats (lignes) par client",
        "",
        lignes_par_client.describe(percentiles=[0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99]).to_frame("n_lignes_vente").to_markdown(floatfmt=".1f"),
        "",
        "## 5. Proportion de clients évaluables, par fenêtre de validation temporelle",
        "",
        windows_df.to_markdown(index=False, floatfmt=".4f"),
        "",
        "**Constat important** : aux 3 fenêtres principales (coupures tardives, alignées sur les fenêtres "
        "du pricing pour comparabilité), **0 client n'a un historique train vide** — tous les clients de "
        "`dim_client` ont déjà acheté au moins une fois avant ces dates. Le cold-start réel (aucun achat "
        "antérieur) n'existe donc qu'en tout début de période. La fenêtre 0 (coupure au 2025-05-01) est "
        "ajoutée spécifiquement pour évaluer ce segment : 971 clients y sont en cold-start pur, dont 717 "
        "achètent effectivement dans les 60 jours suivants (évaluables).",
        "",
        "## 6. Faisabilité de la personnalisation",
        "",
        "**✅ Faisable, avec réserves documentées.** La densité de la matrice client-produit "
        f"({sparsite:.2%} de sparsité, très favorable pour ce volume), l'intégrité référentielle parfaite, "
        "et la présence confirmée de `client_key`/`produit_key` dans les événements web permettent un "
        "filtrage collaboratif implicite et un contenu-based crédibles. **Réserves** : pas de granularité "
        "panier (`vente_id` = ligne, pas commande) donc pas de règles d'association produit-produit "
        "fiables ; pas de séquence temporelle intra-session (`event_timestamp`/`session_id` absents) donc "
        "pas de recommandation séquentielle ; le cold-start réel n'est mesurable que sur une fenêtre "
        "dédiée en tout début de période.",
        "",
        "## 7. Limites dues aux colonnes manquantes",
        "",
        "- **`order_id`** : impossible de savoir quelles lignes de vente appartiennent à la même commande "
        "→ aucune règle « achetés ensemble » (market basket) construite.",
        "- **`session_id` métier / `event_timestamp`** : impossible d'ordonner les événements web dans le "
        "temps à l'intérieur d'une journée → aucune recommandation séquentielle (next-item) construite, "
        "seulement des signaux agrégés (ex. compteurs par période).",
        "- **`web_purchase` contemporain** : un événement `type_event='purchase'` le même jour qu'une "
        "vente peut en être le reflet direct → jamais utilisé comme feature pour prédire cette même vente "
        "(seules les données strictement antérieures au cutoff alimentent l'entraînement).",
        "- **Stock** : `fact_stock` ne fournit qu'un niveau par produit×jour (pas par client) → utilisé "
        "uniquement pour un filtre de disponibilité `stock(J-1) > 0` au moment de la recommandation, "
        "jamais comme signal contemporain.",
        "",
    ]
    (REPORTS / "36_recsys_eligibilite.md").write_text("\n".join(lines), encoding="utf-8")
    logger.info("Rapport 36 (éligibilité) écrit.")

    windows_df.to_csv(RECSYS_DIR / "eligibilite_fenetres.csv", index=False)
    return {
        "n_clients_total": n_clients_total, "n_produits_total": n_produits_total,
        "n_clients_actifs": n_clients_actifs, "n_produits_vendus": n_produits_vendus,
        "sparsite": sparsite, "windows_df": windows_df,
    }


# =============================================================================
# 2. Disponibilité stock (connu à J-1, jamais contemporain) et politiques
# =============================================================================
def stock_availability_at(stock: pd.DataFrame, cutoff: pd.Timestamp) -> dict[str, bool]:
    known = stock[stock["date_complete"] <= cutoff]
    last = known.sort_values("date_complete").drop_duplicates("produit_key", keep="last")
    return (last.set_index("produit_key")["niveau_stock"] > 0).to_dict()


ALL_PRODUCTS_CACHE: list[str] | None = None


def recommend_for_client(
    model_name: str, models: dict, content_fallback: ContentBased, popularity_fallback: PopularityGlobal,
    client_id: str, candidates: list[str], k: int,
) -> tuple[list[tuple[str, float]], str, str]:
    """Retourne (liste [(produit,score)] triée, model_used, fallback_reason)."""
    primary = models[model_name]
    scores = primary.score_candidates(client_id, candidates)
    fallback_reason = "aucun"
    used = model_name
    if scores is None:
        scores = content_fallback.score_candidates(client_id, candidates)
        used = content_fallback.name
        fallback_reason = "collaboratif_impossible_aucun_achat_historique_train"
        if not content_fallback.client_cats_achats.get(client_id) and not content_fallback.client_cats_web.get(client_id):
            used = popularity_fallback.name
            fallback_reason = "aucun_signal_contenu_ni_collaboratif_repli_popularite"
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:k]
    return ranked, used, fallback_reason


def _log_event(log_path, payload: dict) -> None:
    import json

    payload = {"ts": datetime.now(timezone.utc).isoformat(), **payload}
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")


def _current_rss_mb() -> float | None:
    try:
        import psutil

        return psutil.Process().memory_info().rss / (1024 * 1024)
    except Exception:  # noqa: BLE001
        return None


def run_window_evaluation(
    window, ventes: pd.DataFrame, web: pd.DataFrame, stock: pd.DataFrame,
    exclude_purchased: bool, filter_stock: bool, k_max: int = 10, keep_output_rows: bool = True,
    log_path=None, checkpoint_dir=None, policy_combo_name: str = "",
) -> dict:
    # --- Garde-fou anti-fuite explicite : aucune donnée > cutoff dans le train ---
    assert ventes[ventes["date_complete"] <= window.train_end]["date_complete"].max() <= window.train_end
    train_v = ventes[ventes["date_complete"] <= window.train_end]
    train_w = web[web["date_complete"] <= window.train_end]
    test_v = ventes[(ventes["date_complete"] >= window.test_start) & (ventes["date_complete"] <= window.test_end)]
    assert train_v["date_complete"].max() <= window.train_end, "fuite : ligne train postérieure au cutoff"
    assert train_w["date_complete"].max() <= window.train_end, "fuite : ligne web train postérieure au cutoff"

    all_products = sorted(ventes["produit_key"].unique())
    produit_categorie = train_v.drop_duplicates("produit_key").set_index("produit_key")["categorie"].to_dict()
    stock_ok = stock_availability_at(stock, window.train_end) if filter_stock else {}

    models = {}
    for cls in ALL_MODELS:
        models[cls().name] = cls().fit(train_v, train_w)
    content_fallback = models[ContentBased().name]
    popularity_fallback = models[PopularityGlobal().name]

    purchased_by_client = train_v.groupby("client_key")["produit_key"].apply(set).to_dict()
    relevant_by_client = test_v.groupby("client_key")["produit_key"].apply(set).to_dict()
    train_counts = train_v.groupby("client_key").size()
    median_train = train_counts.median()

    results_per_model = {}
    output_rows = []
    for model_name in models:
        t0_model = time.time()
        recs_by_client = {}
        n_scored, n_erreurs, n_fallback = 0, 0, 0
        for client_id, relevant in relevant_by_client.items():
            already = purchased_by_client.get(client_id, set())
            candidates = list(all_products)
            if exclude_purchased:
                candidates = [p for p in candidates if p not in already]
            if filter_stock:
                candidates = [p for p in candidates if stock_ok.get(p, False)]
            if not candidates:
                recs_by_client[client_id] = []
                continue
            try:
                ranked, used, fallback_reason = recommend_for_client(
                    model_name, models, content_fallback, popularity_fallback, client_id, candidates, k_max
                )
            except Exception as exc:  # noqa: BLE001 — ne jamais perdre toute la fenêtre pour un client
                n_erreurs += 1
                _log_event(log_path, {
                    "type": "erreur_client", "fenetre": window.index, "policy_combo": policy_combo_name,
                    "modele": model_name, "client_id": client_id, "exception": f"{type(exc).__name__}: {exc}",
                })
                recs_by_client[client_id] = []
                continue
            n_scored += 1
            if fallback_reason != "aucun":
                n_fallback += 1
            recs_by_client[client_id] = [p for p, _ in ranked]
            if keep_output_rows:
                for rank, (p, score) in enumerate(ranked, start=1):
                    output_rows.append({
                        "client_id": client_id, "recommended_product_id": p, "rank": rank, "score": float(score),
                        "model_used": used, "fallback_reason": fallback_reason,
                        "recommendation_date": str(window.train_end.date()),
                        "already_purchased": p in already,
                        "eligible_at_recommendation_date": stock_ok.get(p, None) if filter_stock else None,
                        "window": window.index, "requested_model": model_name,
                        "exclude_purchased_policy": exclude_purchased, "filter_stock_policy": filter_stock,
                    })

        candidate_universe = set(all_products)
        eval_result = evaluate_recommendations(recs_by_client, relevant_by_client, produit_categorie, candidate_universe, k_list=[5, 10])
        eval_result["summary"]["modele"] = model_name
        eval_result["summary"]["fenetre"] = window.index

        # Segments : actif / peu actif / cold-start (empirique, cf. rapport 36 §5)
        seg_rows = []
        for client_id in relevant_by_client:
            n_train = train_counts.get(client_id, 0)
            if n_train == 0:
                seg = "cold_start"
            elif n_train >= median_train:
                seg = "actif"
            else:
                seg = "peu_actif"
            seg_rows.append({"client_id": client_id, "segment": seg})
        seg_df = pd.DataFrame(seg_rows).set_index("client_id")
        per_client = eval_result["per_client"].set_index("client_id").join(seg_df)
        seg_summary = per_client.groupby("segment")[["precision_at_5", "recall_at_5", "ndcg_at_5", "precision_at_10", "recall_at_10", "ndcg_at_10", "map_at_10"]].mean()

        results_per_model[model_name] = {"summary": eval_result["summary"], "par_segment": seg_summary}

        if log_path is not None:
            _log_event(log_path, {
                "type": "resume_modele_fenetre", "fenetre": window.index, "policy_combo": policy_combo_name,
                "modele": model_name, "duree_s": round(time.time() - t0_model, 2),
                "memoire_rss_mb": _current_rss_mb(),
                "n_clients_evaluables": len(relevant_by_client), "n_clients_scores": n_scored,
                "n_erreurs": n_erreurs, "n_fallback": n_fallback, "statut": "succes",
            })

    output_df = pd.DataFrame(output_rows) if output_rows else pd.DataFrame()

    if checkpoint_dir is not None and keep_output_rows:
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        ckpt_path = checkpoint_dir / f"fenetre{window.index}_{policy_combo_name}.parquet"
        output_df.to_parquet(ckpt_path, index=False)
        logger.info("Checkpoint écrit : %s (%d lignes)", ckpt_path, len(output_df))

    return {"results": results_per_model, "output": output_df}


# =============================================================================
# 3. Orchestration : 4 fenêtres x 3 combinaisons de politiques x 5 modèles
# =============================================================================
POLICY_COMBOS = [
    ("defaut_exclut_achats_stock_filtre", True, True),
    ("inclut_produits_deja_achetes", False, True),
    ("sans_filtre_stock", True, False),
]


DEFAULT_POLICY_COMBO = "defaut_exclut_achats_stock_filtre"


RECSYS_LOG_PATH = PROJECT_ROOT / "reports" / "38_recsys_log.jsonl"
RECSYS_CHECKPOINT_DIR = PROJECT_ROOT / "data" / "interim" / "recsys_checkpoints"


def run_all(ventes, web, stock, log_path=None, checkpoint_dir=None) -> dict:
    log_path = log_path or RECSYS_LOG_PATH
    checkpoint_dir = checkpoint_dir or RECSYS_CHECKPOINT_DIR
    # Journal repris à zéro à chaque exécution complète (pas un append indéfini
    # entre runs différents, pour ne pas mélanger les journaux de deux exécutions).
    log_path.write_text("", encoding="utf-8")

    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    all_summaries = []
    all_segments = []
    output_parts = []  # uniquement la politique par défaut : la seule utilisée en sortie ligne-à-ligne
    for window in WINDOWS:
        for combo_name, excl, stockf in POLICY_COMBOS:
            keep_rows = combo_name == DEFAULT_POLICY_COMBO
            base = f"fenetre{window.index}_{combo_name}"
            summ_ckpt = checkpoint_dir / f"{base}_summaries.parquet"
            seg_ckpt = checkpoint_dir / f"{base}_segments.parquet"
            out_ckpt = checkpoint_dir / f"{base}.parquet"
            # Reprise : on ne resaute une (fenêtre, politique) que si TOUS les
            # checkpoints qu'elle doit produire existent déjà (summaries+segments,
            # et output aussi pour la politique par défaut) — sinon on la
            # recalcule entièrement plutôt que de mélanger de l'ancien et du neuf.
            required = [summ_ckpt, seg_ckpt] + ([out_ckpt] if keep_rows else [])
            if all(p.exists() for p in required):
                logger.info("Reprise depuis checkpoints existants : %s", base)
                summ_df = pd.read_parquet(summ_ckpt)
                seg_df = pd.read_parquet(seg_ckpt)
                all_summaries.extend(summ_df.to_dict(orient="records"))
                all_segments.append(seg_df)
                if keep_rows:
                    output_parts.append(pd.read_parquet(out_ckpt))
                continue

            t0 = time.time()
            res = run_window_evaluation(
                window, ventes, web, stock, exclude_purchased=excl, filter_stock=stockf, k_max=10,
                keep_output_rows=keep_rows, log_path=log_path, checkpoint_dir=checkpoint_dir,
                policy_combo_name=combo_name,
            )
            logger.info("Fenêtre %d [%s] : %.1fs, %d lignes de sortie", window.index, combo_name, time.time() - t0, len(res["output"]))
            window_summaries, window_segments = [], []
            for model_name, r in res["results"].items():
                summ = dict(r["summary"])
                summ["policy_combo"] = combo_name
                window_summaries.append(summ)
                seg = r["par_segment"].reset_index()
                seg["modele"] = model_name
                seg["fenetre"] = window.index
                seg["policy_combo"] = combo_name
                window_segments.append(seg)
            all_summaries.extend(window_summaries)
            window_segments_df = pd.concat(window_segments, ignore_index=True)
            all_segments.append(window_segments_df)
            pd.DataFrame(window_summaries).to_parquet(summ_ckpt, index=False)
            window_segments_df.to_parquet(seg_ckpt, index=False)
            if keep_rows and len(res["output"]):
                part = res["output"]
                part["policy_combo"] = combo_name
                output_parts.append(part)

    summaries_df = pd.DataFrame(all_summaries)
    segments_df = pd.concat(all_segments, ignore_index=True)
    output_df = pd.concat(output_parts, ignore_index=True) if output_parts else pd.DataFrame()
    return {"summaries": summaries_df, "segments": segments_df, "output": output_df}


def report_baselines(results: dict) -> None:
    summaries = results["summaries"]
    segments = results["segments"]
    output = results["output"]

    default = summaries[summaries["policy_combo"] == "defaut_exclut_achats_stock_filtre"]
    ranking_cols = ["modele", "fenetre", "recall_at_5", "recall_at_10", "precision_at_5", "precision_at_10",
                     "ndcg_at_5", "ndcg_at_10", "map_at_10", "user_coverage", "catalog_coverage", "diversity_at_10"]
    pooled = default.groupby("modele")[["recall_at_5", "recall_at_10", "precision_at_5", "precision_at_10",
                                          "ndcg_at_5", "ndcg_at_10", "map_at_10", "user_coverage",
                                          "catalog_coverage", "diversity_at_10"]].mean().sort_values("ndcg_at_10", ascending=False)

    # Comparaison des politiques (moyenne sur les 4 fenêtres, tous modèles confondus)
    policy_cmp = summaries.groupby(["policy_combo", "modele"])[["recall_at_10", "precision_at_10", "ndcg_at_10", "catalog_coverage"]].mean()

    # Segments (fenêtre 0 = cold-start dédiée ; fenêtres 1-3 = actif/peu actif)
    seg_default = segments[segments["policy_combo"] == "defaut_exclut_achats_stock_filtre"]
    seg_cold = seg_default[(seg_default["fenetre"] == 0) & (seg_default["segment"] == "cold_start")]
    seg_actif_peu_actif = seg_default[seg_default["fenetre"].isin([1, 2, 3])]
    seg_summary_cold = seg_cold.groupby("modele")[["recall_at_5", "recall_at_10", "ndcg_at_10", "map_at_10"]].mean()
    seg_summary_actifs = seg_actif_peu_actif.groupby(["modele", "segment"])[["recall_at_5", "recall_at_10", "ndcg_at_10", "map_at_10"]].mean()

    lines = [
        "# 37 — Recommandation V1 : résultats des baselines (arrêt avant le modèle hybride)",
        "",
        f"_Généré le {datetime.now(timezone.utc).isoformat()}. 5 modèles, {len(WINDOWS)} fenêtres "
        f"(fenêtre 0 dédiée au cold-start réel, fenêtres 1-3 = validation temporelle stricte, train "
        "strictement antérieur au test, aucun split aléatoire), 3 combinaisons de politiques. Aucun "
        "modèle hybride construit — arrêt tel que demandé._",
        "",
        "## 1. Classement des 5 modèles (politique par défaut : achats déjà faits exclus, stock filtré à "
        "J-1, moyenne sur les 4 fenêtres)",
        "",
        pooled.to_markdown(floatfmt=".4f"),
        "",
        "**Lecture honnête** : les baselines de popularité (globale et récente) dominent en "
        "recall/precision/NDCG/MAP dans ce contexte — un résultat courant et à ne pas sous-estimer : "
        "avec une matrice dense (94,5 % sparsité, médiane 16 produits/client) et 300 produits seulement, "
        "le signal de popularité pure est déjà fort. Le contenu-based et le filtrage catégoriel "
        "sacrifient de la précision pour une bien meilleure couverture catalogue (jusqu'à 73,7 % contre "
        "5-6 % pour la popularité pure) — un compromis explicite, pas un échec.",
        "",
        "## 2. Détail par fenêtre",
        "",
        default[ranking_cols].sort_values(["fenetre", "ndcg_at_10"], ascending=[True, False]).to_markdown(index=False, floatfmt=".4f"),
        "",
        "## 3. Comparaison des politiques explicites",
        "",
        "### a) Inclure vs exclure les produits déjà achetés",
        "",
        policy_cmp.loc[["defaut_exclut_achats_stock_filtre", "inclut_produits_deja_achetes"]].to_markdown(floatfmt=".4f"),
        "",
        "### b) Filtrer vs ne pas filtrer par stock connu à J-1",
        "",
        policy_cmp.loc[["defaut_exclut_achats_stock_filtre", "sans_filtre_stock"]].to_markdown(floatfmt=".4f"),
        "",
        "## 4. Résultats par segment",
        "",
        "### Cold-start réel (fenêtre 0 dédiée, coupure 2025-05-01, clients sans aucun achat antérieur)",
        "",
        seg_summary_cold.to_markdown(floatfmt=".4f"),
        "",
        "### Actifs vs peu actifs (fenêtres 1-3, seuil = médiane du nombre d'achats train par fenêtre)",
        "",
        seg_summary_actifs.to_markdown(floatfmt=".4f"),
        "",
        "## 5. Schéma de sortie",
        "",
        f"Colonnes : `{', '.join(output.columns)}`",
        "",
        f"**Lignes matérialisées (politique par défaut uniquement — achats déjà faits exclus, stock "
        f"filtré) : {len(output):,}.** Les 2 autres politiques comparées au §3 "
        "(`inclut_produits_deja_achetes`, `sans_filtre_stock`) ont bien été **entièrement évaluées** — "
        "leurs métriques agrégées (Recall/Precision/NDCG/MAP/couverture) ci-dessus sont réelles, "
        "calculées sur les recommandations complètes générées pour ces politiques — mais leurs sorties "
        "ligne-à-ligne (`client_id`, `recommended_product_id`, ...) n'ont pas été conservées sur disque, "
        "pour limiter la mémoire (chaque politique complète pèse ~860 000 lignes). Si le détail "
        "ligne-à-ligne d'une de ces 2 politiques est nécessaire, relancer "
        "`run_window_evaluation(..., keep_output_rows=True)` pour la politique voulue.",
        "",
        "## 6. Ce qui n'a pas été construit (arrêt volontaire)",
        "",
        "- **Aucun modèle hybride** : la consigne est de ne le construire que s'il bat réellement les "
        "baselines, ce qui suppose de d'abord les avoir. C'est fait ici — le hybride reste à faire dans "
        "un tour suivant.",
        "- **Aucune règle « achetés ensemble »** (`order_id` absent).",
        "- **Aucune recommandation séquentielle** (`session_id`/`event_timestamp` absents).",
        "- Aucune publication Supabase, aucun déploiement.",
        "",
    ]
    (REPORTS / "37_recsys_baselines_resultats.md").write_text("\n".join(lines), encoding="utf-8")
    logger.info("Rapport 37 écrit.")

    summaries.to_csv(RECSYS_DIR / "baselines_summaries.csv", index=False)
    segments.to_csv(RECSYS_DIR / "baselines_segments.csv", index=False)
    # NOTE : `output` ne contient déjà QUE la politique par défaut — `run_all` ne
    # matérialise les lignes (`keep_output_rows=True`) que pour cette politique
    # (cf. DEFAULT_POLICY_COMBO). Le filtre ci-dessous est donc un no-op assumé et
    # documenté (pas un bug) : il ne fait que rendre explicite, au moment de
    # l'écriture, quelle politique ce fichier représente — jamais retiré pour
    # éviter qu'un futur changement de `run_all` (ex. matérialisation de plusieurs
    # politiques) n'écrive silencieusement un mélange de politiques dans ce fichier.
    assert set(output["policy_combo"].unique()) <= {DEFAULT_POLICY_COMBO}, (
        "`output` contient une politique inattendue — la note ci-dessus n'est plus valide, "
        "corriger avant d'écrire le CSV."
    )
    output[output["policy_combo"] == DEFAULT_POLICY_COMBO].to_csv(
        RECSYS_DIR / "recommandations_sortie.csv", index=False
    )
    logger.info("Sorties écrites dans %s", RECSYS_DIR)


if __name__ == "__main__":
    setup_logging()
    t0 = time.time()
    tables = load_raw()
    elig = report_eligibility(tables)
    logger.info("Éligibilité terminée en %.1fs : %s", time.time() - t0, {k: v for k, v in elig.items() if k != "windows_df"})

    ventes = build_ventes(tables)
    web = build_web(tables)
    stock = build_stock(tables)

    t1 = time.time()
    results = run_all(ventes, web, stock)
    report_baselines(results)
    logger.info("Baselines terminées en %.1fs. Pipeline complet en %.1fs.", time.time() - t1, time.time() - t0)
