import json
from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_stretch_reference_and_population_are_locked():
    data = json.loads((ROOT / "reports/advanced/wape15_diagnostic.json").read_text())
    ref = data["reference_locked"]
    assert ref["model"] == "LightGBM_direct_per_horizon"
    assert ref["wape30"] == 0.2583140754237418
    assert ref["grain"].startswith("produit") and "fen" in ref["grain"]
    assert ref["windows"] == 6
    assert ref["population_unchanged"] is True


def test_pilot_does_not_pass_five_percent_gate():
    data = json.loads((ROOT / "reports/advanced/wape15_pilot.json").read_text())
    h30 = [row["wape"] for row in data["rows"] if row["horizon"] == 30]
    assert min(h30) > data["five_percent_gate"]
    assert all(row["future_features_excluded"] for row in data["rows"])


def test_four_candidate_gates_are_independent_and_all_fail():
    data = json.loads((ROOT / "reports/advanced/wape15_four_candidates.json").read_text())
    candidates = {row["candidate"] for row in data["rows"]}
    assert candidates == {"CatBoost_direct_y30", "hurdle_cum30", "hierarchical_category_to_product", "ensemble_constrained_oos"}
    assert data["all_candidates_pass"] is False
    assert all(not row["gate_pass"] for row in data["rows"])
    assert all(row["future_features_excluded"] for row in data["rows"])


def test_pilot_gate_uses_same_windows_as_pilot():
    data = json.loads((ROOT / "reports/advanced/wape15_four_candidates.json").read_text())
    assert data["pilot_windows"] == data["reference_windows"] == [1, 2]
    assert data["reference_mean_windows_1_2"] == 0.27835
    assert data["gate"] == 0.26443
