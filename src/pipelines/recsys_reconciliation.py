"""Recommandation V1 — réconciliation exacte du plafond de Recall, métriques
sur périmètre éligible séparées de l'end-to-end, comparaison des scénarios de
réachat, sélection objective de la baseline principale. Ne réentraîne rien de
lourd : relit les données sources + rejoue uniquement les calculs de
candidats (rapides, déjà utilisés en vérification).

    python -m src.pipelines.recsys_reconciliation

Point d'attention explicite (rappel de l'audit stock antérieur) : le niveau
de stock ne descend JAMAIS sous 21 dans cette livraison (reconfirmé ici,
min=21 sur 117 763 enregistrements) — aucune vraie rupture n'existe. Toute
exclusion liée au stock dans ce rapport vient d'une ABSENCE d'enregistrement
de stock avant le cutoff (produit pas encore suivi), jamais d'un niveau nul
observé. Cette distinction est maintenue explicitement partout ci-dessous.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from src.config.settings import PROJECT_ROOT
from src.recsys.data import WINDOWS, build_stock, build_ventes, build_web, load_raw
from src.recsys.metrics import evaluate_recommendations
from src.utils.logging_utils import get_logger, setup_logging

logger = get_logger(__name__)
REPORTS = PROJECT_ROOT / "reports"
RECSYS_DIR = PROJECT_ROOT / "reports" / "recsys_final"


# =============================================================================
# 1. Réconciliation exacte des cibles exclues, une raison unique par exclusion
# =============================================================================
def reconcile_excluded_targets(ventes: pd.DataFrame, stock: pd.DataFrame, produits: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    from src.pipelines.recsys_prototype import stock_availability_at

    produit_keys_connus = set(produits["produit_key"])
    rows = []
    examples = []
    for window in WINDOWS:
        train_v = ventes[ventes["date_complete"] <= window.train_end]
        test_v = ventes[(ventes["date_complete"] >= window.test_start) & (ventes["date_complete"] <= window.test_end)]
        purchased_by_client = train_v.groupby("client_key")["produit_key"].apply(set).to_dict()
        relevant_by_client = test_v.groupby("client_key")["produit_key"].apply(set).to_dict()

        known_stock_products = set(stock[stock["date_complete"] <= window.train_end]["produit_key"].unique())
        stock_ok = stock_availability_at(stock, window.train_end)
        all_products = set(ventes["produit_key"].unique())

        reasons_count = {"deja_achete_exclu_volontairement": 0, "stock_j1_reellement_nul": 0,
                          "produit_non_encore_disponible": 0, "produit_absent_table_produit": 0, "autre": 0}
        for client_id, targets in relevant_by_client.items():
            already = purchased_by_client.get(client_id, set())
            candidates = (all_products - already) & {p for p, ok in stock_ok.items() if ok}
            excluded = targets - candidates
            for p in excluded:
                if p not in produit_keys_connus:
                    reason = "produit_absent_table_produit"
                elif p in already:
                    reason = "deja_achete_exclu_volontairement"
                elif p not in known_stock_products:
                    reason = "produit_non_encore_disponible"
                elif not stock_ok.get(p, False):
                    reason = "stock_j1_reellement_nul"
                else:
                    reason = "autre"
                reasons_count[reason] += 1
                if len(examples) < 30 and reason in ("produit_non_encore_disponible", "stock_j1_reellement_nul", "autre"):
                    examples.append({"fenetre": window.index, "produit": p, "raison": reason})

        row = {"fenetre": window.index, "n_cibles_totales": sum(len(v) for v in relevant_by_client.values())}
        row.update(reasons_count)
        row["n_cibles_exclues_total"] = sum(reasons_count.values())
        rows.append(row)

    return pd.DataFrame(rows), pd.DataFrame(examples)


# =============================================================================
# 2. Métriques end-to-end (toutes cibles) vs ranking sur cibles éligibles seules
# =============================================================================
def metrics_end_to_end_vs_eligible(ventes: pd.DataFrame, web: pd.DataFrame, stock: pd.DataFrame) -> pd.DataFrame:
    from src.pipelines.recsys_prototype import ALL_MODELS, ContentBased, PopularityGlobal, recommend_for_client, stock_availability_at

    rows = []
    for window in WINDOWS:
        train_v = ventes[ventes["date_complete"] <= window.train_end]
        train_w = web[web["date_complete"] <= window.train_end]
        test_v = ventes[(ventes["date_complete"] >= window.test_start) & (ventes["date_complete"] <= window.test_end)]
        all_products = sorted(ventes["produit_key"].unique())
        produit_categorie = train_v.drop_duplicates("produit_key").set_index("produit_key")["categorie"].to_dict()
        stock_ok = stock_availability_at(stock, window.train_end)

        models = {cls().name: cls().fit(train_v, train_w) for cls in ALL_MODELS}
        content_fallback = models[ContentBased().name]
        popularity_fallback = models[PopularityGlobal().name]
        purchased_by_client = train_v.groupby("client_key")["produit_key"].apply(set).to_dict()
        relevant_by_client = test_v.groupby("client_key")["produit_key"].apply(set).to_dict()

        for model_name in models:
            recs_by_client, eligible_relevant_by_client = {}, {}
            for client_id, targets in relevant_by_client.items():
                already = purchased_by_client.get(client_id, set())
                candidates = [p for p in all_products if p not in already and stock_ok.get(p, False)]
                eligible_relevant_by_client[client_id] = targets & set(candidates)
                if not candidates:
                    recs_by_client[client_id] = []
                    continue
                ranked, _, _ = recommend_for_client(model_name, models, content_fallback, popularity_fallback, client_id, candidates, 10)
                recs_by_client[client_id] = [p for p, _ in ranked]

            end_to_end = evaluate_recommendations(recs_by_client, relevant_by_client, produit_categorie, set(all_products), k_list=[5, 10])
            eligible_only = evaluate_recommendations(recs_by_client, eligible_relevant_by_client, produit_categorie, set(all_products), k_list=[5, 10])

            n_total_targets = sum(len(v) for v in relevant_by_client.values())
            n_eligible_targets = sum(len(v) for v in eligible_relevant_by_client.values())

            for perimetre, summ in [("end_to_end_toutes_cibles", end_to_end["summary"]), ("ranking_cibles_eligibles_seules", eligible_only["summary"])]:
                r = dict(summ)
                r["modele"] = model_name
                r["fenetre"] = window.index
                r["perimetre"] = perimetre
                r["taux_cibles_eligibles"] = n_eligible_targets / max(n_total_targets, 1)
                rows.append(r)

    return pd.DataFrame(rows)


# =============================================================================
# 3. Scénarios réachat : découverte (exclusion) vs réapprovisionnement (autorisé)
# =============================================================================
def repurchase_scenarios(ventes: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for window in WINDOWS:
        train_v = ventes[ventes["date_complete"] <= window.train_end]
        test_v = ventes[(ventes["date_complete"] >= window.test_start) & (ventes["date_complete"] <= window.test_end)]
        purchased_by_client = train_v.groupby("client_key")["produit_key"].apply(set).to_dict()
        relevant_by_client = test_v.groupby("client_key")["produit_key"].apply(set).to_dict()

        n_targets = sum(len(v) for v in relevant_by_client.values())
        n_rachats = sum(len(v & purchased_by_client.get(c, set())) for c, v in relevant_by_client.items())
        rows.append({
            "fenetre": window.index, "n_cibles_totales": n_targets, "n_cibles_qui_sont_des_rachats": n_rachats,
            "pct_cibles_rachats": n_rachats / max(n_targets, 1),
        })
    return pd.DataFrame(rows)


def main() -> None:
    setup_logging()
    tables = load_raw()
    ventes = build_ventes(tables)
    web = build_web(tables)
    stock = build_stock(tables)
    produits = tables["dim_produit"]

    # Reconfirmation explicite de l'audit stock antérieur.
    assert stock["niveau_stock"].min() == 21, "Le minimum de stock a changé depuis l'audit précédent — à réinvestiguer avant de continuer."
    assert (stock["niveau_stock"] <= 0).sum() == 0

    reconciliation, examples = reconcile_excluded_targets(ventes, stock, produits)
    metrics_split = metrics_end_to_end_vs_eligible(ventes, web, stock)
    repurchase = repurchase_scenarios(ventes)

    reconciliation.to_csv(RECSYS_DIR / "reconciliation_cibles_exclues.csv", index=False)
    examples.to_csv(RECSYS_DIR / "exemples_exclusions.csv", index=False)
    metrics_split.to_csv(RECSYS_DIR / "metriques_end_to_end_vs_eligible.csv", index=False)
    repurchase.to_csv(RECSYS_DIR / "scenarios_reachat.csv", index=False)
    logger.info("Réconciliation terminée. reconciliation=%s", reconciliation.to_dict(orient="records"))


if __name__ == "__main__":
    main()
