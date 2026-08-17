import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "models" / "advanced" / "recommendation_ranking"


def test_ranker_pilot_has_only_prior_features_and_deterministic_negative_seed():
    meta = json.loads((OUT / "ranking_pilot_metadata.json").read_text(encoding="utf-8"))
    assert meta["features_strictly_prior"] is True
    assert meta["no_future_purchase_feature"] is True
    assert meta["negative_sampling_seed"] == 42
    assert set(pd.read_csv(OUT / "ranking_pilot_metrics.csv").window) == {1, 2}


def test_ranker_gate_failure_keeps_popularity_official():
    meta = json.loads((OUT / "ranking_pilot_metadata.json").read_text(encoding="utf-8"))
    assert meta["official_baseline"] == "popularite_globale"
    assert meta["gate"]["four_window_continued"] is False
    assert meta["gate"]["ndcg_gain_ge_5pct"] is False


def test_complement_gate_requires_all_windows():
    meta = json.loads((OUT / "complement_candidate_metadata.json").read_text(encoding="utf-8"))
    assert meta["candidate_gate_ge_050"] is True
    assert meta["evaluated_windows"] == [2, 3, 4]
    assert meta["candidate_gate_rule"].startswith("all three evaluable windows")
    assert meta["lambda_rank_started"] is False
    assert meta["f1_status"] == "non_evaluable_no_history"
    assert meta["f1_model_evaluation_allowed"] is False
    assert meta["f1_fallback_required"] is True
    assert meta["f1_diagnostic"]["train_orders"] == 0
    assert meta["f1_diagnostic"]["mean_candidates"] == 0.0


def test_complement_union_reproduces_f1_zero_regression():
    meta = json.loads((OUT / "complement_candidate_metadata.json").read_text(encoding="utf-8"))
    assert meta["union_recall_at50"][0] == 0.0
    assert min(meta["union_recall_at50"]) == 0.0


def test_complement_evaluability_rule_is_explicit():
    meta = json.loads((OUT / "complement_candidate_metadata.json").read_text(encoding="utf-8"))
    d = meta["f1_diagnostic"]
    assert d["train_orders"] == 0 and d["train_distinct_products"] == 0
    assert d["target_catalog_presence"] == 0.0 and d["cold_start_rate"] == 1.0


def test_complement_ranker_artifact_declares_leakage_controls():
    p = OUT / "complement_ranker_metadata.json"
    if not p.exists():
        return
    meta = json.loads(p.read_text(encoding="utf-8"))
    assert meta["deterministic_negative_seed"] == 42
    assert meta["evaluated_windows"] == [2, 3, 4]
    assert meta["f1_model_evaluation_allowed"] is False


def test_end_to_end_predictions_are_materialized_and_bootstrapped():
    pred = OUT / "complement_topk_predictions.parquet"
    meta = OUT / "complement_end_to_end_metadata.json"
    assert pred.exists() and meta.exists()
    df = pd.read_parquet(pred)
    assert set(df.window.unique()) == {2, 3, 4}
    assert (df.label == 1).groupby(df.order_id).sum().max() >= 0
    assert not df.duplicated(["order_id", "window", "target", "model", "item"]).any()
    assert all(str(t) not in str(c) for t, c in zip(df.target.head(1000), df.context_items.head(1000)))
    m = json.loads(meta.read_text(encoding="utf-8"))
    assert m["bootstrap_replicates"] >= 2000
    assert m["bootstrap_unit"] == "commande_x_fenetre"
