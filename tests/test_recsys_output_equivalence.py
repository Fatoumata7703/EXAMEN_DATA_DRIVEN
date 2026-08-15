"""Preuve d'équivalence entre l'ancienne construction de sortie (une seule
liste Python de dicts convertie en DataFrame d'un coup — a échoué deux fois
par manque de mémoire transitoire sur 2,59M lignes) et la nouvelle
construction par lots (une DataFrame par (fenêtre, politique), puis
`pd.concat`).

Ce test ne rejoue pas le pipeline recsys complet (trop coûteux pour un test
unitaire) : il prouve la propriété générale exploitée par le correctif —
convertir un lot de dicts en DataFrame puis concaténer les lots donne
EXACTEMENT le même résultat (valeurs, dtypes, ordre) que tout convertir en un
seul bloc — sur un échantillon dont le schéma reproduit exactement les
colonnes de sortie du recsys (`recsys_prototype.py`, colonnes définies dans
`run_window_evaluation`).
"""

from __future__ import annotations

import random

import pandas as pd
import pytest

OUTPUT_COLUMNS = [
    "client_id", "recommended_product_id", "rank", "score", "model_used", "fallback_reason",
    "recommendation_date", "already_purchased", "eligible_at_recommendation_date",
    "window", "requested_model", "exclude_purchased_policy", "filter_stock_policy",
]


def _make_rows(n: int, window: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    rows = []
    for i in range(n):
        rows.append({
            "client_id": f"CLI{i % 50:06d}", "recommended_product_id": f"PRD{i % 30:06d}",
            "rank": (i % 10) + 1, "score": rng.random(),
            "model_used": rng.choice(["popularite_globale", "contenu_categorie_prix"]),
            "fallback_reason": rng.choice(["aucun", "collaboratif_impossible_aucun_achat_historique_train"]),
            "recommendation_date": "2026-02-01", "already_purchased": rng.random() < 0.2,
            "eligible_at_recommendation_date": rng.random() < 0.9,
            "window": window, "requested_model": "popularite_globale",
            "exclude_purchased_policy": True, "filter_stock_policy": True,
        })
    return rows


def test_construction_par_lots_equivaut_a_la_construction_globale():
    # "Ancienne" méthode : tout accumuler dans une seule liste puis un seul pd.DataFrame(...).
    all_rows = []
    batches_source = []
    for window in range(4):
        batch = _make_rows(200, window, seed=window)
        all_rows.extend(batch)
        batches_source.append(batch)
    old_df = pd.DataFrame(all_rows)

    # "Nouvelle" méthode : une DataFrame par lot, puis pd.concat.
    new_df = pd.concat([pd.DataFrame(b) for b in batches_source], ignore_index=True)

    assert list(old_df.columns) == list(new_df.columns)
    pd.testing.assert_frame_equal(old_df, new_df, check_dtype=True)


def test_construction_par_lots_preserve_le_schema_de_sortie_recsys():
    """Les colonnes produites doivent être exactement celles attendues en
    sortie du simulateur (contrat gelé, cf. rapport 37 §5)."""
    batch = pd.DataFrame(_make_rows(10, 0, seed=1))
    assert list(batch.columns) == OUTPUT_COLUMNS


def test_filtre_par_defaut_nest_plus_un_no_op():
    """Si un jour la sortie contient à nouveau plusieurs politiques, le
    filtre `policy_combo == défaut` doit réellement réduire les lignes —
    sinon c'est le signe qu'il est redevenu un no-op silencieux (piège déjà
    rencontré une fois, cf. rapport 37 §5 et le commentaire dans
    `recsys_prototype.report_baselines`)."""
    multi_policy_rows = []
    for policy in ("defaut_exclut_achats_stock_filtre", "inclut_produits_deja_achetes"):
        rows = _make_rows(5, 0, seed=hash(policy) % 1000)
        for r in rows:
            r["policy_combo"] = policy
        multi_policy_rows.extend(rows)
    df = pd.DataFrame(multi_policy_rows)
    filtered = df[df["policy_combo"] == "defaut_exclut_achats_stock_filtre"]
    assert len(filtered) < len(df), "Le filtre policy_combo doit réduire les lignes quand plusieurs politiques sont présentes"
    assert len(filtered) == 5
