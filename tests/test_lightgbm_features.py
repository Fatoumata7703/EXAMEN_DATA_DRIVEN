"""Tests des features LightGBM — construction statique (`_rolling_features`,
`build_training_matrix`).

Réécrit le 2026-08-14 : l'ancienne fonction `build_features` (qui opérait sur
train+test concaténés) a été remplacée par une architecture récursive sans
fuite (`src/pipelines/backtest_lightgbm.py`). Ces tests couvrent la
construction *statique* des lags/rolling ; la preuve de non-fuite sur la
boucle complète à 30 jours est dans `test_lightgbm_recursive_no_leakage.py`
— les deux niveaux sont nécessaires (l'un ne remplace pas l'autre).
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.pipelines.backtest_lightgbm import _rolling_features, build_training_matrix


@pytest.fixture
def table() -> pd.DataFrame:
    dates = pd.date_range("2025-01-01", periods=70, freq="D")
    return pd.DataFrame(
        {
            "unique_id": "P1",
            "ds": dates,
            "y": range(1, 71),  # strictement croissant : idéal pour détecter une fuite
            "categorie": "Maison",
            "marque": "A",
        }
    )


def test_lag_1_ne_contient_jamais_y_du_jour(table):
    feats = _rolling_features(table["y"], table["unique_id"])
    decale = table["y"].shift(1)
    pd.testing.assert_series_equal(feats["lag_1"], decale, check_names=False)


def test_rolling_mean_exclut_le_jour_courant(table):
    feats = _rolling_features(table["y"], table["unique_id"])
    idx = 40
    attendu = table["y"].iloc[idx - 7 : idx].mean()
    assert feats["roll_mean_7"].iloc[idx] == pytest.approx(attendu)
    biaisee = table["y"].iloc[idx - 6 : idx + 1].mean()  # inclurait le jour courant : faux
    assert feats["roll_mean_7"].iloc[idx] != pytest.approx(biaisee)


def test_diff_lag_utilise_des_valeurs_decalees(table):
    feats = _rolling_features(table["y"], table["unique_id"])
    idx = 60
    attendu = table["y"].iloc[idx - 1] - table["y"].iloc[idx - 1 - 7]
    assert feats["diff_7"].iloc[idx] == pytest.approx(attendu)


def test_perturber_une_valeur_future_ne_change_jamais_les_features_passees(table):
    feats_a = _rolling_features(table["y"], table["unique_id"])
    perturbee = table.copy()
    perturbee.loc[perturbee["ds"] == perturbee["ds"].max(), "y"] = 99999.0
    feats_b = _rolling_features(perturbee["y"], perturbee["unique_id"])

    avant_derniere = table.index[table["ds"] < table["ds"].max()]
    for name in feats_a:
        pd.testing.assert_series_equal(
            feats_a[name].loc[avant_derniere].reset_index(drop=True),
            feats_b[name].loc[avant_derniere].reset_index(drop=True),
            check_names=False,
        )


def test_build_training_matrix_ne_depasse_jamais_le_train_fourni(table):
    mat = build_training_matrix(table)
    assert mat["ds"].max() <= table["ds"].max()
    assert mat["ds"].min() >= table["ds"].min()


def test_build_training_matrix_supprime_les_lignes_a_historique_insuffisant(table):
    """Les 56 premiers jours n'ont pas assez d'historique pour `lag_56` : ils
    doivent être exclus, pas remplis avec du NaN silencieux."""
    mat = build_training_matrix(table)
    assert mat["lag_56"].notna().all()
    assert len(mat) == len(table) - 56


def test_plusieurs_produits_restent_independants():
    dates = pd.date_range("2025-01-01", periods=10, freq="D")
    df = pd.concat([
        pd.DataFrame({"unique_id": "A", "ds": dates, "y": range(10)}),
        pd.DataFrame({"unique_id": "B", "ds": dates, "y": range(100, 110)}),
    ], ignore_index=True)
    feats = _rolling_features(df["y"], df["unique_id"])
    a_lag1 = feats["lag_1"][df["unique_id"] == "A"].reset_index(drop=True)
    b_lag1 = feats["lag_1"][df["unique_id"] == "B"].reset_index(drop=True)
    assert a_lag1.iloc[1] == 0  # y(A, jour0)
    assert b_lag1.iloc[1] == 100  # y(B, jour0), jamais contaminé par A
