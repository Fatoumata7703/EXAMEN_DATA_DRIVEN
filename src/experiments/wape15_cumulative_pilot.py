"""Pilote direct y_7d/y_14d/y_30d sur fenêtres 1-2, sans feature future."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor

ROOT = Path(__file__).parents[2]
DATA = ROOT / "data/processed/final/product_daily_forecasting.parquet"
FEATURES = ROOT / "data/cache/advanced_forecasting_features.parquet"
OUT = ROOT / "reports/advanced/wape15_pilot.json"
WINDOW_STARTS = {1: pd.Timestamp("2026-02-02"), 2: pd.Timestamp("2026-03-04")}


def make_targets(d: pd.DataFrame, horizon: int) -> pd.Series:
    g = d.groupby("produit_key", sort=False).y
    return sum(g.shift(-i) for i in range(1, horizon + 1))


def score(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.abs(p - y).sum() / max(y.sum(), 1.0))


def main() -> int:
    d = pd.read_parquet(FEATURES).sort_values(["produit_key", "ds"]).copy()
    d["ds"] = pd.to_datetime(d.ds)
    # Only cutoff-known numeric features; deliberately remove all target/future fields.
    forbidden = {"y", "purchase", "quantite_vendue", "target", "target_ds", "target_dow", "target_weekend", "target_month", "target_week", "target_month_start", "target_month_end", "planned_discount"}
    features = [c for c in d.select_dtypes(include=["number"]).columns if c not in forbidden and not c.startswith("target_")]
    features = [c for c in features if c not in {"ds"}]
    rows = []
    for window, test_start in WINDOW_STARTS.items():
        train_end = test_start - pd.Timedelta(days=1)
        origin = train_end
        test = d[d.ds.eq(origin)].copy()
        for horizon in (7, 14, 30):
            target = make_targets(d, horizon)
            frame = d.assign(target_cum=target, target_end=d.ds + pd.Timedelta(days=horizon))
            train = frame[(frame.target_end <= train_end) & frame.target_cum.notna()]
            train_x = train[features].replace([np.inf, -np.inf], np.nan).fillna(0)
            test_x = test[features].replace([np.inf, -np.inf], np.nan).fillna(0)
            test_y = frame.loc[test.index, "target_cum"].to_numpy(float)
            for model_name, params in {
                "LightGBM_Tweedie_cum": {"objective": "tweedie", "tweedie_variance_power": 1.3},
                "LightGBM_Poisson_cum": {"objective": "poisson"},
                "LightGBM_L1_cum": {"objective": "regression_l1"},
            }.items():
                model = LGBMRegressor(n_estimators=180, learning_rate=.04, num_leaves=31, min_child_samples=80, random_state=42, n_jobs=2, verbosity=-1, **params)
                model.fit(train_x, train.target_cum)
                pred = np.maximum(0, model.predict(test_x))
                rows.append({"window": window, "horizon": horizon, "model": model_name, "wape": score(test_y, pred), "bias": float((pred - test_y).sum() / max(test_y.sum(), 1.0)), "n_products": int(len(test_y)), "features": len(features), "future_features_excluded": True})
    payload = {"pilot_windows": [1, 2], "target_grain": "produit×fenêtre", "target_definition": "sum confirmed y J+1..J+h", "features": features, "rows": rows, "reference_wape30": 0.2583140754237418, "five_percent_gate": 0.2453983716525547}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
