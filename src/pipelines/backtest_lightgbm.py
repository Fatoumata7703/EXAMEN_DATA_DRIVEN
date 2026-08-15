"""Backtest des modèles LightGBM candidats (phase 4) — stratégie récursive, sans fuite.

    python -m src.pipelines.backtest_lightgbm

Correction du 2026-08-14 : la version précédente construisait les retards de
`y` (lags/rolling) sur `train + test` concaténés, si bien que les prédictions
au-delà de J+1 utilisaient les **vraies** ventes de validation comme feature —
une fuite temporelle caractérisée. Un test qui ne vérifiait que la fonction de
construction statique (`build_features`) sur un historique isolé ne pouvait
pas la détecter : il fallait un test sur la **boucle complète à 30 jours**.

## Architecture retenue : stratégie récursive

Pour une prévision fixe faite au cutoff sur J+1..J+30 :

1. Le modèle est **entraîné** sur `train` seul, en walk-forward classique
   (chaque ligne historique utilise son propre passé — légitime, aucune fuite
   puisque tout est déjà observé).
2. La **prédiction** avance jour par jour : pour J+h, les variables
   historiques (lags, moyennes mobiles) sont recalculées à partir de
   l'historique réel jusqu'au cutoff **plus les prédictions déjà produites**
   pour J+1..J+h-1 — jamais les vraies valeurs de validation. Les variables
   futures connues (calendrier, promotion planifiée, prix, âge produit)
   varient normalement par jour, puisqu'elles sont réellement connues à
   l'avance.

## Stock : trois scénarios, jamais mélangés (cf. reports/20_risque_stock.md)

* **A — benchmark principal (h=1..30)** : **aucune variable de stock**. C'est
  la seule façon d'éviter toute ambiguïté sur les jours J+2..J+30, pour
  lesquels aucune règle de projection du stock n'est validée.
* **B — analyse séparée, horizon 1 uniquement** : `stock_disponible_lag1` du
  cutoff (réellement connu, puisque c'est le stock de la veille du cutoff)
  utilisé pour prévoir uniquement J+1. Jamais comparé au benchmark principal.
* **C — scénario de stock projeté** : non réalisé, faute de règle de
  projection validée à partir de la seule information disponible au cutoff.
  Inventer une règle ad hoc serait une hypothèse de modélisation non
  justifiée — documenté comme tel plutôt que fabriqué.
"""

from __future__ import annotations

import json
import time
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from src.config.settings import PROJECT_ROOT, load_config
from src.evaluation.metrics import compute_all_metrics
from src.features.calendar import CALENDAR_FEATURE_COLUMNS, build_calendar_features
from src.pipelines.backtest_baselines import H, N_WINDOWS, build_windows
from src.utils.logging_utils import get_logger, setup_logging

logger = get_logger(__name__)

LAGS = [1, 2, 3, 7, 14, 21, 28, 56]
ROLLING_WINDOWS = [7, 14, 28, 56]
DIFF_LAGS = [7, 28]

LIGHTGBM_PARAMS = dict(
    learning_rate=0.05, num_leaves=63, min_data_in_leaf=40, feature_fraction=0.85,
    bagging_fraction=0.85, bagging_freq=1, lambda_l2=1.0, n_estimators=600,
    verbosity=-1, random_state=42,
)
CATEGORICAL_COLS = ["categorie", "marque", "portee_promo"]

# --- Classification explicite des variables (point 5) -----------------------
# Connues au cutoff (peuvent varier librement par jour futur, day J+1..J+30) :
FUTURE_KNOWN_COLS = [
    "categorie", "marque", "prix_catalogue", "prix_attendu", "en_promotion", "remise_pct",
    "n_promotions", "portee_promo", "age_produit_jours", "horizon",
] + list(CALENDAR_FEATURE_COLUMNS)
# Hypothèse explicite, documentée et non vérifiable techniquement ici : le
# calendrier promotionnel des 30 prochains jours est connu au moment de la
# prévision (`dim_promotion` est un plan, pas un historique). Si cette
# hypothèse ne tient pas en production, `en_promotion`/`remise_pct` doivent
# être neutralisées sur l'horizon — cf. scénario "sans promotions futures"
# dans le rapport.

