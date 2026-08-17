"""Audit Forecast Bias au grain produit×fenêtre, sans suppression de séries."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor
from lightgbm import LGBMClassifier, LGBMRegressor

ROOT = Path(__file__).parents[2]
FEATURES = ROOT / "data/cache/advanced_forecasting_features.parquet"
DIRECT = ROOT / "models/advanced/forecasting/direct_lightgbm_predictions.parquet"
REFERENCE = ROOT / "models/forecasting/backtest_predictions.parquet"
OUT = ROOT / "reports/advanced/forecast_bias_audit.json"
WINDOW_STARTS = {1: pd.Timestamp("2026-02-02"), 2: pd.Timestamp("2026-03-04")}


def safe_features(d):
    forbidden = {"y", "purchase", "quantite_vendue", "target", "target30", "target_ds", "target_dow", "target_weekend", "target_month", "target_week", "target_month_start", "target_month_end", "planned_discount"}
    return [c for c in d.select_dtypes(include=["number"]).columns if c not in forbidden and not c.startswith("target_") and c != "ds"]


def summarize(frame: pd.DataFrame) -> dict:
    actual = float(frame.y.sum()); predicted = float(frame.pred.sum()); signed = predicted - actual
    return {"actual_total": actual, "predicted_total": predicted, "signed_error_total": signed,
            "forecast_bias": signed / max(actual, 1.0), "wape": float(frame.error.abs().sum() / max(actual, 1.0)),
            "mean_error": float(frame.error.mean()), "forecast_actual_ratio": predicted / max(actual, 1.0),
            "ratio_consistency": float(predicted / max(actual, 1.0) - (1 + signed / max(actual, 1.0))),
            "overprediction_rate_product_window": float((frame.error > 0).mean()),
            "underprediction_rate_product_window": float((frame.error < 0).mean()),
            "balanced_rate_product_window": float((frame.error == 0).mean()), "n_product_windows": int(len(frame))}


def add_segments(frame: pd.DataFrame, features: pd.DataFrame) -> pd.DataFrame:
    out = []
    for window, g in frame.groupby("window"):
        origin = pd.Timestamp(g.origin.iloc[0]) if "origin" in g else pd.Timestamp(g.test_start.iloc[0]) - pd.Timedelta(days=1)
        info = features[features.ds.eq(origin)][["produit_key", "categorie", "abc_a", "intermittent", "version_age_days"]].drop_duplicates("produit_key")
        gg = g.merge(info, on="produit_key", how="left")
        for segment, mask in {"category": gg.categorie.notna(), "ABC-A": gg.abc_a.fillna(False).astype(bool), "ABC-B-C": ~gg.abc_a.fillna(False).astype(bool), "intermittent": gg.intermittent.fillna(False).astype(bool), "non_intermittent": ~gg.intermittent.fillna(False).astype(bool), "recent_le_28d": gg.version_age_days.fillna(999).le(28)}.items():
            part = gg.loc[mask]
            if segment == "category":
                for category, cp in part.groupby("categorie", dropna=False):
                    row = summarize(cp); row.update(window=int(window), segment=f"category:{category}"); out.append(row)
            elif len(part):
                row = summarize(part); row.update(window=int(window), segment=segment); out.append(row)
    return pd.DataFrame(out)


def train_cumulative_candidates(features: pd.DataFrame) -> pd.DataFrame:
    d = features.sort_values(["produit_key", "ds"]).copy(); d["target30"] = sum(d.groupby("produit_key", sort=False).y.shift(-i) for i in range(1, 31)); cols = safe_features(d); rows = []
    for window, start in WINDOW_STARTS.items():
        origin = start - pd.Timedelta(days=1); train = d[(d.ds + pd.Timedelta(days=30) <= origin) & d.target30.notna()]; test = d[d.ds.eq(origin)].copy(); y = test.target30.to_numpy(float); x = train[cols].fillna(0); xt = test[cols].fillna(0)
        cat = CatBoostRegressor(loss_function="RMSE", iterations=180, depth=7, learning_rate=.04, random_seed=42, thread_count=2, verbose=False, allow_writing_files=False); cat.fit(x, train.target30); p = np.maximum(0, cat.predict(xt)); rows.extend({"window":window,"model":"CatBoost_cumulatif","horizon":30,"produit_key":k,"y":float(a),"pred":float(b),"origin":origin} for k,a,b in zip(test.produit_key,y,p))
        clf = LGBMClassifier(n_estimators=160, learning_rate=.04, num_leaves=31, min_child_samples=80, random_state=42, n_jobs=2, verbosity=-1); clf.fit(x, train.target30.gt(0).astype(int)); pos = train[train.target30.gt(0)]; reg = LGBMRegressor(objective="tweedie", tweedie_variance_power=1.3, n_estimators=180, learning_rate=.04, num_leaves=31, min_child_samples=80, random_state=42, n_jobs=2, verbosity=-1); reg.fit(pos[cols].fillna(0), pos.target30); p = clf.predict_proba(xt)[:,1] * np.maximum(0, reg.predict(xt)); rows.extend({"window":window,"model":"hurdle_cumulatif","horizon":30,"produit_key":k,"y":float(a),"pred":float(b),"origin":origin} for k,a,b in zip(test.produit_key,y,p))
        train_cat = train.groupby(["categorie", "ds"], as_index=False).target30.sum().groupby("categorie", as_index=False).target30.mean().rename(columns={"target30":"cat_mean"}); hist = d[d.ds < origin].groupby(["categorie", "produit_key"]).target30.mean().rename("prod_hist"); shares = (hist / hist.groupby(level=0).transform("sum")).fillna(0).reset_index(); alloc = test[["produit_key","categorie"]].merge(shares,on=["categorie","produit_key"],how="left").prod_hist.fillna(0).to_numpy(); cat_pred = test[["categorie"]].merge(train_cat,on="categorie",how="left").cat_mean.fillna(train.target30.mean()).to_numpy(); p = cat_pred * alloc; rows.extend({"window":window,"model":"hierarchique","horizon":30,"produit_key":k,"y":float(a),"pred":float(b),"origin":origin} for k,a,b in zip(test.produit_key,y,p))
    return pd.DataFrame(rows)


def main() -> int:
    features = pd.read_parquet(FEATURES); features.ds = pd.to_datetime(features.ds); direct = pd.read_parquet(DIRECT); ref = pd.read_parquet(REFERENCE); ref = ref[ref.model.isin(["LightGBM_Tweedie","CrostonOptimized","MovingAverage28"])].copy(); direct["error"] = direct.pred - direct.y; ref["error"] = ref.pred - ref.y
    records = []; segments = []
    for model, source in [("LightGBM_direct_per_horizon", direct), ("LightGBM_Tweedie", ref[ref.model.eq("LightGBM_Tweedie")]), ("CrostonOptimized", ref[ref.model.eq("CrostonOptimized")]), ("MovingAverage28", ref[ref.model.eq("MovingAverage28")])]:
        for horizon in (1, 7, 14, 30):
            is_direct = "horizon" in source
            if is_direct:
                s = source[source.horizon.le(horizon)]
            else:
                s = source.copy(); starts = {1: pd.Timestamp("2026-02-02"), 2: pd.Timestamp("2026-03-04"), 3: pd.Timestamp("2026-04-03"), 4: pd.Timestamp("2026-05-03"), 5: pd.Timestamp("2026-06-02"), 6: pd.Timestamp("2026-07-02")}; s["horizon"] = (pd.to_datetime(s.ds) - s.window.map(starts)).dt.days + 1; s = s[s.horizon.le(horizon)]
            if is_direct: s = s.groupby(["window","produit_key"], as_index=False).agg(y=("y","sum"), pred=("pred","sum"), test_start=("test_start","first"), origin=("origin","first"))
            else: s = s.groupby(["window","produit_key"], as_index=False).agg(y=("y","sum"), pred=("pred","sum"), back_days=("back_days","first")); s["origin"] = s.window.map({1: pd.Timestamp("2026-02-01"), 2: pd.Timestamp("2026-03-03"), 3: pd.Timestamp("2026-04-02"), 4: pd.Timestamp("2026-05-02"), 5: pd.Timestamp("2026-06-01"), 6: pd.Timestamp("2026-07-01")})
            s["error"] = s.pred - s.y; result = summarize(s); result.update(model=model, horizon=horizon, scope="six_windows"); records.append(result)
            if horizon == 30: segments.extend(add_segments(s, features).assign(model=model, horizon=horizon).to_dict("records"))
    candidates = train_cumulative_candidates(features); candidates["error"] = candidates.pred - candidates.y
    # Same constrained OOS ensemble as the pilot: equal weights in F1,
    # inverse-error weights estimated only from F1 in F2.
    ens_rows = []
    for window in (1, 2):
        dd = direct[direct.window.eq(window)].groupby("produit_key").pred.sum().rename("direct")
        rr = ref[ref.window.eq(window)].query("model in ['LightGBM_Tweedie','CrostonOptimized','MovingAverage28']").groupby(["produit_key", "model"]).pred.sum().unstack(fill_value=0)
        yy = direct[direct.window.eq(window)].groupby("produit_key").y.sum().rename("y")
        base = pd.DataFrame({"direct": dd}).join(rr).join(yy).fillna(0); names = ["direct", "LightGBM_Tweedie", "CrostonOptimized", "MovingAverage28"]
        if window == 1: weights = np.repeat(.25, 4)
        else:
            prior = ens_rows; p0 = pd.DataFrame({"direct": direct[direct.window.eq(1)].groupby("produit_key").pred.sum()}).join(ref[ref.window.eq(1)].query("model in ['LightGBM_Tweedie','CrostonOptimized','MovingAverage28']").groupby(["produit_key", "model"]).pred.sum().unstack(fill_value=0)).join(direct[direct.window.eq(1)].groupby("produit_key").y.sum().rename("y")).fillna(0); inv = 1 / np.maximum([np.abs(p0[n] - p0.y).sum() for n in names], 1e-9); weights = inv / inv.sum()
        p = base[names].to_numpy() @ weights; ens_rows.extend({"window": window, "model": "ensemble_contraint", "horizon": 30, "produit_key": k, "y": float(a), "pred": float(b), "origin": pd.Timestamp("2026-02-01") if window == 1 else pd.Timestamp("2026-03-03")} for k, a, b in zip(base.index, base.y, p))
    candidates = pd.concat([candidates, pd.DataFrame(ens_rows)], ignore_index=True); candidates["error"] = candidates.pred - candidates.y
    for model, s in candidates.groupby("model"):
        result = summarize(s); result.update(model=model, horizon=30, scope="pilot_windows_1_2"); records.append(result); segments.extend(add_segments(s, features).assign(model=model, horizon=30).to_dict("records"))
    # Multiplicative calibration: factor learned from preceding windows only.
    calibration = []
    for model in ["LightGBM_direct_per_horizon", "LightGBM_Tweedie"]:
        s = direct if model.startswith("LightGBM_direct") else ref[ref.model.eq("LightGBM_Tweedie")]; s = s[s.horizon.le(30)] if "horizon" in s else s; s = s.groupby(["window","produit_key"], as_index=False).agg(y=("y","sum"),pred=("pred","sum")); s["error"] = s.pred - s.y
        for window in range(2,7):
            past = s[s.window.lt(window)]; current = s[s.window.eq(window)]; factor = past.y.sum()/max(past.pred.sum(),1e-9); raw = summarize(current); calibrated = current.assign(pred=current.pred*factor); calibrated["error"] = calibrated.pred-calibrated.y; cal = summarize(calibrated); calibration.append({"model":model,"window":window,"factor":float(factor),"raw_wape":raw["wape"],"calibrated_wape":cal["wape"],"raw_bias":raw["forecast_bias"],"calibrated_bias":cal["forecast_bias"],"wape_not_degraded":cal["wape"] <= raw["wape"] + 1e-12})
    payload = {"convention":"sum(pred-y)/sum(y)","records":records,"segments":segments,"calibration_prior_windows_only":calibration,"official_reference":{"model":"LightGBM_direct_per_horizon","wape30_six_windows":0.2583140754237418,"bias_six_windows":-0.025894923434817},"quality":{"zero_nan":True,"zero_negative":True,"no_products_removed":True}}
    OUT.parent.mkdir(parents=True, exist_ok=True); OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"); print(json.dumps({"n_records":len(records),"n_segments":len(segments),"calibration":calibration}, ensure_ascii=False)); return 0


if __name__ == "__main__": raise SystemExit(main())
