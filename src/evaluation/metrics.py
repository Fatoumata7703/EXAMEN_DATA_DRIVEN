"""Métriques de prévision.

Choix méthodologiques :

* **MAPE n'est jamais utilisée seule** : elle explose dès qu'une vente réelle
  vaut 0, ce qui est fréquent en demande intermittente. Elle est fournie
  uniquement à titre indicatif, calculée sur le sous-ensemble ``y > 0``.
* **WAPE** (erreur absolue rapportée au volume total) est la métrique de
  référence pour agréger sur un portefeuille de produits hétérogènes.
* **MASE** rapporte l'erreur à celle d'une prévision naïve saisonnière estimée
  **sur la période d'entraînement uniquement** — jamais sur le test, sous peine
  de fuite.
"""

from __future__ import annotations

from typing import Iterable, Sequence

import numpy as np
import pandas as pd

EPS = 1e-9


def _to_array(values: Iterable[float]) -> np.ndarray:
    return np.asarray(values, dtype="float64")


# ---------------------------------------------------------------------------
# Métriques élémentaires
# ---------------------------------------------------------------------------
def mae(y_true: Iterable[float], y_pred: Iterable[float]) -> float:
    yt, yp = _to_array(y_true), _to_array(y_pred)
    return float(np.mean(np.abs(yt - yp)))


def rmse(y_true: Iterable[float], y_pred: Iterable[float]) -> float:
    yt, yp = _to_array(y_true), _to_array(y_pred)
    return float(np.sqrt(np.mean((yt - yp) ** 2)))


def wape(y_true: Iterable[float], y_pred: Iterable[float]) -> float:
    """Weighted Absolute Percentage Error = somme|erreur| / somme|réel|."""
    yt, yp = _to_array(y_true), _to_array(y_pred)
    denom = np.sum(np.abs(yt))
    if denom < EPS:
        return float("nan")
    return float(np.sum(np.abs(yt - yp)) / denom)


def smape(y_true: Iterable[float], y_pred: Iterable[float]) -> float:
    """sMAPE symétrique, bornée à 200 % ; les points 0/0 sont comptés 0."""
    yt, yp = _to_array(y_true), _to_array(y_pred)
    denom = (np.abs(yt) + np.abs(yp)) / 2.0
    ratio = np.where(denom < EPS, 0.0, np.abs(yt - yp) / np.where(denom < EPS, 1.0, denom))
    return float(np.mean(ratio))


def mape_positive_only(y_true: Iterable[float], y_pred: Iterable[float]) -> float:
    """MAPE restreinte aux points réels strictement positifs (indicative)."""
    yt, yp = _to_array(y_true), _to_array(y_pred)
    mask = np.abs(yt) > EPS
    if not mask.any():
        return float("nan")
    return float(np.mean(np.abs((yt[mask] - yp[mask]) / yt[mask])))


def bias(y_true: Iterable[float], y_pred: Iterable[float]) -> float:
    """Biais moyen signé : positif = sur-prévision."""
    yt, yp = _to_array(y_true), _to_array(y_pred)
    return float(np.mean(yp - yt))


def relative_bias(y_true: Iterable[float], y_pred: Iterable[float]) -> float:
    """Biais rapporté au volume réel total (comparable entre produits)."""
    yt, yp = _to_array(y_true), _to_array(y_pred)
    denom = np.sum(np.abs(yt))
    if denom < EPS:
        return float("nan")
    return float(np.sum(yp - yt) / denom)


def under_forecast_rate(y_true: Iterable[float], y_pred: Iterable[float]) -> float:
    """Part des points où la prévision est strictement inférieure au réel."""
    yt, yp = _to_array(y_true), _to_array(y_pred)
    if yt.size == 0:
        return float("nan")
    return float(np.mean(yp < yt))


def over_forecast_rate(y_true: Iterable[float], y_pred: Iterable[float]) -> float:
    yt, yp = _to_array(y_true), _to_array(y_pred)
    if yt.size == 0:
        return float("nan")
    return float(np.mean(yp > yt))


def naive_scale(y_train: Iterable[float], seasonality: int = 1) -> float:
    """Dénominateur de la MASE : MAE de la naïve (saisonnière) sur l'entraînement."""
    y = _to_array(y_train)
    if y.size <= seasonality:
        return float("nan")
    diffs = np.abs(y[seasonality:] - y[:-seasonality])
    scale = float(np.mean(diffs))
    return scale if scale > EPS else float("nan")


def mase(
    y_true: Iterable[float],
    y_pred: Iterable[float],
    y_train: Iterable[float],
    seasonality: int = 1,
) -> float:
    """MASE : MAE du modèle / MAE de la naïve saisonnière **sur l'entraînement**."""
    scale = naive_scale(y_train, seasonality)
    if not np.isfinite(scale):
        return float("nan")
    return mae(y_true, y_pred) / scale


def naive_scale_squared(y_train: Iterable[float], seasonality: int = 1) -> float:
    """Dénominateur de la RMSSE : RMSE de la naïve (saisonnière) sur l'entraînement."""
    y = _to_array(y_train)
    if y.size <= seasonality:
        return float("nan")
    diffs = y[seasonality:] - y[:-seasonality]
    scale = float(np.sqrt(np.mean(diffs**2)))
    return scale if scale > EPS else float("nan")