# Inconnues au cutoff pour J+2..J+30 : jamais utilisées à leur vraie valeur de
# validation. Reconstruites récursivement (lags de `y`) ou entièrement
# exclues (stock, web, prix payé, remise appliquée — cf. docstring module).
HISTORICAL_COLS = (
    [f"lag_{l}" for l in LAGS]
    + [f"roll_{s}_{w}" for w in ROLLING_WINDOWS for s in ("mean", "std", "min", "max", "median", "sum")]
    + [f"diff_{d}" for d in DIFF_LAGS]
)
STOCK_COLS = ["stock_disponible_lag1", "indicateur_rupture_lag1", "indicateur_stock_faible_lag1"]


def _rolling_features(series: pd.Series, group: pd.Series) -> dict[str, pd.Series]:
    """Lags/rolling/diff pour une série `y` déjà indexée dans l'ordre chronologique
    par produit. Utilisé identiquement pour l'entraînement (walk-forward) et
    pour figer les features au cutoff (une seule évaluation, au dernier point)."""
    out: dict[str, pd.Series] = {}
    g = series.groupby(group)
    for lag in LAGS:
        out[f"lag_{lag}"] = g.shift(lag)
    for window in ROLLING_WINDOWS:
        shifted = g.shift(1)
        roll = shifted.groupby(group).rolling(window, min_periods=1)
        for stat in ("mean", "std", "min", "max", "median", "sum"):
            out[f"roll_{stat}_{window}"] = getattr(roll, stat)().reset_index(level=0, drop=True)
    for dlag in DIFF_LAGS:
        out[f"diff_{dlag}"] = g.shift(1) - g.shift(1 + dlag)
    return out


def build_training_matrix(train: pd.DataFrame) -> pd.DataFrame:
    """Matrice d'entraînement — walk-forward strict, calculée sur `train` SEUL
    (jamais sur train+test concaténés)."""
    df = train.sort_values(["unique_id", "ds"]).reset_index(drop=True).copy()
    for name, s in _rolling_features(df["y"], df["unique_id"]).items():
        df[name] = s
    cal = build_calendar_features(df["ds"])
    df = df.merge(cal, on="ds", how="left")
    if "age_produit_jours" not in df.columns and "date_debut_validite" in df.columns:
        df["age_produit_jours"] = (df["ds"] - df["date_debut_validite"]).dt.days.clip(lower=0)
    df["horizon"] = 0  # sans objet à l'entraînement ; présent pour la cohérence des colonnes
    return df.dropna(subset=[f"lag_{max(LAGS)}"])  # lignes avec historique suffisant uniquement


@dataclass
class ProductStaticAttrs:
    """Attributs futurs connus, indépendants du jour (catégorie, prix, etc.),
    et fenêtre promotionnelle par produit — pour construire les features
    futures de chaque jour de l'horizon sans jamais relire `table` au-delà
    du cutoff pour l'historique."""
    frame: pd.DataFrame  # index=unique_id


