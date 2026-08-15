"""Entraînement final AutoETS+repli Naive sur tout l'historique disponible,
production des prévisions 7/14/30 jours (90 jours avec réserve forte) et
livrable local. Aucune publication Supabase, aucun déploiement.

    python -m src.pipelines.train_final_forecast

Modèle : AutoETS (statsforecast, season_length=7), repli Naive (dernière
valeur observée répétée) sur exception — exactement le pipeline validé au
backtest (`reports/23_rapport_final_forecasting.md` §9). Intervalles :
méthode conforme sur résidus empiriques, calibrée sur les résidus poolés des
6 fenêtres de backtest (`reports/backtest/operational_predictions/`), par
bucket d'horizon — pas d'intervalle natif statsforecast (non calibré/validé
dans ce projet, cf. rapport 23 §8).
"""

from __future__ import annotations

import glob
import json
import warnings
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from src.config.settings import PROJECT_ROOT
from src.pipelines.backtest_baselines import H as BACKTEST_H, SEASONALITY
from src.pipelines.backtest_postprocess import OPERATIONAL_DIR
from src.utils.logging_utils import get_logger, setup_logging

logger = get_logger(__name__)

MODEL_DIR = PROJECT_ROOT / "models" / "forecast_final"
DELIVERABLE_PATH = PROJECT_ROOT / "reports" / "forecast_final" / "previsions_finales.parquet"
DELIVERABLE_CSV = PROJECT_ROOT / "reports" / "forecast_final" / "previsions_finales.csv"
META_PATH = MODEL_DIR / "metadata.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "24_entrainement_final.md"

HORIZONS_LIVRABLE = [7, 14, 30]  # horizons "normaux", validés par le backtest (H=30)
HORIZON_ETENDU = 90  # produit avec réserve forte : hors de la plage validée (backtest H=30)
MAX_H = 90

VERSION = "forecast-autoets-naive-fallback-v1"
HORIZON_BUCKETS = [("J+1", 1, 1), ("J+2 a J+7", 2, 7), ("J+8 a J+14", 8, 14), ("J+15 a J+30", 15, 30)]


def fit_predict_one_series(y_train: np.ndarray, h: int) -> tuple[np.ndarray, str, bool]:
    """Retourne (prévision, modele_effectif, fallback_applique)."""
    from statsforecast.models import AutoETS

    try:
        warnings.simplefilter("ignore")
        pred = np.asarray(AutoETS(season_length=SEASONALITY).forecast(h=h, y=y_train)["mean"], dtype=float)
        pred = np.clip(pred, 0, None)
        return pred, "AutoETS", False
    except Exception as exc:  # noqa: BLE001
        last = y_train[-1] if len(y_train) else 0.0
        pred = np.repeat(max(last, 0.0), h)
        logger.info("Repli Naive pour une série : %s: %s", type(exc).__name__, exc)
        return pred, "Naive", True


def compute_calibration_quantiles() -> dict[tuple[str, float], tuple[float, float]]:
    """Résidus poolés des 6 fenêtres de backtest (AutoETS+repli, y_pred_final),
    par bucket d'horizon — calibration sur TOUTES les fenêtres disponibles
    (aucune fenêtre à protéger ici : on prévoit des dates futures jamais vues
    dans le backtest, contrairement à la validation croisée du rapport 23 §8)."""
    op = pd.concat(
        [pd.read_parquet(f) for f in sorted(glob.glob(str(OPERATIONAL_DIR / "*.parquet")))],
        ignore_index=True,
    )
    ae = op[(op["model_requested"] == "AutoETS") & (op["train_observations"] > 0)].copy()
    ae["h"] = (ae["ds"] - ae["cutoff"]).dt.days
    e = ae["y"] - ae["y_pred_final"]

    quantiles: dict[tuple[str, float], tuple[float, float]] = {}
    for label, lo, hi in HORIZON_BUCKETS:
        mask = (ae["h"] >= lo) & (ae["h"] <= hi)
        residuals = e[mask].to_numpy("float64")
        for level, alpha in ((0.80, 0.20), (0.95, 0.05)):
            quantiles[(label, level)] = (
                float(np.quantile(residuals, alpha / 2)),
                float(np.quantile(residuals, 1 - alpha / 2)),
            )
    return quantiles


def bucket_for_horizon(h: int) -> str:
    if h == 1:
        return "J+1"
    if h <= 7:
        return "J+2 a J+7"
    if h <= 14:
        return "J+8 a J+14"
    if h <= 30:
        return "J+15 a J+30"
    return "J+15 a J+30"  # 90j : réutilise le dernier bucket validé, cf. réserve forte


