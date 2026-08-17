"""Diagnostic sans entraînement pour l'objectif WAPE15."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parents[2]
PRED = ROOT / "models/advanced/forecasting/direct_lightgbm_predictions.parquet"
RAW = ROOT / "data/processed/final/product_daily_forecasting.parquet"
FEATURES = ROOT / "data/cache/advanced_forecasting_features.parquet"
OUT = ROOT / "reports/advanced/wape15_diagnostic.json"


def wape(frame: pd.DataFrame) -> float:
    return float(frame.error.abs().sum() / max(frame.y.sum(), 1.0))


def main() -> int:
    pred = pd.read_parquet(PRED)
    raw = pd.read_parquet(RAW)
    features = pd.read_parquet(FEATURES)
    pred["ds"] = pd.to_datetime(pred.ds)
    raw["ds"] = pd.to_datetime(raw.ds)
    features["ds"] = pd.to_datetime(features.ds)
    pred["error"] = pred.pred - pred.y
    # The direct forecast is already the exact product × day target mapping.
    pred["y30"] = pred.y
    pred["e30"] = pred.error
    rows = []
    for window, group in pred.groupby("window"):
        origin = pd.Timestamp(group.origin.iloc[0])
        info = features[features.ds.eq(origin)][["produit_key", "categorie", "abc_a", "intermittent", "version_age_days"]].drop_duplicates("produit_key")
        g = group.merge(info, on="produit_key", how="left")
        product = g.groupby("produit_key", as_index=False).agg(y=("y30", "sum"), error=("e30", "sum"), categorie=("categorie", "first"), abc_a=("abc_a", "first"), intermittent=("intermittent", "first"), version_age_days=("version_age_days", "first"))
        product["abs_error"] = product.error.abs()
        product["wape_component"] = product.abs_error / max(product.y.sum(), 1.0)
        product = product.sort_values("abs_error", ascending=False)
        for segment, mask in {
            "ABC-A": product.abc_a.fillna(False).astype(bool),
            "ABC-B": ~product.abc_a.fillna(False).astype(bool),
            "intermittent": product.intermittent.fillna(False).astype(bool),
            "new_le_28d": product.version_age_days.fillna(999).le(28),
            "mature": product.version_age_days.fillna(999).gt(28),
        }.items():
            part = product.loc[mask]
            rows.append({"window": int(window), "segment": segment, "n_products": int(len(part)), "wape": wape(part), "error_contribution": float(part.abs_error.sum() / max(product.abs_error.sum(), 1.0)), "quantity_share": float(part.y.sum() / max(product.y.sum(), 1.0))})
        rows.append({"window": int(window), "segment": "all", "n_products": int(len(product)), "wape": wape(product), "error_contribution": 1.0, "quantity_share": 1.0})
        for category, part in product.groupby("categorie", dropna=False):
            rows.append({"window": int(window), "segment": f"category:{category}", "n_products": int(len(part)), "wape": wape(part), "error_contribution": float(part.abs_error.sum() / max(product.abs_error.sum(), 1.0)), "quantity_share": float(part.y.sum() / max(product.y.sum(), 1.0))})
        for n in (10, 20, 50):
            hard = product.head(n)
            rows.append({"window": int(window), "segment": f"hardest_{n}", "n_products": int(len(hard)), "wape": wape(hard), "error_contribution": float(hard.abs_error.sum() / max(product.abs_error.sum(), 1.0)), "quantity_share": float(hard.y.sum() / max(product.y.sum(), 1.0))})

    # Historical-only oracle: mean of positive demand and zero-rate from dates < origin.
    oracle_rows = []
    for window, group in pred.groupby("window"):
        origin = pd.Timestamp(group.origin.iloc[0])
        hist = raw[raw.ds < origin]
        stats = hist.groupby("produit_key").y.agg(mean="mean", positive_mean=lambda x: x[x.gt(0)].mean() if x.gt(0).any() else 0.0, zero_rate=lambda x: (x.eq(0)).mean(), active_days=lambda x: x.gt(0).sum())
        test = group.groupby("produit_key").y.sum().rename("y30").to_frame().join(stats)
        # Expected 30-day demand from historical mean; no future information.
        test["oracle"] = test["mean"].fillna(0) * 30
        test["error"] = test.oracle - test.y30
        oracle_rows.append({"window": int(window), "wape": float(test.error.abs().sum() / max(test.y30.sum(), 1.0)), "n_products": int(len(test))})

    payload = {
        "reference_locked": {"model": "LightGBM_direct_per_horizon", "wape30": 0.2583140754237418, "grain": "produit×fenêtre", "windows": 6, "population_unchanged": True},
        "diagnostic": rows,
        "historical_only_oracle": oracle_rows,
        "attainability": {"target_wape30": 0.15, "reference_gap_absolute": 0.1083140754, "reference_gap_relative": 0.4194, "interpretation": "objectif très ambitieux ; le diagnostic doit précéder toute optimisation et ne justifie aucune réduction de population"},
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"reference": payload["reference_locked"], "oracle": oracle_rows}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