def recursive_predict(
    model,
    train: pd.DataFrame,
    products: list[str],
    cutoff: pd.Timestamp,
    horizon: int,
    future_known_by_day: pd.DataFrame,  # colonnes futures connues, une ligne par (unique_id, ds)
    feat_cols: list[str],
    cat_cols: list[str],
    cat_categories: dict[str, pd.CategoricalDtype],
    predict_fn=None,
) -> pd.DataFrame:
    """``predict_fn(feat_df[feat_cols]) -> dict`` avec au moins la clé
    ``y_pred`` ; peut ajouter ``proba`` (modèle hurdle) — colonnes supplémentaires
    conservées telles quelles dans la sortie. Par défaut : ``model.predict``."""
    if predict_fn is None:
        predict_fn = lambda X: {"y_pred": np.clip(model.predict(X), 0, None)}  # noqa: E731
    """Prédit J+1..J+horizon, jour par jour, en ne réutilisant **jamais** que
    les prédictions déjà produites pour reconstruire les lags — jamais les
    vraies valeurs de validation.
    """
    history = train[train["unique_id"].isin(products)][["unique_id", "ds", "y"]].copy()
    predictions = []

    for h in range(1, horizon + 1):
        day = cutoff + pd.Timedelta(days=h)
        hist_sorted = history.sort_values(["unique_id", "ds"])
        # Pour obtenir les features "au jour J+h" (lags/rolling excluant ce
        # jour), on ajoute une ligne sonde (uid, day, y=NaN) à l'historique
        # connu, on recalcule les rolling sur l'ensemble, et on lit cette
        # ligne — le NaN de la sonde n'entre dans aucun `shift(>=1)`.
        probe = pd.DataFrame({"unique_id": products, "ds": day, "y": np.nan})
        combined = pd.concat([hist_sorted, probe], ignore_index=True).sort_values(["unique_id", "ds"])
        roll2 = _rolling_features(combined["y"], combined["unique_id"])
        probe_mask = combined["ds"] == day
        feat_df = combined.loc[probe_mask, ["unique_id", "ds"]].copy()
        for name, s in roll2.items():
            feat_df[name] = s[probe_mask].to_numpy()

        fk = future_known_by_day[future_known_by_day["ds"] == day]
        feat_df = feat_df.merge(fk, on=["unique_id", "ds"], how="left")
        feat_df["horizon"] = h

        for c in cat_cols:
            feat_df[c] = pd.Categorical(feat_df[c], categories=cat_categories[c])
        for c in feat_cols:
            if c not in feat_df.columns:
                feat_df[c] = np.nan

        result = predict_fn(feat_df[feat_cols])
        for key, values in result.items():
            feat_df[key] = values
        keep_cols = ["unique_id", "ds"] + list(result.keys())
        predictions.append(feat_df[keep_cols])

        # Les prédictions du jour deviennent les "observations" pour le pas
        # suivant — jamais les vraies valeurs de test.
        history = pd.concat(
            [history, pd.DataFrame({"unique_id": feat_df["unique_id"], "ds": day, "y": result["y_pred"]})],
            ignore_index=True,
        )

    return pd.concat(predictions, ignore_index=True)


def build_future_known(table: pd.DataFrame, test_dates: pd.DatetimeIndex, products: list[str]) -> pd.DataFrame:
    """Variables futures connues pour chaque (produit, jour) de l'horizon —
    lues depuis `table` car ce sont, par hypothèse, des variables planifiées
    (calendrier, promotion planifiée, prix catalogue), jamais des résultats
    observés a posteriori."""
    sub = table[(table["unique_id"].isin(products)) & (table["ds"].isin(test_dates))].copy()
    cal = build_calendar_features(sub["ds"])
    sub = sub.merge(cal, on="ds", how="left", suffixes=("", "_cal"))
    if "age_produit_jours" not in sub.columns and "date_debut_validite" in sub.columns:
        sub["age_produit_jours"] = (sub["ds"] - sub["date_debut_validite"]).dt.days.clip(lower=0)
    cols = ["unique_id", "ds"] + [c for c in FUTURE_KNOWN_COLS if c in sub.columns and c != "horizon"]
    return sub[cols].drop_duplicates(subset=["unique_id", "ds"])


def feature_columns(df: pd.DataFrame, include_stock: bool = False) -> list[str]:
    cols = list(FUTURE_KNOWN_COLS) + list(HISTORICAL_COLS)
    if include_stock:
        cols += STOCK_COLS
    return [c for c in cols if c in df.columns]


def _fit_lgbm(train_df: pd.DataFrame, feat_cols: list[str], cat_cols: list[str], objective: str, tweedie_p: float = 1.1):
    import lightgbm as lgb

    params = dict(LIGHTGBM_PARAMS, objective=objective)
    if objective == "tweedie":
        params["tweedie_variance_power"] = tweedie_p
    for c in cat_cols:
        train_df[c] = train_df[c].astype("category")
    model = lgb.LGBMRegressor(**params)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model.fit(train_df[feat_cols], train_df["y"], categorical_feature=cat_cols)
    return model


