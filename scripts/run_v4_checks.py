"""Point d'entree unique de verification du produit V4, pense pour etre
branche tel quel dans un pipeline d'integration continue (aucune execution
automatique n'est configuree ici : ce script ne fait qu'exister, il n'est
pas deploye ni planifie).

Enchaine, dans l'ordre, sans reseau et sans reentrainement :
1. le garde-fou d'immutabilite du forecasting ;
2. les tests unitaires pricing V4 et recommandation V4 ;
3. les tests API et d'integration du produit V4 ;
4. la validation de tous les manifestes SHA-256 du depot.

Sort avec un code non nul des la premiere etape en echec.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

from src.config.settings import PROJECT_ROOT

STEPS: list[tuple[str, list[str]]] = [
    ("Garde-fou forecasting (aucun fichier modifie)",
     [sys.executable, "-m", "pytest", "tests/test_forecasting_unchanged.py", "-v"]),
    ("Tests unitaires pricing V4",
     [sys.executable, "-m", "pytest", "tests/test_v4_pricing.py", "-q"]),
    ("Tests unitaires recommandation V4",
     [sys.executable, "-m", "pytest", "tests/test_v4_recommendation.py", "-q"]),
    ("Tests API produit V4",
     [sys.executable, "-m", "pytest", "api_v4/tests/test_api.py", "-q"]),
    ("Tests d'integration produit V4",
     [sys.executable, "-m", "pytest", "api_v4/tests/test_integration.py", "-q"]),
    ("Validation des manifestes SHA-256",
     [sys.executable, "-m", "scripts.validate_manifests"]),
]


def main() -> int:
    overall_start = time.perf_counter()
    for label, command in STEPS:
        print(f"\n=== {label} ===")
        started = time.perf_counter()
        result = subprocess.run(command, cwd=PROJECT_ROOT)
        elapsed = time.perf_counter() - started
        print(f"--- {label} : {'OK' if result.returncode == 0 else 'ECHEC'} ({elapsed:.1f}s) ---")
        if result.returncode != 0:
            print(f"\nArret : etape en echec -> {label}")
            return result.returncode
    total = time.perf_counter() - overall_start
    print(f"\nToutes les verifications sont passees ({total:.1f}s au total).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
