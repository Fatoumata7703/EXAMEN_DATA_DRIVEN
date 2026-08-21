"""Garde-fou : le forecasting V2 valide ne doit jamais etre modifie par les
travaux V4 (pricing/recommandation). Ce test ne relit ni ne reentraine
aucun modele de forecasting ; il verifie seulement que les fichiers deja
versionnes n'ont pas bouge.

Trois niveaux de verification independants :
1. Les valeurs de decision et de metrique macro figees dans
   `models/FINAL_STATUS.json` (modeles retenus, WAPE30, biais) restent
   exactement celles validees.
2. Les empreintes SHA-256 des artefacts forecasting correspondent aux
   manifestes deja commit (`models/forecasting/manifest.sha256.json`,
   `models/advanced/forecasting/manifest.sha256.json`), qui datent d'avant
   le debut des travaux V4.
3. Aucun commit poste sur la branche V4 (depuis le commit de depart
   `40bdfae`, premier commit portant ces fichiers) ne touche un chemin
   forecasting.
"""
from __future__ import annotations

import hashlib
import json
import subprocess

from src.config.settings import PROJECT_ROOT

FINAL_STATUS_PATH = PROJECT_ROOT / "models" / "FINAL_STATUS.json"

FORECASTING_DIRS = (
    PROJECT_ROOT / "models" / "forecasting",
    PROJECT_ROOT / "models" / "advanced" / "forecasting",
)

FORECASTING_PATHS_FOR_GIT_CHECK = (
    "models/forecasting",
    "models/advanced/forecasting",
    "models/FINAL_STATUS.json",
    "models/FINAL_STATUS.sha256.json",
)

# Empreinte figee de models/FINAL_STATUS.json au moment ou ce garde-fou a ete
# ecrit (branche v4/pricing-recommendation-training, apres finalisation du
# produit V4). Toute divergence signale une modification du fichier de
# decision forecasting/pricing/recommandation V2, ce qui n'est jamais
# attendu pendant les travaux V4.
EXPECTED_FINAL_STATUS_SHA256 = "a33747a4d483528f9c0d900e39f21e17f09f463656c5fe21acfc1099525eea1b"

# Commit a partir duquel les fichiers forecasting actuels existent sous cette
# forme (premier commit de l'historique squash portant ces artefacts).
FORECASTING_BASELINE_COMMIT = "40bdfae"


def _sha256(path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def test_final_status_declares_the_expected_forecasting_decision():
    status = json.loads(FINAL_STATUS_PATH.read_text(encoding="utf-8"))["status"]
    assert status["forecasting_status"] == "validated"
    assert status["forecasting_daily_model"] == "CrostonOptimized"
    assert status["forecasting_30d_model"] == "LightGBM_direct_per_horizon"
    assert status["forecasting_wape30_macro"] == 0.25831
    assert status["forecasting_bias"] == -0.02589


def test_final_status_file_hash_is_unchanged():
    actual = _sha256(FINAL_STATUS_PATH)
    assert actual == EXPECTED_FINAL_STATUS_SHA256, (
        "models/FINAL_STATUS.json a change depuis la finalisation du produit V4 : "
        f"empreinte actuelle {actual}, attendue {EXPECTED_FINAL_STATUS_SHA256}"
    )


def test_final_status_hash_matches_its_own_manifest():
    manifest_path = PROJECT_ROOT / "models" / "FINAL_STATUS.sha256.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert _sha256(FINAL_STATUS_PATH) == manifest["FINAL_STATUS.json"]


def test_forecasting_artifacts_match_their_committed_manifests():
    mismatches = []
    for directory in FORECASTING_DIRS:
        manifest_path = directory / "manifest.sha256.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for relative_name, expected_hash in manifest.items():
            actual_hash = _sha256(directory / relative_name)
            if actual_hash != expected_hash:
                mismatches.append(f"{directory / relative_name}: attendu {expected_hash}, obtenu {actual_hash}")
    assert not mismatches, "artefacts forecasting modifies :\n" + "\n".join(mismatches)


def test_no_commit_since_baseline_touches_forecasting_paths():
    result = subprocess.run(
        ["git", "diff", "--name-only", FORECASTING_BASELINE_COMMIT, "HEAD", "--",
         *FORECASTING_PATHS_FOR_GIT_CHECK],
        cwd=PROJECT_ROOT, capture_output=True, text=True, check=True,
    )
    changed = [line for line in result.stdout.splitlines() if line.strip()]
    assert not changed, (
        "des commits posterieurs au demarrage des travaux V4 modifient des "
        f"chemins forecasting : {changed}"
    )


def test_forecasting_working_tree_has_no_uncommitted_changes():
    result = subprocess.run(
        ["git", "status", "--porcelain", "--", *FORECASTING_PATHS_FOR_GIT_CHECK],
        cwd=PROJECT_ROOT, capture_output=True, text=True, check=True,
    )
    assert result.stdout.strip() == "", (
        "modifications non commit detectees sur des chemins forecasting : " + result.stdout
    )