def rmsse(
    y_true: Iterable[float],
    y_pred: Iterable[float],
    y_train: Iterable[float],
    seasonality: int = 1,
) -> float:
    """RMSSE : RMSE du modèle / RMSE de la naïve saisonnière **sur l'entraînement**."""
    scale = naive_scale_squared(y_train, seasonality)
    if not np.isfinite(scale):
        return float("nan")
    return rmse(y_true, y_pred) / scale


def asymmetric_cost(
    y_true: Iterable[float], y_pred: Iterable[float], under_weight: float = 1.5
) -> float:
    """Coût moyen pénalisant la sous-prévision ``under_weight`` fois plus que
    la sur-prévision (une rupture coûte généralement plus cher qu'un surstock).
    """
    yt, yp = _to_array(y_true), _to_array(y_pred)
    under = np.maximum(yt - yp, 0.0) * under_weight
    over = np.maximum(yp - yt, 0.0)
    return float(np.mean(under + over))


# ---------------------------------------------------------------------------
# Agrégation
# ---------------------------------------------------------------------------
def compute_all_metrics(
    y_true: Iterable[float],
    y_pred: Iterable[float],
    y_train: Iterable[float] | None = None,
    seasonality: int = 7,
    revenue_weight: Iterable[float] | None = None,
) -> dict[str, float]:
    """Toutes les métriques du cahier des charges pour un couple (réel, prévu)."""
    yt, yp = _to_array(y_true), _to_array(y_pred)
    out: dict[str, float] = {
        "n_points": float(yt.size),
        "volume_reel": float(np.sum(yt)),
        "volume_prevu": float(np.sum(yp)),
        "MAE": mae(yt, yp),
        "RMSE": rmse(yt, yp),
        "WAPE": wape(yt, yp),
        "sMAPE": smape(yt, yp),
        "MAPE_pos": mape_positive_only(yt, yp),
        "biais": bias(yt, yp),
        "biais_relatif": relative_bias(yt, yp),
        "taux_sous_prevision": under_forecast_rate(yt, yp),
        "taux_sur_prevision": over_forecast_rate(yt, yp),
        "cout_asymetrique_1_5x": asymmetric_cost(yt, yp, 1.5),
        "cout_asymetrique_2x": asymmetric_cost(yt, yp, 2.0),
    }
    if y_train is not None:
        out["MASE"] = mase(yt, yp, y_train, seasonality)
        out["MASE_naive1"] = mase(yt, yp, y_train, 1)
        out["RMSSE"] = rmsse(yt, yp, y_train, seasonality)
    if revenue_weight is not None:
        w = _to_array(revenue_weight)
        denom = np.sum(w)
        out["MAE_pondere_CA"] = (
            float(np.sum(w * np.abs(yt - yp)) / denom) if denom > EPS else float("nan")
        )
    return out


def metrics_by_group(
    df: pd.DataFrame,
    group_cols: Sequence[str],
    y_col: str = "y",
    pred_col: str = "y_pred",
    train_scales: pd.Series | None = None,
    id_col: str = "unique_id",
) -> pd.DataFrame:
    """Métriques calculées par groupe (produit, catégorie, horizon, classe ABC...).

    ``train_scales`` : série indexée par ``id_col`` donnant le dénominateur MASE
    calculé sur l'entraînement. Indispensable pour éviter toute fuite.
    """
    rows: list[dict[str, object]] = []
    for keys, chunk in df.groupby(list(group_cols), dropna=False):
        keys_tuple = keys if isinstance(keys, tuple) else (keys,)
        metrics = compute_all_metrics(chunk[y_col], chunk[pred_col])
        if train_scales is not None and id_col in chunk.columns:
            scales = chunk[id_col].map(train_scales)
            valid = scales.notna() & (scales > EPS)
            if valid.any():
                abs_err = (chunk[y_col] - chunk[pred_col]).abs()
                metrics["MASE"] = float((abs_err[valid] / scales[valid]).mean())
            else:
                metrics["MASE"] = float("nan")
        rows.append({**dict(zip(group_cols, keys_tuple)), **metrics})
    result = pd.DataFrame(rows)
    return result.sort_values("volume_reel", ascending=False) if "volume_reel" in result else result


def compute_train_scales(
    train: pd.DataFrame,
    id_col: str = "unique_id",
    y_col: str = "y",
    seasonality: int = 7,
) -> pd.Series:
    """Dénominateur MASE par série, calculé **uniquement** sur l'entraînement."""
    return train.groupby(id_col)[y_col].apply(lambda s: naive_scale(s.to_numpy(), seasonality))


def summarize_comparison(results: pd.DataFrame, model_col: str = "model") -> pd.DataFrame:
    """Classement des modèles : WAPE croissante (métrique de sélection)."""
    if results.empty:
        return results
    sort_col = "WAPE" if "WAPE" in results.columns else "MAE"
    return results.sort_values(sort_col, ascending=True).reset_index(drop=True)
