"""Post-traitement du backtest instrumenté — couche opérationnelle, séparée des bruts.

    python -m src.pipelines.backtest_postprocess

Ne touche **jamais** aux 42 checkpoints bruts (`data/interim/backtest/*.parquet`,
produits par les 8 h 50 de calcul du 2026-08-13/14). Ce module :

1. les copie tels quels dans ``reports/backtest/raw_predictions/`` (preuve
   d'immutabilité) ;
2. construit ``reports/backtest/operational_predictions/`` : mêmes lignes,
   plus la classification complète du repli le cas échéant.

Deux causes de valeur manquante, **jamais confondues** :

* **Cas A — historique insuffisant** : le produit existe dans le train, mais
  le modèle exige plus d'observations qu'il n'en a. Repli *spécifique à la
  famille du modèle* (`Naive` pour SeasonalNaive7 sous-alimenté,
  `AvailableHistoryAverage` pour WindowAverage28 sous-alimenté) — jamais
  `ColdStartZero`.
* **Cas B — produit absent du train** : aucune observation passée n'existe.
  Ce n'est pas un échec de modèle. `model_effective = ColdStartZero`,
  valeur = 0, jamais qualifié de « Naive ».

Les replis déjà survenus pendant le calcul d'origine (exception, budget —
journalisés dans `reports/15_backtest_log.jsonl`) sont réattribués ici avec la
même rigueur : `model_requested` n'est **jamais** écrasé par le modèle de repli.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from src.config.settings import PROJECT_ROOT
from src.evaluation.metrics import compute_all_metrics, naive_scale
from src.pipelines.backtest_baselines import (
    CHECKPOINT_DIR,
    LOG_PATH,
    N_WINDOWS,
    SEASONALITY,
    _model_factory,
    build_windows,
)
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)

RAW_DIR = PROJECT_ROOT / "reports" / "backtest" / "raw_predictions"
OPERATIONAL_DIR = PROJECT_ROOT / "reports" / "backtest" / "operational_predictions"

AUTOARIMA_COVERAGE_THRESHOLD = 0.90  # sous ce seuil : "non comparable / couverture insuffisante"

STATUS_VALUES = (
    "success_valid_prediction",
    "success_invalid_prediction_fallback",
    "exception_fallback",
    "budget_fallback",
    "cold_start_fallback",
)


@dataclass
class WindowContext:
    index: int
    cutoff: pd.Timestamp
    train_observations: pd.Series  # index=unique_id -> n obs dans le train
    last_value: pd.Series  # index=unique_id -> dernière valeur connue
    mean_value: pd.Series  # index=unique_id -> moyenne de l'historique disponible


def build_window_contexts(table: pd.DataFrame) -> dict[int, WindowContext]:
    windows = build_windows(table)
    out: dict[int, WindowContext] = {}
    for w in windows:
        train = table[table["ds"] <= w.train_end]
        g = train.groupby("unique_id")["y"]
        out[w.index] = WindowContext(
            index=w.index,
            cutoff=w.train_end,
            train_observations=g.size(),
            last_value=g.last(),
            mean_value=g.mean(),
        )
    return out


def load_repli_log() -> pd.DataFrame:
    """Événements de repli déjà survenus pendant le calcul d'origine."""
    if not LOG_PATH.exists():
        return pd.DataFrame(columns=["modele", "fenetre", "serie", "exception", "raison"])
    events = [json.loads(l) for l in LOG_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
    replis = [e for e in events if e.get("type") == "repli"]
    return pd.DataFrame(replis) if replis else pd.DataFrame(
        columns=["modele", "fenetre", "serie", "exception", "raison"]
    )


def load_model_window_summaries() -> pd.DataFrame:
    events = [json.loads(l) for l in LOG_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
    return pd.DataFrame([e for e in events if e.get("type") == "resume_modele_fenetre"])


def classify_checkpoint(
    df: pd.DataFrame,
    model_name: str,
    window_idx: int,
    ctx: WindowContext,
    repli_log: pd.DataFrame,
) -> pd.DataFrame:
    """Classifie chaque ligne : succès natif, repli historique/exception/budget/cold-start."""
    out = df.copy()
    out["model_requested"] = model_name
    out["window"] = window_idx
    out["cutoff"] = ctx.cutoff
    out["train_observations"] = out["unique_id"].map(ctx.train_observations).fillna(0).astype(int)

    is_finite_raw = np.isfinite(out["y_pred_raw"].astype(float))
    is_cold_start = out["train_observations"] == 0

    # Replis déjà survenus pendant le calcul d'origine (exception/budget),
    # identifiés par le journal — leur y_pred_raw est déjà une valeur Naive
    # finie, indiscernable d'un succès natif sans cette jointure.
    win_repli = repli_log[(repli_log["modele"] == model_name) & (repli_log["fenetre"] == window_idx)]
    exception_series = set(win_repli.loc[win_repli["raison"] == "exception_modele", "serie"])
    budget_series = set(win_repli.loc[win_repli["raison"] == "budget_temps_depasse", "serie"])
    exception_reason = dict(zip(win_repli["serie"], win_repli["exception"]))

    is_exception = out["unique_id"].isin(exception_series)
    is_budget = out["unique_id"].isin(budget_series)

    n = len(out)
    status = np.full(n, "success_valid_prediction", dtype=object)
    fallback_type = np.full(n, None, dtype=object)
    fallback_reason = np.full(n, None, dtype=object)
    model_effective = np.full(n, model_name, dtype=object)
    y_pred_final = out["y_pred_raw"].to_numpy(dtype=float).copy()

    # --- Cas B : produit absent du train (priorité la plus haute) ---------
    status[is_cold_start.to_numpy()] = "cold_start_fallback"
    fallback_type[is_cold_start.to_numpy()] = "cold_start_zero"
    fallback_reason[is_cold_start.to_numpy()] = "produit_absent_du_train"
    model_effective[is_cold_start.to_numpy()] = "ColdStartZero"
    y_pred_final[is_cold_start.to_numpy()] = 0.0

    # --- Replis déjà journalisés (exception / budget), hors cold-start ----
    m_exc = is_exception.to_numpy() & ~is_cold_start.to_numpy()
    status[m_exc] = "exception_fallback"
    fallback_type[m_exc] = "exception_fallback"
    for idx in np.flatnonzero(m_exc):
        fallback_reason[idx] = f"exception: {exception_reason.get(out['unique_id'].iloc[idx], '?')}"
    model_effective[m_exc] = "Naive"

    m_bud = is_budget.to_numpy() & ~is_cold_start.to_numpy() & ~m_exc
    status[m_bud] = "budget_fallback"
    fallback_type[m_bud] = "budget_fallback"
    fallback_reason[m_bud] = "budget_temps_depasse"
    model_effective[m_bud] = "Naive"

    # --- Cas A : historique insuffisant (NaN/Inf silencieux, non journalisé) --
    m_silent = (~is_finite_raw.to_numpy()) & ~is_cold_start.to_numpy() & ~m_exc & ~m_bud
    for idx in np.flatnonzero(m_silent):
        uid = out["unique_id"].iloc[idx]
        n_obs = int(out["train_observations"].iloc[idx])
        if model_name == "SeasonalNaive7" and n_obs < SEASONALITY:
            model_effective[idx] = "Naive"
            y_pred_final[idx] = ctx.last_value.get(uid, 0.0)
            fallback_reason[idx] = f"seasonal_naive_historique_insuffisant(n={n_obs}<7)"
        elif model_name == "WindowAverage28" and n_obs < 28:
            mean_v = ctx.mean_value.get(uid, np.nan)
            if np.isfinite(mean_v):
                model_effective[idx] = "AvailableHistoryAverage"
                y_pred_final[idx] = float(mean_v)
                fallback_reason[idx] = f"window_average_historique_insuffisant(n={n_obs}<28)"
            else:
                model_effective[idx] = "Naive"
                y_pred_final[idx] = ctx.last_value.get(uid, 0.0)
                fallback_reason[idx] = f"window_average_moyenne_non_finie_repli_naive(n={n_obs})"
        else:
            model_effective[idx] = "Naive"
            y_pred_final[idx] = ctx.last_value.get(uid, 0.0)
            fallback_reason[idx] = f"prediction_non_finie_repli_naive(n={n_obs})"
        status[idx] = "success_invalid_prediction_fallback"
        fallback_type[idx] = "historique_insuffisant"

    out["status"] = status
    out["fallback_type"] = fallback_type
    out["fallback_reason"] = fallback_reason
    out["model_effective"] = model_effective
    out["fallback_applied"] = out["status"] != "success_valid_prediction"
    out["y_pred_final"] = np.clip(y_pred_final, 0, None)  # clipping final, jamais négatif

    return out[
        ["unique_id", "ds", "y", "y_pred_raw", "y_pred_final", "model_requested", "model_effective",
         "fallback_applied", "fallback_type", "fallback_reason", "train_observations", "window", "cutoff",
         "status"]
    ]


def run_postprocess(table: pd.DataFrame) -> pd.DataFrame:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    OPERATIONAL_DIR.mkdir(parents=True, exist_ok=True)

    contexts = build_window_contexts(table)
    repli_log = load_repli_log()

    all_operational: list[pd.DataFrame] = []
    for src in sorted(CHECKPOINT_DIR.glob("*.parquet")):
        # Preuve d'immutabilité : copie binaire exacte, jamais réécrite.
        dst = RAW_DIR / src.name
        if not dst.exists():
            shutil.copy2(src, dst)

        df = pd.read_parquet(src)
        model_name = df["modele"].iloc[0]
        window_idx = int(df["fenetre"].iloc[0])
        ctx = contexts[window_idx]

        operational = classify_checkpoint(df, model_name, window_idx, ctx, repli_log)
        operational.to_parquet(OPERATIONAL_DIR / src.name, index=False)
        all_operational.append(operational)

    return pd.concat(all_operational, ignore_index=True)


def assert_no_non_finite(df: pd.DataFrame) -> None:
    bad = ~np.isfinite(df["y_pred_final"].astype(float))
    if bad.any():
        raise ValueError(
            f"{int(bad.sum())} valeur(s) non finie(s) dans y_pred_final après repli — "
            f"exemples : {df.loc[bad, ['model_requested', 'window', 'unique_id']].head(5).to_dict('records')}"
        )


def main() -> pd.DataFrame:
    table = pd.read_parquet(PROJECT_ROOT / "data" / "processed" / "table_analytique.parquet")
    table["ds"] = pd.to_datetime(table["ds"])
    operational = run_postprocess(table)
    assert_no_non_finite(operational)
    logger.info(
        "Post-traitement terminé : %s lignes opérationnelles, 0 valeur non finie restante.",
        f"{len(operational):,}",
    )
    return operational


if __name__ == "__main__":
    main()
