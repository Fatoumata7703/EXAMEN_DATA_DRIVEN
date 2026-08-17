import json
from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_forecast_bias_ratio_consistency_and_reference():
    data = json.loads((ROOT / "reports/advanced/forecast_bias_audit.json").read_text())
    direct30 = next(r for r in data["records"] if r["model"] == "LightGBM_direct_per_horizon" and r["horizon"] == 30)
    assert abs(direct30["forecast_actual_ratio"] - (1 + direct30["forecast_bias"])) < 1e-12
    assert abs(data["official_reference"]["wape30_six_windows"] - 0.2583140754237418) < 1e-12
    assert data["quality"]["zero_nan"] and data["quality"]["zero_negative"]


def test_bias_calibration_is_prior_window_only_and_not_globally_promoted():
    data = json.loads((ROOT / "reports/advanced/forecast_bias_audit.json").read_text())
    calibration = data["calibration_prior_windows_only"]
    assert calibration
    assert all(row["window"] >= 2 for row in calibration)
    assert not all(row["wape_not_degraded"] for row in calibration if row["model"] == "LightGBM_direct_per_horizon")
