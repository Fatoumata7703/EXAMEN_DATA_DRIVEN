import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "models" / "advanced" / "recommendation_ranking"


def test_candidate_gate_and_official_baseline_are_explicit():
    metadata = json.loads((OUT / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["official_baseline"] == "popularite_globale"
    assert metadata["ranking_started"] is False
    assert min(metadata["next_purchase_candidate_recall_at50_lower_bound"]) >= 0.50
    assert metadata["complement_panier_reference"]["status"] == "systeme_metier_separe"


def test_candidate_manifest_matches():
    manifest = json.loads((OUT / "manifest.sha256.json").read_text(encoding="utf-8"))
    for name, expected in manifest.items():
        assert hashlib.sha256((OUT / name).read_bytes()).hexdigest() == expected


def test_session_is_not_declared_usable():
    coverage = json.loads((OUT / "candidate_coverage.json").read_text(encoding="utf-8"))
    assert coverage["session"]["candidate_recall_at50"] == "not_usable"
