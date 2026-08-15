"""Archivage définitif de la V1 forecasting — snapshot de métriques figé,
métadonnées enrichies, aucune valeur déjà publiée n'est recalculée à un
grain différent ou écrasée silencieusement.

    python -m src.pipelines.finalize_forecast_v1

Écrit :
* reports/forecast_final/v1_metrics_snapshot.json — instantané complet,
  gelé, de toutes les métriques V1 (quotidien, cumulé 7/14/30j, par
  fenêtre, fallbacks, cold-start, intervalles).
* models/forecast_final/metadata.json — enrichi (clés ajoutées, aucune
  clé existante supprimée ni modifiée).
"""

from __future__ import annotations

import glob
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from src.config.settings import PROJECT_ROOT
from src.pipelines.backtest_postprocess import OPERATIONAL_DIR
from src.pipelines.backtest_report_forecasting_final import (
    CORE_MODELS, load_daily, raw_bias_normalized, raw_wape,
)
from src.pipelines.train_final_forecast import META_PATH, compute_calibration_quantiles
from src.utils.logging_utils import get_logger, setup_logging

logger = get_logger(__name__)

SNAPSHOT_PATH = PROJECT_ROOT / "reports" / "forecast_final" / "v1_metrics_snapshot.json"
TABLE_PATH = PROJECT_ROOT / "data" / "processed" / "table_analytique.parquet"


