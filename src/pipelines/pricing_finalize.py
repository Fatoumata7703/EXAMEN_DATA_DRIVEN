"""Clôture pricing V1 — métadonnées, manifeste SHA-256, vérifications finales.
Miroir de `finalize_forecast_v1.py` / `freeze_v1_manifest.py`, adapté au
pricing. Ne republie rien, ne déploie rien.

    python -m src.pipelines.pricing_finalize
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from src.config.settings import PROJECT_ROOT
from src.utils.logging_utils import get_logger, setup_logging

logger = get_logger(__name__)

PRICING_DIR = PROJECT_ROOT / "reports" / "pricing_final"
META_PATH = PRICING_DIR / "metadata.json"
MANIFEST_PATH = PRICING_DIR / "manifest.json"
CHECKS_PATH = PRICING_DIR / "final_checks.json"

ARTIFACTS = {
    "eligibilite": PROJECT_ROOT / "reports" / "28_pricing_eligibilite.md",
    "baselines_confusion": PROJECT_ROOT / "reports" / "29_pricing_baselines_confusion.md",
    "validation_temporelle": PROJECT_ROOT / "reports" / "30_pricing_validation_temporelle.md",
    "marges_negatives": PROJECT_ROOT / "reports" / "31_pricing_marges_negatives.md",
    "simulateur": PROJECT_ROOT / "reports" / "32_pricing_simulateur.md",
    "comparaison_politiques": PROJECT_ROOT / "reports" / "34_pricing_comparaison_politiques.md",
    "comparaison_rapport_final": PROJECT_ROOT / "reports" / "33_pricing_comparaison_rapport_final.md",
    "audit_pricing": PROJECT_ROOT / "reports" / "26_audit_pricing.md",
    "livrable_intermediaire": PROJECT_ROOT / "reports" / "27_livrable_intermediaire_pricing.md",
    "objectifs_v2": PRICING_DIR / "pricing_v2_objectives.md",
    "simulateur_sorties_csv": PRICING_DIR / "simulateur_sorties.csv",
    "comparaison_methodes_csv": PRICING_DIR / "comparaison_methodes.csv",
    "comparaison_politiques_csv": PRICING_DIR / "comparaison_politiques.csv",
    "eligibilite_csv": PRICING_DIR / "eligibilite_produits.csv",
    "baselines_csv": PRICING_DIR / "baselines.csv",
    "dataset_pricing": PROJECT_ROOT / "data" / "processed" / "table_pricing.parquet",
    "dependances": PROJECT_ROOT / "requirements.txt",
}

SECRET_PATTERNS = [
    re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    re.compile(r"postgres(?:ql)?://[^\s\"']+:[^\s\"']+@"),
    re.compile(r"(?i)(service_role|anon_key|api_key|secret)\s*[:=]\s*[\"']?[A-Za-z0-9._-]{16,}"),
]


def sha256_of(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def scan_for_secrets(path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:  # noqa: BLE001
        return []
    return [p.pattern for p in SECRET_PATTERNS if p.search(text)]


def main() -> None:
    setup_logging()
    sim = pd.read_csv(PRICING_DIR / "simulateur_sorties.csv")
    comparison = pd.read_csv(PRICING_DIR / "comparaison_methodes.csv", index_col=0)
    eligibility = pd.read_csv(PRICING_DIR / "eligibilite_produits.csv")

    # La méthode réellement utilisée par le simulateur est stockée dans la colonne 'methode' du csv
    method_used = sim["methode"].iloc[0] if len(sim) else None
    quantity_wape_exact = float(comparison.loc[method_used, "WAPE_quantite"]) if method_used in comparison.index else None
    biais_exact = float(comparison.loc[method_used, "biais_quantite"]) if method_used in comparison.index else None

    metadata = {
        # --- Clés minimales exactes demandées ---
        "pricing_version": "pricing_v1_exploratory",
        "model": method_used,
        "catalog_price_changes": 0,
        "catalog_prices_fixed_products": 300,
        "causal": False,
        "optimal_price_claim_allowed": False,
        "automatic_application_allowed": False,
        "human_validation_required": True,
        "quantity_wape": quantity_wape_exact,
        "off_policy_evaluation_validated": False,
        "primary_objective": "margin_scenario_simulation",
        "minimum_margin_floor": 0.05,
        # --- Compléments ---
        "genere_le": datetime.now(timezone.utc).isoformat(),
        "positionnement": "aide a la decision exploratoire (analyse promotions, uplift observationnel, simulation de remises sous contrainte de marge) - PAS un moteur de prix optimal causal, PAS pret pour la production",
        "biais_quantite_methode_retenue": biais_exact,
        "objectif_prix_optimal_continu_hors_promo": "non_calculable_structurellement",
        "regle_selection_methode": f"biais_quantite_abs < {0.15} sinon min(abs_biais)",
        "n_produits_eligible_individuel": int((eligibility["groupe"] == "eligible_individuel").sum()),
        "n_produits_eligible_pooling_categorie": int((eligibility["groupe"] == "eligible_pooling_categorie").sum()),
        "n_produits_non_eligible": int((eligibility["groupe"] == "non_eligible").sum()),
        "marges_minimales_testees": [0.0, 0.05, 0.10, 0.15],
        "objectifs_simules": ["marge", "chiffre_affaires", "ecoulement_stock", "compromis_marge_volume"],
        "n_lignes_marge_negative_historique": 679,
        "n_produits_marge_negative_historique": 73,
        "confidence_haute_atteignable": quantity_wape_exact is not None and quantity_wape_exact < 0.5,
        "cible": "quantite_vendue_observee (identique au forecasting) et chiffre_affaires_net_xof / marge_totale_xof",
        "aucune_publication_supabase": True,
        "aucun_deploiement": True,
    }
    PRICING_DIR.mkdir(parents=True, exist_ok=True)
    META_PATH.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Métadonnées écrites : %s", META_PATH)

    manifest = {"genere_le": datetime.now(timezone.utc).isoformat(), "artefacts": {}}
    for label, path in ARTIFACTS.items():
        if not path.exists():
            manifest["artefacts"][label] = {"chemin": str(path), "statut": "ABSENT"}
            continue
        manifest["artefacts"][label] = {
            "chemin": str(path.relative_to(PROJECT_ROOT)), "sha256": sha256_of(path), "taille_octets": path.stat().st_size,
        }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Manifeste écrit : %s", MANIFEST_PATH)

    checks: dict[str, object] = {"genere_le": datetime.now(timezone.utc).isoformat()}

    ok_rows = sim[sim["simulation_status"] == "ok"]
    n_neg_price = int((ok_rows["prix_simule_xof"] < 0).sum())
    n_below_cost = int((ok_rows["prix_simule_xof"] < ok_rows["cout_unitaire_xof"]).sum())
    n_nan = int(ok_rows[["suggested_discount_exploratory", "prix_simule_xof", "quantite_prevue", "ca_prevu_xof", "marge_prevue_xof"]].isna().sum().sum())
    checks["prix_simule_negatif"] = {"n": n_neg_price, "ok": n_neg_price == 0}
    checks["prix_simule_sous_le_cout"] = {"n": n_below_cost, "ok": n_below_cost == 0}
    checks["nan_dans_simulations_ok"] = {"n": n_nan, "ok": n_nan == 0}

    grid_max = 30.0
    n_extrapole = int((ok_rows["suggested_discount_exploratory"] > grid_max).sum())
    checks["extrapolation_hors_grille"] = {"n": n_extrapole, "ok": n_extrapole == 0}

    non_elig_with_reco = sim[(sim["simulation_status"] == "insufficient_evidence") & sim["suggested_discount_exploratory"].notna()]
    checks["insufficient_evidence_sans_fausse_simulation"] = {"n": len(non_elig_with_reco), "ok": len(non_elig_with_reco) == 0}

    aucune_haute = int((ok_rows["niveau_confiance"] == "haute").sum())
    checks["aucune_confiance_haute_si_wape_eleve"] = {
        "n_haute": aucune_haute,
        "ok": aucune_haute == 0 or (comparison.loc[method_used, "WAPE_quantite"] < 0.5 if method_used in comparison.index else False),
    }

    try:
        result = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=300)
        tests_summary = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "voir stderr"
        tests_ok = result.returncode == 0
    except Exception as exc:  # noqa: BLE001
        tests_summary, tests_ok = f"échec : {exc}", False
    checks["tests"] = {"resume": tests_summary, "ok": tests_ok}

    secrets_found = {label: hits for label, path in ARTIFACTS.items() if path.exists() and (hits := scan_for_secrets(path))}
    checks["absence_secrets"] = {"ok": len(secrets_found) == 0, "detail": secrets_found}

    all_ok = all(v["ok"] for v in checks.values() if isinstance(v, dict) and "ok" in v)
    checks["verdict_global"] = "TOUS LES CONTROLES PASSENT" if all_ok else "AU MOINS UN CONTROLE A ECHOUE"
    CHECKS_PATH.write_text(json.dumps(checks, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Vérifications écrites : %s — %s", CHECKS_PATH, checks["verdict_global"])


if __name__ == "__main__":
    main()
