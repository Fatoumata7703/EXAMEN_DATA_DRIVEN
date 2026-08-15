"""Tests de `src.pipelines.backtest_postprocess` — chaque scénario de repli
reproduit exactement, séparément.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.evaluation.metrics import wape
from src.pipelines.backtest_postprocess import WindowContext, classify_checkpoint


def _ctx(train_obs: dict[str, int], last: dict[str, float], mean: dict[str, float]) -> WindowContext:
    return WindowContext(
        index=1,
        cutoff=pd.Timestamp("2025-06-01"),
        train_observations=pd.Series(train_obs),
        last_value=pd.Series(last),
        mean_value=pd.Series(mean),
    )


def _raw(uid: str, model: str, y: float, y_pred_raw: float) -> pd.DataFrame:
    return pd.DataFrame({
        "unique_id": [uid], "ds": [pd.Timestamp("2025-06-02")],
        "y": [y], "y_pred_raw": [y_pred_raw], "modele": [model], "fenetre": [1],
    })


EMPTY_REPLI = pd.DataFrame(columns=["modele", "fenetre", "serie", "exception", "raison"])


# ---------------------------------------------------------------------------
# Cas B — produit sans historique
# ---------------------------------------------------------------------------
def test_produit_sans_historique_devient_cold_start_zero():
    ctx = _ctx({}, {}, {})  # "PNEW" absent des trois lookups -> train_observations=0
    df = _raw("PNEW", "AutoARIMA", y=3.0, y_pred_raw=2.5)
    out = classify_checkpoint(df, "AutoARIMA", 1, ctx, EMPTY_REPLI)
    row = out.iloc[0]
    assert row["train_observations"] == 0
    assert row["status"] == "cold_start_fallback"
    assert row["fallback_type"] == "cold_start_zero"
    assert row["fallback_reason"] == "produit_absent_du_train"
    assert row["model_effective"] == "ColdStartZero"
    assert row["y_pred_final"] == 0.0
    assert row["model_requested"] == "AutoARIMA"  # jamais écrasé


# ---------------------------------------------------------------------------
# Cas A — historique insuffisant, SeasonalNaive7
# ---------------------------------------------------------------------------
def test_seasonal_naive7_historique_1_jour():
    ctx = _ctx({"P1": 1}, {"P1": 4.0}, {"P1": 4.0})
    df = _raw("P1", "SeasonalNaive7", y=2.0, y_pred_raw=np.nan)
    out = classify_checkpoint(df, "SeasonalNaive7", 1, ctx, EMPTY_REPLI)
    row = out.iloc[0]
    assert row["status"] == "success_invalid_prediction_fallback"
    assert row["fallback_type"] == "historique_insuffisant"
    assert row["model_effective"] == "Naive"
    assert row["y_pred_final"] == 4.0  # dernière valeur connue
    assert row["model_requested"] == "SeasonalNaive7"


def test_seasonal_naive7_historique_5_jours():
    ctx = _ctx({"P1": 5}, {"P1": 7.0}, {"P1": 3.0})
    df = _raw("P1", "SeasonalNaive7", y=1.0, y_pred_raw=np.nan)
    out = classify_checkpoint(df, "SeasonalNaive7", 1, ctx, EMPTY_REPLI)
    row = out.iloc[0]
    assert row["fallback_type"] == "historique_insuffisant"
    assert row["model_effective"] == "Naive"  # < 7 obs -> Naive, jamais AvailableHistoryAverage
    assert row["y_pred_final"] == 7.0
    assert "n=5<7" in row["fallback_reason"]


def test_seasonal_naive7_avec_assez_dhistorique_nest_pas_un_repli():
    ctx = _ctx({"P1": 30}, {"P1": 9.0}, {"P1": 5.0})
    df = _raw("P1", "SeasonalNaive7", y=2.0, y_pred_raw=6.0)  # valeur finie, historique suffisant
    out = classify_checkpoint(df, "SeasonalNaive7", 1, ctx, EMPTY_REPLI)
    row = out.iloc[0]
    assert row["status"] == "success_valid_prediction"
    assert row["fallback_applied"] is np.False_ or row["fallback_applied"] is False
    assert row["model_effective"] == "SeasonalNaive7"
    assert row["y_pred_final"] == 6.0


# ---------------------------------------------------------------------------
# Cas A — historique insuffisant, WindowAverage28
# ---------------------------------------------------------------------------
def test_window_average28_historique_insuffisant_utilise_moyenne_disponible():
    ctx = _ctx({"P1": 10}, {"P1": 9.0}, {"P1": 3.5})
    df = _raw("P1", "WindowAverage28", y=4.0, y_pred_raw=np.nan)
    out = classify_checkpoint(df, "WindowAverage28", 1, ctx, EMPTY_REPLI)
    row = out.iloc[0]
    assert row["status"] == "success_invalid_prediction_fallback"
    assert row["fallback_type"] == "historique_insuffisant"
    assert row["model_effective"] == "AvailableHistoryAverage"  # PAS Naive
    assert row["y_pred_final"] == 3.5
    assert "n=10<28" in row["fallback_reason"]


def test_window_average28_moyenne_non_finie_replie_sur_naive():
    """Garde-fou : si même la moyenne disponible est non finie, repli Naive ultime."""
    ctx = _ctx({"P1": 3}, {"P1": 8.0}, {"P1": np.nan})
    df = _raw("P1", "WindowAverage28", y=1.0, y_pred_raw=np.nan)
    out = classify_checkpoint(df, "WindowAverage28", 1, ctx, EMPTY_REPLI)
    row = out.iloc[0]
    assert row["model_effective"] == "Naive"
    assert row["y_pred_final"] == 8.0
    assert "moyenne_non_finie" in row["fallback_reason"]


# ---------------------------------------------------------------------------
# Prévision non finie silencieuse — NaN et infinie
# ---------------------------------------------------------------------------
def test_prevision_nan_silencieuse_autre_modele():
    ctx = _ctx({"P1": 15}, {"P1": 6.0}, {"P1": 4.0})
    df = _raw("P1", "AutoETS", y=2.0, y_pred_raw=np.nan)
    out = classify_checkpoint(df, "AutoETS", 1, ctx, EMPTY_REPLI)
    row = out.iloc[0]
    assert row["model_effective"] == "Naive"
    assert row["y_pred_final"] == 6.0
    assert np.isfinite(row["y_pred_final"])


def test_prevision_infinie_est_traitee_comme_non_finie():
    ctx = _ctx({"P1": 15}, {"P1": 6.0}, {"P1": 4.0})
    df = _raw("P1", "AutoETS", y=2.0, y_pred_raw=np.inf)
    out = classify_checkpoint(df, "AutoETS", 1, ctx, EMPTY_REPLI)
    row = out.iloc[0]
    assert row["status"] == "success_invalid_prediction_fallback"
    assert row["model_effective"] == "Naive"
    assert np.isfinite(row["y_pred_final"])

    df_neg = _raw("P1", "AutoETS", y=2.0, y_pred_raw=-np.inf)
    out_neg = classify_checkpoint(df_neg, "AutoETS", 1, ctx, EMPTY_REPLI)
    assert np.isfinite(out_neg.iloc[0]["y_pred_final"])


# ---------------------------------------------------------------------------
# Repli budget / exception (déjà survenus pendant le calcul d'origine)
# ---------------------------------------------------------------------------
def test_repli_budget_est_reclassifie_sans_ecraser_model_requested():
    ctx = _ctx({"P1": 500}, {"P1": 5.0}, {"P1": 5.0})
    repli = pd.DataFrame([{
        "modele": "AutoARIMA", "fenetre": 1, "serie": "P1",
        "exception": None, "raison": "budget_temps_depasse",
    }])
    df = _raw("P1", "AutoARIMA", y=3.0, y_pred_raw=5.0)  # déjà rempli en Naive pendant le run d'origine
    out = classify_checkpoint(df, "AutoARIMA", 1, ctx, repli)
    row = out.iloc[0]
    assert row["status"] == "budget_fallback"
    assert row["fallback_type"] == "budget_fallback"
    assert row["model_effective"] == "Naive"
    assert row["model_requested"] == "AutoARIMA"  # jamais écrasé
    assert row["fallback_reason"] == "budget_temps_depasse"


def test_repli_exception_conserve_le_message_expurge():
    ctx = _ctx({"P1": 40}, {"P1": 2.0}, {"P1": 2.0})
    repli = pd.DataFrame([{
        "modele": "AutoETS", "fenetre": 1, "serie": "P1",
        "exception": "IndexError: too many indices", "raison": "exception_modele",
    }])
    df = _raw("P1", "AutoETS", y=1.0, y_pred_raw=2.0)
    out = classify_checkpoint(df, "AutoETS", 1, ctx, repli)
    row = out.iloc[0]
    assert row["status"] == "exception_fallback"
    assert row["model_effective"] == "Naive"
    assert "IndexError" in row["fallback_reason"]


# ---------------------------------------------------------------------------
# Métrique au dénominateur nul
# ---------------------------------------------------------------------------
def test_wape_avec_somme_reelle_nulle_est_nan_sans_lever():
    valeur = wape([0.0, 0.0, 0.0], [1.0, 0.0, 2.0])
    assert np.isnan(valeur)