def run_window_scenario_a(
    table: pd.DataFrame, spec, model_name: str, objective: str, log_path,
) -> pd.DataFrame:
    """Scénario A — benchmark principal, sans stock, stratégie récursive."""
    train_full = table[table["ds"] <= spec.train_end]
    train_mat = build_training_matrix(train_full)
    feat_cols = feature_columns(train_mat, include_stock=False)
    cat_cols = [c for c in CATEGORICAL_COLS if c in feat_cols]
    cat_categories = {c: train_mat[c].astype("category").cat.categories for c in cat_cols}

    t0 = time.perf_counter()
    try:
        model = _fit_lgbm(train_mat.copy(), feat_cols, cat_cols, objective)
        status, exc = "succes", None
    except Exception as e:  # noqa: BLE001
        status, exc = "echec", f"{type(e).__name__}: {e}"
        model = None
    fit_duration = time.perf_counter() - t0

    test_dates = pd.date_range(spec.test_start, spec.test_end, freq="D")
    products = sorted(table.loc[(table["ds"] >= spec.test_start) & (table["ds"] <= spec.test_end), "unique_id"].unique())
    fk = build_future_known(table, test_dates, products)

    t1 = time.perf_counter()
    if model is not None:
        preds = recursive_predict(
            model, train_full, products, spec.train_end, len(test_dates), fk, feat_cols, cat_cols, cat_categories
        )
    else:
        preds = pd.DataFrame({"unique_id": [], "ds": [], "y_pred": []})
    predict_duration = time.perf_counter() - t1

    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "modele": model_name, "fenetre": spec.index, "statut": status, "exception": exc,
            "duree_fit_s": round(fit_duration, 2), "duree_predict_s": round(predict_duration, 2),
            "n_train": len(train_mat), "n_produits_test": len(products),
        }, ensure_ascii=False) + "\n")
    logger.info(
        "  [%s][A] fenêtre %d : %s (fit %.1fs, predict %.1fs, %d produits)",
        model_name, spec.index, status, fit_duration, predict_duration, len(products),
    )

    truth = table[(table["ds"] >= spec.test_start) & (table["ds"] <= spec.test_end)][["unique_id", "ds", "y"]]
    out = truth.merge(preds, on=["unique_id", "ds"], how="left")
    out["y_pred"] = out["y_pred"].fillna(0.0)
    out["modele"] = model_name
    out["fenetre"] = spec.index
    return out


# =============================================================================
# Modèle hurdle — évalué en deux parties (point 7)
# =============================================================================
def _fit_hurdle(train_df: pd.DataFrame, feat_cols: list[str], cat_cols: list[str]):
    import lightgbm as lgb

    for c in cat_cols:
        train_df[c] = train_df[c].astype("category")

    clf_params = dict(LIGHTGBM_PARAMS, objective="binary")
    clf = lgb.LGBMClassifier(**clf_params)
    reg_params = dict(LIGHTGBM_PARAMS, objective="regression")
    reg = lgb.LGBMRegressor(**reg_params)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        clf.fit(train_df[feat_cols], (train_df["y"] > 0).astype(int), categorical_feature=cat_cols)
        positive = train_df[train_df["y"] > 0]
        reg.fit(positive[feat_cols], positive["y"], categorical_feature=cat_cols)
    return clf, reg


def run_window_scenario_a_hurdle(table: pd.DataFrame, spec, model_name: str, log_path) -> pd.DataFrame:
    """Hurdle : `y_pred = P(y>0) x E(y|y>0)`, jamais binarisé par défaut.
    Conserve `proba` (sortie du classifieur) pour l'évaluation séparée §7."""
    train_full = table[table["ds"] <= spec.train_end]
    train_mat = build_training_matrix(train_full)
    feat_cols = feature_columns(train_mat, include_stock=False)
    cat_cols = [c for c in CATEGORICAL_COLS if c in feat_cols]
    cat_categories = {c: train_mat[c].astype("category").cat.categories for c in cat_cols}

    t0 = time.perf_counter()
    try:
        clf, reg = _fit_hurdle(train_mat.copy(), feat_cols, cat_cols)
        status, exc = "succes", None
    except Exception as e:  # noqa: BLE001
        status, exc = "echec", f"{type(e).__name__}: {e}"
        clf = reg = None
    fit_duration = time.perf_counter() - t0

    def predict_fn(X: pd.DataFrame) -> dict:
        proba = clf.predict_proba(X)[:, 1]
        conditional = np.clip(reg.predict(X), 0, None)
        return {"y_pred": np.clip(proba * conditional, 0, None), "proba": proba, "conditional": conditional}

    test_dates = pd.date_range(spec.test_start, spec.test_end, freq="D")
    products = sorted(table.loc[(table["ds"] >= spec.test_start) & (table["ds"] <= spec.test_end), "unique_id"].unique())
    fk = build_future_known(table, test_dates, products)

    t1 = time.perf_counter()
    if clf is not None:
        preds = recursive_predict(
            None, train_full, products, spec.train_end, len(test_dates), fk, feat_cols, cat_cols,
            cat_categories, predict_fn=predict_fn,
        )
    else:
        preds = pd.DataFrame({"unique_id": [], "ds": [], "y_pred": [], "proba": [], "conditional": []})
    predict_duration = time.perf_counter() - t1

    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "modele": model_name, "fenetre": spec.index, "statut": status, "exception": exc,
            "duree_fit_s": round(fit_duration, 2), "duree_predict_s": round(predict_duration, 2),
            "n_train": len(train_mat), "n_produits_test": len(products),
        }, ensure_ascii=False) + "\n")
    logger.info(
        "  [%s][A-hurdle] fenêtre %d : %s (fit %.1fs, predict %.1fs)",
        model_name, spec.index, status, fit_duration, predict_duration,
    )

    truth = table[(table["ds"] >= spec.test_start) & (table["ds"] <= spec.test_end)][["unique_id", "ds", "y"]]
    out = truth.merge(preds, on=["unique_id", "ds"], how="left")
    out["y_pred"] = out["y_pred"].fillna(0.0)
    out["proba"] = out["proba"].fillna(0.0)
    out["modele"] = model_name
    out["fenetre"] = spec.index
    return out


