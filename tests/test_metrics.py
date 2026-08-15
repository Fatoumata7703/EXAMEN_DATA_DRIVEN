"""Tests des métriques d'évaluation."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.evaluation import metrics as m


def test_perfect_forecast_gives_zero_error():
    y = [1.0, 5.0, 0.0, 3.0]
    assert m.mae(y, y) == 0.0
    assert m.rmse(y, y) == 0.0
    assert m.wape(y, y) == 0.0
    assert m.smape(y, y) == 0.0
    assert m.bias(y, y) == 0.0


def test_wape_is_volume_weighted():
    # Une erreur de 2 sur un volume total de 10 => WAPE = 0.2
    y_true = [4.0, 6.0]
    y_pred = [4.0, 8.0]
    assert m.wape(y_true, y_pred) == pytest.approx(0.2)


def test_smape_handles_zeros_without_exploding():
    y_true = [0.0, 0.0, 10.0]
    y_pred = [0.0, 5.0, 10.0]
    value = m.smape(y_true, y_pred)
    assert np.isfinite(value)
    assert 0 <= value <= 2


def test_mape_positive_only_ignores_zero_actuals():
    y_true = [0.0, 10.0]
    y_pred = [5.0, 11.0]
    # Seul le second point compte : |11-10|/10 = 0.1
    assert m.mape_positive_only(y_true, y_pred) == pytest.approx(0.1)


def test_bias_sign_convention():
    assert m.bias([10.0], [12.0]) > 0  # sur-prévision
    assert m.bias([10.0], [8.0]) < 0   # sous-prévision


def test_under_forecast_rate():
    assert m.under_forecast_rate([10, 10, 10], [9, 11, 10]) == pytest.approx(1 / 3)


def test_mase_uses_training_scale():
    # Entraînement : série alternée, naive1 MAE = 2
    y_train = [1.0, 3.0, 1.0, 3.0, 1.0]
    scale = m.naive_scale(y_train, seasonality=1)
    assert scale == pytest.approx(2.0)
    # Test : erreur absolue moyenne = 1 => MASE = 0.5
    value = m.mase([2.0, 2.0], [3.0, 1.0], y_train, seasonality=1)
    assert value == pytest.approx(0.5)


def test_mase_is_nan_when_scale_undefined():
    # Série constante : la naïve a une erreur nulle, MASE non définie
    assert np.isnan(m.mase([1.0], [2.0], [5.0, 5.0, 5.0], seasonality=1))


def test_wape_nan_when_no_volume():
    assert np.isnan(m.wape([0.0, 0.0], [1.0, 1.0]))


def test_metrics_by_group_returns_one_row_per_group():
    df = pd.DataFrame(
        {
            "unique_id": ["a", "a", "b", "b"],
            "y": [10.0, 12.0, 1.0, 0.0],
            "y_pred": [9.0, 13.0, 1.0, 1.0],
        }
    )
    out = m.metrics_by_group(df, ["unique_id"])
    assert len(out) == 2
    assert set(out["unique_id"]) == {"a", "b"}
    assert out.loc[out["unique_id"] == "a", "MAE"].iloc[0] == pytest.approx(1.0)


def test_compute_all_metrics_keys():
    out = m.compute_all_metrics([1.0, 2.0], [1.0, 3.0], y_train=[1.0, 2.0, 3.0, 4.0], seasonality=1)
    for key in ("MAE", "RMSE", "WAPE", "sMAPE", "biais", "taux_sous_prevision", "MASE"):
        assert key in out


# ---------------------------------------------------------------------------
# Nouvelles métriques : RMSSE, coût asymétrique
# ---------------------------------------------------------------------------
def test_rmsse_uses_training_scale():
    y_train = [1.0, 3.0, 1.0, 3.0, 1.0]  # naive1 : diffs alternent +-2 -> RMSE=2
    scale = m.naive_scale_squared(y_train, seasonality=1)
    assert scale == pytest.approx(2.0)
    value = m.rmsse([2.0, 2.0], [4.0, 0.0], y_train, seasonality=1)  # RMSE test = 2
    assert value == pytest.approx(1.0)


def test_rmsse_nan_when_scale_undefined():
    assert np.isnan(m.rmsse([1.0], [2.0], [5.0, 5.0, 5.0], seasonality=1))


def test_asymmetric_cost_penalizes_underforecast_more():
    # Sous-prévision de 10 : cout = 10*1.5=15 ; sur-prévision de 10 : cout = 10.
    under = m.asymmetric_cost([10.0], [0.0], under_weight=1.5)
    over = m.asymmetric_cost([0.0], [10.0], under_weight=1.5)
    assert under == pytest.approx(15.0)
    assert over == pytest.approx(10.0)
    assert under > over


def test_asymmetric_cost_zero_on_perfect_forecast():
    assert m.asymmetric_cost([1.0, 2.0, 3.0], [1.0, 2.0, 3.0], 2.0) == 0.0


def test_compute_all_metrics_includes_new_keys():
    out = m.compute_all_metrics([1.0, 2.0], [1.0, 3.0], y_train=[1.0, 2.0, 3.0, 4.0], seasonality=1)
    for key in ("RMSSE", "cout_asymetrique_1_5x", "cout_asymetrique_2x"):
        assert key in out