def main() -> None:
    setup_logging()
    table = pd.read_parquet(PROJECT_ROOT / "data" / "processed" / "table_analytique.parquet")
    table["ds"] = pd.to_datetime(table["ds"])
    cutoff = table["ds"].max()
    date_entrainement = datetime.now(timezone.utc)

    logger.info("Entraînement final : historique jusqu'au %s (inclus), %d séries.",
                cutoff.date(), table["unique_id"].nunique())

    quantiles = compute_calibration_quantiles()

    products = sorted(table["unique_id"].unique())
    rows = []
    t0 = datetime.now(timezone.utc)
    n_fallback = 0
    for uid in products:
        y_train = table.loc[table["unique_id"] == uid].sort_values("ds")["y"].to_numpy(dtype="float64")
        pred, model_effective, fallback = fit_predict_one_series(y_train, MAX_H)
        n_fallback += int(fallback)
        for h in range(1, MAX_H + 1):
            target_date = cutoff + pd.Timedelta(days=h)
            bucket = bucket_for_horizon(h)
            lo_q80, hi_q80 = quantiles[(bucket, 0.80)]
            lo_q95, hi_q95 = quantiles[(bucket, 0.95)]
            point = float(pred[h - 1])
            rows.append({
                "product_id": uid,
                "date_prevision": cutoff.date().isoformat(),
                "date_cible": target_date.date().isoformat(),
                "horizon": h,
                "quantite_prevue": point,
                "borne_basse_80": max(point + lo_q80, 0.0),
                "borne_haute_80": max(point + hi_q80, max(point + lo_q80, 0.0)),
                "borne_basse_95": max(point + lo_q95, 0.0),
                "borne_haute_95": max(point + hi_q95, max(point + lo_q95, 0.0)),
                "modele_demande": "AutoETS",
                "modele_effectif": model_effective,
                "fallback_applique": fallback,
                "version": VERSION,
                "date_entrainement": date_entrainement.isoformat(),
                "horizon_valide_par_backtest": h <= BACKTEST_H,
            })
    duration = (datetime.now(timezone.utc) - t0).total_seconds()
    logger.info("Terminé : %d séries, %d replis Naive (%.2f%%), %.1fs.",
                len(products), n_fallback, 100 * n_fallback / len(products), duration)

    deliverable = pd.DataFrame(rows)
    DELIVERABLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    deliverable.to_parquet(DELIVERABLE_PATH, index=False)
    deliverable.to_csv(DELIVERABLE_CSV, index=False)

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    metadata = {
        "version": VERSION,
        "date_entrainement": date_entrainement.isoformat(),
        "cutoff_donnees": cutoff.date().isoformat(),
        "n_series": len(products),
        "n_fallback_naive": n_fallback,
        "taux_fallback": n_fallback / len(products),
        "modele_principal": "AutoETS (statsforecast, season_length=7)",
        "modele_repli": "Naive (dernière valeur observée, répétée)",
        "horizon_max_produit": MAX_H,
        "horizon_valide_par_backtest": BACKTEST_H,
        "methode_intervalles": "conforme empirique sur résidus poolés des 6 fenêtres de backtest, par bucket d'horizon (J+1 / J+2-7 / J+8-14 / J+15-30) ; J+31-90 réutilise le bucket J+15-30 (hors plage validée)",
        "avertissement_90j": (
            "Les prévisions au-delà de J+30 (jusqu'à J+90) n'ont fait l'objet d'AUCUNE validation "
            "empirique — le backtest s'arrête à H=30. Les intervalles J+31-90 réutilisent la calibration "
            "J+15-30 par extrapolation, ce qui SOUS-ESTIME probablement l'incertitude réelle à 90 jours. "
            "À utiliser avec une réserve forte, jamais comme engagement opérationnel."
        ),
        "cible": "quantite_vendue_observee (ventes observées, pas une demande théorique corrigée du stock)",
        "aucune_publication_supabase": True,
        "aucun_deploiement": True,
    }
    META_PATH.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")

    report = "\n".join([
        "# 24 — Entraînement final et livrable de prévisions",
        "",
        f"_Généré le {date_entrainement.isoformat()}._",
        "",
        f"- Modèle : **AutoETS + repli Naive** (identique au pipeline validé, rapport 23 §9).",
        f"- Historique d'entraînement : jusqu'au **{cutoff.date()}** inclus, {len(products)} séries.",
        f"- Replis Naive : {n_fallback}/{len(products)} séries ({100*n_fallback/len(products):.2f}%).",
        f"- Durée d'entraînement + prévision : {duration:.1f}s.",
        f"- Horizons produits : 1 à {MAX_H} jours ; **seuls 1-30 jours sont couverts par le backtest** "
        f"(H={BACKTEST_H}) — 31-90 jours marqués `horizon_valide_par_backtest=False` dans le livrable, "
        "réserve forte explicite (cf. `models/forecast_final/metadata.json`).",
        f"- Intervalles : conformes, calibrés sur les résidus poolés des 6 fenêtres de backtest, par "
        "bucket d'horizon.",
        "",
        f"**Livrable** : `{DELIVERABLE_PATH.relative_to(PROJECT_ROOT)}` "
        f"(et .csv) — {len(deliverable)} lignes, colonnes : "
        + ", ".join(deliverable.columns),
        "",
        f"**Métadonnées modèle** : `{META_PATH.relative_to(PROJECT_ROOT)}`",
        "",
        "**Aucune publication Supabase, aucun déploiement — livrable strictement local.**",
    ])
    REPORT_PATH.write_text(report, encoding="utf-8")
    logger.info("Rapport écrit : %s", REPORT_PATH)


if __name__ == "__main__":
    main()