def evaluate_hurdle_classifier(out: pd.DataFrame, threshold: float = 0.5) -> dict:
    """Évaluation du classifieur `P(y>0)` — PR-AUC, Brier, log loss,
    calibration, précision/rappel à un seuil explicite. Utilise les vraies
    étiquettes de validation (`y > 0`) : légitime ici, puisqu'il s'agit de
    **scorer** le classifieur après coup, pas de le nourrir en feature."""
    from sklearn.metrics import (
        average_precision_score, brier_score_loss, log_loss,
        precision_score, recall_score, roc_auc_score,
    )

    y_true = (out["y"] > 0).astype(int)
    proba = out["proba"].clip(1e-6, 1 - 1e-6)
    if y_true.nunique() < 2:
        return {"PR_AUC": float("nan"), "ROC_AUC": float("nan"), "Brier": float("nan"),
                "log_loss": float("nan"), "precision": float("nan"), "recall": float("nan")}

    pred_bin = (out["proba"] >= threshold).astype(int)
    calib = (
        pd.DataFrame({"bucket": pd.cut(out["proba"], np.linspace(0, 1, 11)), "y": y_true})
        .groupby("bucket", observed=True)["y"].agg(["mean", "size"])
    )
    return {
        "PR_AUC": float(average_precision_score(y_true, proba)),
        "ROC_AUC": float(roc_auc_score(y_true, proba)),
        "Brier": float(brier_score_loss(y_true, proba)),
        "log_loss": float(log_loss(y_true, proba, labels=[0, 1])),
        "precision_at_threshold": float(precision_score(y_true, pred_bin, zero_division=0)),
        "recall_at_threshold": float(recall_score(y_true, pred_bin, zero_division=0)),
        "seuil": threshold,
        "calibration_par_decile": calib.to_dict(),
    }


# =============================================================================
# Cold-start LightGBM — comparé à ColdStartZero, moyenne catégorie, etc. (point 8)
# =============================================================================
def cold_start_baselines(
    table: pd.DataFrame, spec, cold_start_products: list[str],
) -> pd.DataFrame:
    """Stratégies de démarrage à froid n'utilisant QUE des attributs
    disponibles avant la prévision (catégorie, calendrier) — jamais un
    encodage arbitraire du nouveau `product_id`, qui introduirait une
    relation ordinale fictive entre des identifiants sans rapport."""
    train = table[table["ds"] <= spec.train_end]
    test = table[
        (table["ds"] >= spec.test_start) & (table["ds"] <= spec.test_end)
        & (table["unique_id"].isin(cold_start_products))
    ][["unique_id", "ds", "y", "categorie"]].copy()
    if test.empty:
        return pd.DataFrame()

    test["dow"] = test["ds"].dt.dayofweek
    train_cal = train.assign(dow=train["ds"].dt.dayofweek)

    cat_mean = train.groupby("categorie")["y"].mean()
    cat_dow_mean = train_cal.groupby(["categorie", "dow"])["y"].mean()
    global_mean = train["y"].mean()

    rows = []
    for name, pred in (
        ("ColdStartZero", pd.Series(0.0, index=test.index)),
        ("MoyenneCategorie", test["categorie"].map(cat_mean).fillna(global_mean)),
        ("MoyenneCategorieJourSemaine",
         pd.Series(
             [cat_dow_mean.get((c, d), cat_mean.get(c, global_mean)) for c, d in zip(test["categorie"], test["dow"])],
             index=test.index,
         )),
    ):
        met = compute_all_metrics(test["y"], pred)
        rows.append({"modele": name, "fenetre": spec.index, "n_lignes": len(test), **met})
    return pd.DataFrame(rows)


