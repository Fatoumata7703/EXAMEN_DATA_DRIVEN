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
    assert meta["candidate_gate_ge_050"] is False
    assert meta["lambda_rank_started"] is False
    assert meta["f1_diagnostic"]["train_orders"] == 0
    assert meta["f1_diagnostic"]["mean_candidates"] == 0.0


def test_complement_union_reproduces_f1_zero_regression():
    meta = json.loads((OUT / "complement_candidate_metadata.json").read_text(encoding="utf-8"))
    assert meta["union_recall_at50"][0] == 0.0
    assert min(meta["union_recall_at50"]) == 0.0
