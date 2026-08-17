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