# =============================================================================
# Orchestration séquentielle (point 9) — mêmes 6 cutoffs, mêmes observations,
# checkpoints par (modèle, fenêtre), détection NaN/Inf, instrumentation du temps.
# =============================================================================
CHECKPOINT_DIR_LGBM = PROJECT_ROOT / "data" / "interim" / "backtest_lightgbm"
LOG_PATH_LGBM = PROJECT_ROOT / "reports" / "20_backtest_lightgbm_log.jsonl"


def main() -> None:
    cfg = load_config()
    setup_logging(level=cfg.get("logging.level", "INFO"))
    CHECKPOINT_DIR_LGBM.mkdir(parents=True, exist_ok=True)
    LOG_PATH_LGBM.write_text("", encoding="utf-8")

    table = pd.read_parquet(PROJECT_ROOT / "data" / "processed" / "table_analytique.parquet")
    table["ds"] = pd.to_datetime(table["ds"])
    windows = build_windows(table)

    runners = [
        ("LightGBM_direct", lambda t, w: run_window_scenario_a(t, w, "LightGBM_direct", "regression", LOG_PATH_LGBM)),
        ("LightGBM_Poisson", lambda t, w: run_window_scenario_a(t, w, "LightGBM_Poisson", "poisson", LOG_PATH_LGBM)),
        ("LightGBM_Tweedie", lambda t, w: run_window_scenario_a(t, w, "LightGBM_Tweedie", "tweedie", LOG_PATH_LGBM)),
        ("LightGBM_Hurdle", lambda t, w: run_window_scenario_a_hurdle(t, w, "LightGBM_Hurdle", LOG_PATH_LGBM)),
    ]

    all_predictions = []
    all_cold_start = []
    hurdle_eval_rows = []

    for model_name, runner in runners:
        for spec in windows:
            ckpt = CHECKPOINT_DIR_LGBM / f"fenetre{spec.index}_{model_name}.parquet"
            if ckpt.exists():
                logger.info("  [%s] fenêtre %d : checkpoint existant, repris sans recalcul.", model_name, spec.index)
                out = pd.read_parquet(ckpt)
            else:
                out = runner(table, spec)
                bad = ~np.isfinite(out["y_pred"].astype(float))
                if bad.any():
                    raise ValueError(
                        f"{model_name} fenêtre {spec.index} : {int(bad.sum())} prédiction(s) non finie(s)."
                    )
                out.to_parquet(ckpt, index=False)

            all_predictions.append(out)

            if model_name == "LightGBM_Hurdle":
                hm = evaluate_hurdle_classifier(out)
                hm["fenetre"] = spec.index
                hurdle_eval_rows.append(hm)

            if model_name == runners[0][0]:  # une seule fois : cold-start indépendant du modèle
                train_products = set(table[table["ds"] <= spec.train_end]["unique_id"])
                test_products = set(table[(table["ds"] >= spec.test_start) & (table["ds"] <= spec.test_end)]["unique_id"])
                cold = list(test_products - train_products)
                csb = cold_start_baselines(table, spec, cold)
                if not csb.empty:
                    all_cold_start.append(csb)

    predictions = pd.concat(all_predictions, ignore_index=True)
    predictions.to_parquet(PROJECT_ROOT / "reports" / "20_predictions_lightgbm.parquet", index=False)

    if all_cold_start:
        pd.concat(all_cold_start, ignore_index=True).to_csv(
            PROJECT_ROOT / "reports" / "20_cold_start_lightgbm.csv", index=False
        )
    if hurdle_eval_rows:
        pd.DataFrame([{k: v for k, v in r.items() if k != "calibration_par_decile"} for r in hurdle_eval_rows]).to_csv(
            PROJECT_ROOT / "reports" / "20_hurdle_classifier_eval.csv", index=False
        )

    logger.info("Backtest LightGBM (scénario A) terminé : %s lignes.", f"{len(predictions):,}")


if __name__ == "__main__":
    main()
