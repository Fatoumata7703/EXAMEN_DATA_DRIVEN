"""Gel des artefacts V1 : manifeste SHA-256 + vérifications finales.

    python -m src.pipelines.freeze_v1_manifest

Ne modifie AUCUN rapport V1 existant. Écrit uniquement :
* reports/forecast_final/v1_manifest.json — empreintes SHA-256.
* reports/forecast_final/v1_final_checks.json — résultats des vérifications.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from src.config.settings import PROJECT_ROOT
from src.pipelines.train_final_forecast import fit_predict_one_series
from src.utils.logging_utils import get_logger, setup_logging

logger = get_logger(__name__)

MANIFEST_PATH = PROJECT_ROOT / "reports" / "forecast_final" / "v1_manifest.json"
CHECKS_PATH = PROJECT_ROOT / "reports" / "forecast_final" / "v1_final_checks.json"
DELIVERABLE_PATH = PROJECT_ROOT / "reports" / "forecast_final" / "previsions_finales.parquet"
META_PATH = PROJECT_ROOT / "models" / "forecast_final" / "metadata.json"

ARTIFACTS = {
    "configuration": PROJECT_ROOT / "config" / "config.yaml",
    "metadonnees_modele": META_PATH,
    "snapshot_metriques": PROJECT_ROOT / "reports" / "forecast_final" / "v1_metrics_snapshot.json",
    "previsions_parquet": DELIVERABLE_PATH,
    "previsions_csv": PROJECT_ROOT / "reports" / "forecast_final" / "previsions_finales.csv",
    "dependances": PROJECT_ROOT / "requirements.txt",
    "rapport_18_baselines": PROJECT_ROOT / "reports" / "18_backtest_rapport_final.md",
    "rapport_21_lightgbm": PROJECT_ROOT / "reports" / "21_rapport_final_lightgbm.md",
    "rapport_22_verification_independante": PROJECT_ROOT / "reports" / "22_verification_independante_metriques.json",
    "rapport_23_forecasting_final": PROJECT_ROOT / "reports" / "23_rapport_final_forecasting.md",
    "rapport_24_entrainement_final": PROJECT_ROOT / "reports" / "24_entrainement_final.md",
    "registre_v2": PROJECT_ROOT / "reports" / "forecast_final" / "forecasting_v2_objectives.md",
}

# Motifs de secrets à ne jamais trouver dans un artefact figé.
SECRET_PATTERNS = [
    re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),  # JWT (clés Supabase)
    re.compile(r"postgres(?:ql)?://[^\s\"']+:[^\s\"']+@"),      # connection string avec mot de passe
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
    hits = []
    for pat in SECRET_PATTERNS:
        if pat.search(text):
            hits.append(pat.pattern)
    return hits


def main() -> None:
    setup_logging()

    # --- Manifeste SHA-256 -----------------------------------------------------
    manifest = {"genere_le": datetime.now(timezone.utc).isoformat(), "artefacts": {}}
    for label, path in ARTIFACTS.items():
        if not path.exists():
            manifest["artefacts"][label] = {"chemin": str(path.relative_to(PROJECT_ROOT)), "statut": "ABSENT"}
            logger.warning("Artefact manquant : %s (%s)", label, path)
            continue
        manifest["artefacts"][label] = {
            "chemin": str(path.relative_to(PROJECT_ROOT)),
            "sha256": sha256_of(path),
            "taille_octets": path.stat().st_size,
        }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Manifeste écrit : %s", MANIFEST_PATH)

    # --- Vérifications finales --------------------------------------------------
    checks: dict[str, object] = {"genere_le": datetime.now(timezone.utc).isoformat()}

    # 1. Reproductibilité : refit sur un petit échantillon, deux fois, comparer.
    table = pd.read_parquet(PROJECT_ROOT / "data" / "processed" / "table_analytique.parquet")
    table["ds"] = pd.to_datetime(table["ds"])
    sample_uid = sorted(table["unique_id"].unique())[:5]
    repro_ok = True
    repro_detail = []
    for uid in sample_uid:
        y = table.loc[table["unique_id"] == uid].sort_values("ds")["y"].to_numpy("float64")
        pred1, eff1, fb1 = fit_predict_one_series(y, 10)
        pred2, eff2, fb2 = fit_predict_one_series(y, 10)
        identical = bool(np.array_equal(pred1, pred2)) and eff1 == eff2 and fb1 == fb2
        repro_ok &= identical
        repro_detail.append({"unique_id": uid, "modele_effectif": eff1, "identique_sur_2_runs": identical})
    checks["reproductibilite_echantillon_5_series"] = {"ok": repro_ok, "detail": repro_detail}

    # 2. NaN / Inf / négatifs sur le livrable complet.
    deliverable = pd.read_parquet(DELIVERABLE_PATH)
    numeric_cols = ["quantite_prevue", "borne_basse_80", "borne_haute_80", "borne_basse_95", "borne_haute_95"]
    n_nan = int(deliverable[numeric_cols].isna().sum().sum())
    n_inf = int(np.isinf(deliverable[numeric_cols].to_numpy(dtype="float64")).sum())
    n_neg = int((deliverable[numeric_cols] < 0).sum().sum())
    checks["nan_inf_negatifs"] = {"n_nan": n_nan, "n_inf": n_inf, "n_negatifs": n_neg, "ok": (n_nan == 0 and n_inf == 0 and n_neg == 0)}

    # 3. Cohérence des horizons : 1..90 sans trou, par produit.
    expected_horizons = set(range(1, 91))
    incoherent = []
    for uid, g in deliverable.groupby("product_id"):
        if set(g["horizon"]) != expected_horizons:
            incoherent.append(uid)
    checks["coherence_horizons_1_a_90"] = {"n_produits_incoherents": len(incoherent), "ok": len(incoherent) == 0}

    # 4. Bornes ordonnées.
    bounds_ok = bool((deliverable["borne_basse_80"] <= deliverable["borne_haute_80"]).all() and
                      (deliverable["borne_basse_95"] <= deliverable["borne_haute_95"]).all())
    checks["bornes_ordonnees"] = {"ok": bounds_ok}

    # 5. Présence des métadonnées.
    meta_exists = META_PATH.exists()
    meta_keys_required = {
        "model_version", "primary_model", "fallback_model", "secondary_model", "cold_start_strategy",
        "main_validated_use", "daily_wape_approx", "daily_forecast_reliable", "horizon_7_validated",
        "horizon_14_validated", "horizon_30_validated", "horizon_90_validated", "target",
        "demand_unconstrained_estimated",
    }
    meta_content = json.loads(META_PATH.read_text(encoding="utf-8")) if meta_exists else {}
    missing_keys = sorted(meta_keys_required - set(meta_content.keys()))
    checks["metadonnees"] = {"present": meta_exists, "cles_manquantes": missing_keys, "ok": meta_exists and not missing_keys}

    # 6. Absence de secrets dans les artefacts figés.
    secrets_found = {}
    for label, path in ARTIFACTS.items():
        if path.exists() and path.suffix in (".json", ".md", ".csv", ".yaml", ".txt"):
            hits = scan_for_secrets(path)
            if hits:
                secrets_found[label] = hits
    checks["absence_secrets"] = {"ok": len(secrets_found) == 0, "detail": secrets_found}

    all_ok = all(
        checks[k]["ok"] for k in (
            "reproductibilite_echantillon_5_series", "nan_inf_negatifs", "coherence_horizons_1_a_90",
            "bornes_ordonnees", "metadonnees", "absence_secrets",
        )
    )
    checks["verdict_global"] = "TOUS LES CONTROLES PASSENT" if all_ok else "AU MOINS UN CONTROLE A ECHOUE"

    CHECKS_PATH.write_text(json.dumps(checks, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Vérifications écrites : %s — %s", CHECKS_PATH, checks["verdict_global"])


if __name__ == "__main__":
    main()