def sha256_of(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def cumulative_metrics(daily: pd.DataFrame, model: str, days: int) -> dict:
    """WAPE/biais cumulés sur les `days` premiers jours de chaque fenêtre
    (SUM(y), SUM(y_pred) sur 1..days par produit x fenêtre, puis WAPE)."""
    sub = daily[(daily["modele"] == model) & (daily["h"] >= 1) & (daily["h"] <= days)]
    agg = sub.groupby(["unique_id", "window"])[["y", "y_pred"]].sum()
    y, yp = agg["y"].to_numpy("float64"), agg["y_pred"].to_numpy("float64")
    return {
        "jours": days, "n_produits_fenetres": len(agg),
        "WAPE": raw_wape(y, yp), "biais_normalise": raw_bias_normalized(y, yp),
        "MAE": float(np.abs(yp - y).mean()),
        "biais_total_unites": float((yp - y).mean()),
        "volume_reel_total": float(y.sum()), "volume_prevu_total": float(yp.sum()),
    }


def per_window_metrics(daily: pd.DataFrame, model: str) -> list[dict]:
    sub = daily[daily["modele"] == model]
    agg30 = sub.groupby(["unique_id", "window"])[["y", "y_pred"]].sum().reset_index()
    rows = []
    for w, g in agg30.groupby("window"):
        y, yp = g["y"].to_numpy("float64"), g["y_pred"].to_numpy("float64")
        rows.append({"fenetre": int(w), "WAPE_cumule_30j": raw_wape(y, yp), "biais_normalise": raw_bias_normalized(y, yp)})
    return rows


def main() -> None:
    setup_logging()
    table = pd.read_parquet(TABLE_PATH)
    table["ds"] = pd.to_datetime(table["ds"])
    daily, op = load_daily()

    # --- Métriques quotidiennes (grain produit x jour) -----------------------
    daily_metrics = {}
    for name in CORE_MODELS:
        g = daily[daily["modele"] == name]
        y, yp = g["y"].to_numpy("float64"), g["y_pred"].to_numpy("float64")
        daily_metrics[name] = {
            "WAPE_quotidien": raw_wape(y, yp),
            "biais_normalise": raw_bias_normalized(y, yp),
            "biais_moyen_quotidien_unites": float((yp - y).mean()),
            "MAE_quotidien": float(np.abs(yp - y).mean()),
            "n_lignes": int(len(g)),
        }

    # --- Métriques cumulées 7 / 14 / 30 jours, pour AutoETS et WindowAverage28 ---
    cumule = {}
    for name in ("AutoETS", "WindowAverage28"):
        cumule[name] = {str(d): cumulative_metrics(daily, name, d) for d in (7, 14, 30)}

    # --- Résultats par fenêtre (grain cumulé 30j, référence de sélection) ----
    par_fenetre = {name: per_window_metrics(daily, name) for name in ("AutoETS", "WindowAverage28")}

    # --- Fallbacks AutoETS -----------------------------------------------------
    ae = op[(op["model_requested"] == "AutoETS") & (op["train_observations"] > 0)]
    n_eligible = ae[["unique_id", "window"]].drop_duplicates().shape[0]
    n_native = ae[ae["status"] == "success_valid_prediction"][["unique_id", "window"]].drop_duplicates().shape[0]
    n_exception = ae[ae["status"] == "exception_fallback"][["unique_id", "window"]].drop_duplicates().shape[0]
    fallback_info = {
        "n_eligible": int(n_eligible), "n_natif": int(n_native), "n_repli_exception": int(n_exception),
        "taux_repli": n_exception / n_eligible, "modele_repli": "Naive",
    }

    # --- Cold-start --------------------------------------------------------
    cs = op[op["status"] == "cold_start_fallback"]
    cs_one = cs[cs["model_requested"] == "AutoETS"]
    cold_start_info = {
        "strategie": "ColdStartZero", "n_produits": int(cs_one["unique_id"].nunique()),
        "n_lignes": int(len(cs_one)), "WAPE": 1.0,
        "justification": "Meilleure WAPE poolée parmi les stratégies testées sur données réelles (cf. rapport 21 §5) — pas une hypothèse par défaut non testée.",
    }

    # --- Intervalles ---------------------------------------------------------
    quantiles = compute_calibration_quantiles()
    intervals_info = {f"{bucket}_{level:.2f}": {"lo_residual": lo, "hi_residual": hi}
                       for (bucket, level), (lo, hi) in quantiles.items()}

    # --- Fichiers de prévisions, rapports, tests, dépendances ------------------
    forecast_files = {
        "parquet": str((PROJECT_ROOT / "reports" / "forecast_final" / "previsions_finales.parquet").relative_to(PROJECT_ROOT)),
        "csv": str((PROJECT_ROOT / "reports" / "forecast_final" / "previsions_finales.csv").relative_to(PROJECT_ROOT)),
    }
    reports_list = sorted(
        str(p.relative_to(PROJECT_ROOT)) for p in (PROJECT_ROOT / "reports").glob("1[5-9]_*")
    ) + sorted(
        str(p.relative_to(PROJECT_ROOT)) for p in (PROJECT_ROOT / "reports").glob("2[0-4]_*")
    )

    try:
        pytest_result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q"], cwd=PROJECT_ROOT,
            capture_output=True, text=True, timeout=300,
        )
        tests_status = pytest_result.stdout.strip().splitlines()[-1] if pytest_result.stdout.strip() else "voir stderr"
        tests_ok = pytest_result.returncode == 0
    except Exception as exc:  # noqa: BLE001
        tests_status = f"échec exécution : {exc}"
        tests_ok = False

    dependencies = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8")

    # --- Versions données / schéma (pas de git : hash de contenu) -------------
    data_version = sha256_of(TABLE_PATH)[:16]
    schema_fingerprint = hashlib.sha256(
        json.dumps(sorted(f"{c}:{t}" for c, t in table.dtypes.astype(str).items()), ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:16]

    snapshot = {
        "genere_le": datetime.now(timezone.utc).isoformat(),
        "model_version": "forecasting_v1",
        "data_version_sha256_16": data_version,
        "schema_version_sha256_16": schema_fingerprint,
        "periode_entrainement": {
            "debut": str(table["ds"].min().date()), "fin": str(table["ds"].max().date()),
        },
        "metriques_quotidiennes_grain_produit_jour": daily_metrics,
        "metriques_cumulees_7_14_30j": cumule,
        "resultats_par_fenetre": par_fenetre,
        "fallback_autoets": fallback_info,
        "cold_start": cold_start_info,
        "intervalles_conformes_residus_lo_hi": intervals_info,
        "fichiers_previsions": forecast_files,
        "rapports": reports_list,
        "tests": {"resume": tests_status, "tous_verts": tests_ok},
        "dependances_requirements_txt": dependencies,
        "commande_reentrainement": "python -m src.pipelines.train_final_forecast",
        "commande_generation_previsions": "python -m src.pipelines.train_final_forecast  # entraînement et prévision sont une seule commande (modèles stateless, refit à chaque appel)",
        "commande_backtest_complet": "python -m src.pipelines.backtest_baselines && python -m src.pipelines.backtest_postprocess && python -m src.pipelines.backtest_lightgbm && python -m src.pipelines.backtest_report_final && python -m src.pipelines.backtest_report_lightgbm && python -m src.pipelines.backtest_report_forecasting_final",
    }
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    logger.info("Snapshot écrit : %s", SNAPSHOT_PATH)

    # --- Enrichissement metadata.json (ajout de clés, rien d'écrasé) -----------
    existing = json.loads(META_PATH.read_text(encoding="utf-8"))
    additions = {
        "model_version": "forecasting_v1",
        "primary_model": "AutoETS",
        "fallback_model": "Naive",
        "secondary_model": "WindowAverage28",
        "cold_start_strategy": "ColdStartZero",
        "main_validated_use": "cumulative_sales_forecast_30d",
        "daily_wape_approx": round(daily_metrics["AutoETS"]["WAPE_quotidien"], 4),
        "daily_forecast_reliable": False,
        "horizon_7_validated": True,
        "horizon_14_validated": True,
        "horizon_30_validated": True,
        "horizon_90_validated": False,
        "target": "quantite_vendue_observee",
        "demand_unconstrained_estimated": False,
        "data_version": data_version,
        "schema_version": schema_fingerprint,
        "metrics_snapshot_path": str(SNAPSHOT_PATH.relative_to(PROJECT_ROOT)),
    }
    for k, v in additions.items():
        if k in existing and existing[k] != v:
            logger.warning("Clé déjà présente avec une valeur différente, NON écrasée : %s (existant=%r, nouveau=%r)", k, existing[k], v)
            continue
        existing[k] = v
    META_PATH.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Métadonnées enrichies : %s", META_PATH)


if __name__ == "__main__":
    main()
