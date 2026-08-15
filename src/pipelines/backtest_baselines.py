"""Backtesting instrumenté des modèles de référence (phase 3).

    python -m src.pipelines.backtest_baselines

Modèles : Naive, SeasonalNaive(7), WindowAverage(28), AutoETS, AutoARIMA,
CrostonOptimized, TSB. Validation temporelle glissante, h=30, 6 fenêtres.

Garanties anti-fuite :
* chaque modèle est appelé série par série via ``.forecast(h=H, y=y_train)`` —
  jamais autre chose que l'historique d'entraînement (prouvé par
  `tests/test_statsforecast_no_peeking.py`) ;
* la segmentation (ABC, intermittence, produits récents) est recalculée à
  chaque fenêtre **sur le train de cette fenêtre uniquement** — jamais sur
  l'ensemble des données, sous peine de fuir la revalidation future dans les
  classes utilisées pour évaluer une fenêtre passée ;
* aucun repli silencieux : chaque échec est journalisé avec la série, le
  modèle, la fenêtre, l'exception et le modèle de remplacement.

Instrumentation :
* journal structuré par (fenêtre, modèle) : nombre de séries, succès, échecs,
  replis, durée — écrit en continu dans `reports/15_backtest_log.jsonl` ;
* checkpoint des prédictions après chaque (fenêtre, modèle) dans
  `data/interim/backtest/` — un échec tardif ne fait perdre que le travail en
  cours, jamais les fenêtres déjà terminées ;
* garde-fou de temps par (modèle, fenêtre) : au-delà de `TIME_BUDGET_SECONDS`,
  les séries restantes de ce modèle sur cette fenêtre basculent sur Naive,
  journalisées individuellement — les autres modèles et fenêtres continuent.
"""

from __future__ import annotations

import json
import time
import warnings
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from src.config.settings import PROJECT_ROOT, load_config
from src.evaluation.metrics import compute_all_metrics, naive_scale, naive_scale_squared
from src.features.segmentation import SegmentationConfig, classify, compute_series_features
from src.utils.logging_utils import get_logger, setup_logging

logger = get_logger(__name__)

H = 30
N_WINDOWS = 6
SEASONALITY = 7
TIME_BUDGET_SECONDS = 900.0  # par (modèle, fenêtre) ; cf. §"garde-fou" ci-dessus

CHECKPOINT_DIR = PROJECT_ROOT / "data" / "interim" / "backtest"
LOG_PATH = PROJECT_ROOT / "reports" / "15_backtest_log.jsonl"


def _model_factory():
    from statsforecast.models import (
        TSB,
        AutoARIMA,
        AutoETS,
        CrostonOptimized,
        Naive,
        SeasonalNaive,
        WindowAverage,
    )

    return [
        ("Naive", lambda: Naive()),
        ("SeasonalNaive7", lambda: SeasonalNaive(season_length=SEASONALITY)),
        ("WindowAverage28", lambda: WindowAverage(window_size=28)),
        ("AutoETS", lambda: AutoETS(season_length=SEASONALITY)),
        ("AutoARIMA", lambda: AutoARIMA(season_length=SEASONALITY)),
        ("CrostonOptimized", lambda: CrostonOptimized()),
        ("TSB", lambda: TSB(alpha_d=0.2, alpha_p=0.2)),
    ]


@dataclass
class WindowSpec:
    index: int
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    n_train_days: int
    n_products_train: int
    n_products_test: int
    n_products_nouveaux: int  # apparus après le cutoff (absents du train)


def build_windows(table: pd.DataFrame) -> list[WindowSpec]:
    dmax = table["ds"].max()
    dmin = table["ds"].min()
    specs: list[WindowSpec] = []
    for w in range(N_WINDOWS, 0, -1):
        cutoff = dmax - pd.Timedelta(days=H * w)
        test_start = cutoff + pd.Timedelta(days=1)
        test_end = cutoff + pd.Timedelta(days=H)
        train = table[table["ds"] <= cutoff]
        test = table[(table["ds"] > cutoff) & (table["ds"] <= test_end)]
        if train.empty or test.empty:
            continue
        train_products = set(train["unique_id"])
        test_products = set(test["unique_id"])
        specs.append(
            WindowSpec(
                index=N_WINDOWS - w + 1,
                train_start=dmin,
                train_end=cutoff,
                test_start=test_start,
                test_end=test_end,
                n_train_days=(cutoff - dmin).days + 1,
                n_products_train=len(train_products),
                n_products_test=len(test_products),
                n_products_nouveaux=len(test_products - train_products),
            )
        )
    return specs


def _log_event(payload: dict) -> None:
    payload = {"ts": datetime.now(timezone.utc).isoformat(), **payload}
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")


def run_model_on_window(
    model_name: str,
    model_factory,
    train: pd.DataFrame,
    test_dates: pd.DatetimeIndex,
    window_index: int,
) -> tuple[pd.DataFrame, dict]:
    """Prévoit un modèle, série par série, avec repli et journalisation individuels."""
    series_ids = train["unique_id"].unique()
    rows: list[dict] = []
    n_success = n_fallback = n_budget_skip = 0
    t_start = time.perf_counter()
    budget_exhausted = False

    for uid in series_ids:
        y_train = train.loc[train["unique_id"] == uid].sort_values("ds")["y"].to_numpy()
        elapsed = time.perf_counter() - t_start

        if budget_exhausted or elapsed > TIME_BUDGET_SECONDS:
            budget_exhausted = True
            pred = np.repeat(y_train[-1] if len(y_train) else 0.0, H)
            n_budget_skip += 1
            _log_event(
                {
                    "type": "repli", "modele": model_name, "fenetre": window_index,
                    "serie": uid, "exception": None, "repli": "Naive",
                    "raison": "budget_temps_depasse",
                }
            )
        else:
            try:
                warnings.simplefilter("ignore")
                pred = np.asarray(model_factory().forecast(h=H, y=y_train)["mean"], dtype=float)
                n_success += 1
            except Exception as exc:  # noqa: BLE001
                pred = np.repeat(y_train[-1] if len(y_train) else 0.0, H)
                n_fallback += 1
                _log_event(
                    {
                        "type": "repli", "modele": model_name, "fenetre": window_index,
                        "serie": uid, "exception": f"{type(exc).__name__}: {exc}",
                        "repli": "Naive", "raison": "exception_modele",
                    }
                )
        rows.append({"unique_id": uid, "y_pred_raw": pred})

    duration = time.perf_counter() - t_start
    frame = pd.concat(
        [
            pd.DataFrame({"unique_id": r["unique_id"], "ds": test_dates, "y_pred_raw": r["y_pred_raw"]})
            for r in rows
        ],
        ignore_index=True,
    )
    summary = {
        "type": "resume_modele_fenetre",
        "modele": model_name,
        "fenetre": window_index,
        "n_series": len(series_ids),
        "n_succes": n_success,
        "n_repli_exception": n_fallback,
        "n_repli_budget": n_budget_skip,
        "duree_s": round(duration, 2),
        "budget_depasse": budget_exhausted,
    }
    _log_event(summary)
    logger.info(
        "  [%s] fenêtre %d : %d/%d séries OK, %d replis (exception), %d replis (budget) — %.1fs%s",
        model_name, window_index, n_success, len(series_ids), n_fallback, n_budget_skip, duration,
        " [BUDGET DÉPASSÉ]" if budget_exhausted else "",
    )
    return frame, summary


def run_backtest(table: pd.DataFrame) -> tuple[list[WindowSpec], pd.DataFrame, pd.DataFrame]:
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    windows = build_windows(table)
    all_predictions: list[pd.DataFrame] = []
    all_summaries: list[dict] = []
    all_segments: list[pd.DataFrame] = []

    for spec in windows:
        train = table[table["ds"] <= spec.train_end]
        test = table[(table["ds"] >= spec.test_start) & (table["ds"] <= spec.test_end)]
        test_dates = pd.date_range(spec.test_start, spec.test_end, freq="D")

        logger.info(
            "Fenêtre %d/%d : train %s->%s (%d j, %d produits) | test %s->%s "
            "(%d produits évalués, %d nouveaux post-cutoff)",
            spec.index, N_WINDOWS, spec.train_start.date(), spec.train_end.date(),
            spec.n_train_days, spec.n_products_train, spec.test_start.date(), spec.test_end.date(),
            spec.n_products_test, spec.n_products_nouveaux,
        )

        # Segmentation calculée SUR CE TRAIN UNIQUEMENT (jamais sur les données futures).
        features = compute_series_features(train)
        seg = classify(features, SegmentationConfig())
        seg["fenetre"] = spec.index
        all_segments.append(seg[["unique_id", "fenetre", "profil_demande", "statut", "classe_abc"]])

        for model_name, factory in _model_factory():
            preds, _ = run_model_on_window(model_name, factory, train, test_dates, spec.index)
            merged = test.merge(preds, on=["unique_id", "ds"], how="left")
            merged["modele"] = model_name
            merged["fenetre"] = spec.index

            ckpt = CHECKPOINT_DIR / f"fenetre{spec.index}_{model_name}.parquet"
            merged.to_parquet(ckpt, index=False)
            all_predictions.append(merged)

    predictions = pd.concat(all_predictions, ignore_index=True)
    segments = pd.concat(all_segments, ignore_index=True)
    return windows, predictions, segments


# ---------------------------------------------------------------------------
# Rapport
# ---------------------------------------------------------------------------
def build_report(
    windows: list[WindowSpec], predictions: pd.DataFrame, segments: pd.DataFrame, table: pd.DataFrame
) -> str:
    lines = ["# 15 — Backtest instrumenté des baselines (h=30, 6 fenêtres)", "",
             f"_Généré le {datetime.now(timezone.utc).isoformat()}._", ""]

    # --- Fenêtres --------------------------------------------------------
    lines += ["## Fenêtres exactes", "", "| # | fin entraînement | début validation | fin validation | "
              "historique (j) | produits évalués | dont nouveaux post-cutoff |", "|---|---|---|---|---|---|---|"]
    for w in windows:
        lines.append(
            f"| {w.index} | {w.train_end.date()} | {w.test_start.date()} | {w.test_end.date()} | "
            f"{w.n_train_days} | {w.n_products_test} | {w.n_products_nouveaux} |"
        )
    lines.append("")

    # --- Horizon cumulé par produit (métrique de sélection) --------------
    agg_h = (
        predictions.groupby(["modele", "fenetre", "unique_id"])[["y", "y_pred_raw"]]
        .sum()
        .reset_index()
    )
    zero_sum = agg_h[agg_h["y"] == 0]
    lines += [
        "## Séries à somme réelle nulle sur la fenêtre",
        "",
        f"{zero_sum[['unique_id','fenetre']].drop_duplicates().shape[0]} couple(s) "
        "(produit, fenêtre) à vente cumulée nulle sur l'horizon. Traitement : elles "
        "contribuent 0 au numérateur et 0 au dénominateur de la WAPE poolée (sans "
        "effet), mais leur WAPE **individuelle** est indéfinie (0/0) — exclues des "
        "moyennes par produit, comptées séparément, jamais assimilées à une erreur nulle.",
        "",
    ]

    # --- Clipping ----------------------------------------------------------
    lines += ["## Clipping (prévisions négatives)", "", "| modèle | n. négatives | min prédit | "
              "WAPE avant clip | WAPE après clip |", "|---|---:|---:|---:|---:|"]
    for name, g in predictions.groupby("modele"):
        n_neg = int((g["y_pred_raw"] < 0).sum())
        min_pred = float(g["y_pred_raw"].min())
        clipped = g["y_pred_raw"].clip(lower=0)
        wape_before = compute_all_metrics(g["y"], g["y_pred_raw"])["WAPE"]
        wape_after = compute_all_metrics(g["y"], clipped)["WAPE"]
        lines.append(f"| {name} | {n_neg} | {min_pred:.3f} | {wape_before:.4f} | {wape_after:.4f} |")
    lines.append("")
    predictions = predictions.assign(y_pred=predictions["y_pred_raw"].clip(lower=0))

    # --- Global (poolé, pas moyenne de WAPE) ------------------------------
    # Échelle MASE propre à chaque (produit, fenêtre) — jamais moyennée entre
    # fenêtres, sous peine de mélanger l'échelle d'entraînements différents.
    scale_by_window_product: dict[tuple[int, str], float] = {}
    scale_sq_by_window_product: dict[tuple[int, str], float] = {}
    for w in windows:
        train = table[table["ds"] <= w.train_end]
        s = train.groupby("unique_id")["y"].apply(lambda x: naive_scale(x.to_numpy(), SEASONALITY))
        s2 = train.groupby("unique_id")["y"].apply(lambda x: naive_scale_squared(x.to_numpy(), SEASONALITY))
        for uid, val in s.items():
            scale_by_window_product[(w.index, uid)] = val
        for uid, val in s2.items():
            scale_sq_by_window_product[(w.index, uid)] = val

    lines += ["## Résultats globaux — quantité cumulée par produit sur l'horizon (métrique de sélection)",
              "", "_WAPE globale = SUM(|y-ŷ|) / SUM(y) sur toutes les observations poolées, "
              "jamais la moyenne des WAPE individuelles. Échelle MASE propre à chaque (produit, fenêtre)._", ""]
    rows = []
    for name, g in predictions.groupby("modele"):
        agg = g.groupby(["unique_id", "fenetre"])[["y", "y_pred"]].sum().reset_index()
        agg["_scale"] = [
            scale_by_window_product.get((f, u), np.nan) for f, u in zip(agg["fenetre"], agg["unique_id"])
        ]
        agg["_scale_sq"] = [
            scale_sq_by_window_product.get((f, u), np.nan) for f, u in zip(agg["fenetre"], agg["unique_id"])
        ]
        met = compute_all_metrics(agg["y"], agg["y_pred"])
        valid = agg["_scale"].notna() & (agg["_scale"] > 1e-9)
        met["MASE"] = (
            float(((agg["y"] - agg["y_pred"]).abs()[valid] / agg["_scale"][valid]).mean())
            if valid.any() else float("nan")
        )
        valid_sq = agg["_scale_sq"].notna() & (agg["_scale_sq"] > 1e-9)
        met["RMSSE"] = (
            float(np.sqrt((((agg["y"] - agg["y_pred"]) ** 2)[valid_sq] / (agg["_scale_sq"][valid_sq] ** 2)).mean()))
            if valid_sq.any() else float("nan")
        )
        met["modele"] = name
        rows.append(met)
    resume_global = pd.DataFrame(rows).sort_values("WAPE")
    cols = ["modele", "WAPE", "MAE", "RMSE", "RMSSE", "MASE", "sMAPE", "biais", "biais_relatif",
            "taux_sous_prevision", "cout_asymetrique_1_5x", "cout_asymetrique_2x"]
    lines.append(resume_global[cols].to_markdown(index=False, floatfmt=".4f"))
    lines.append("")

    # --- Par fenêtre (stabilité) -------------------------------------------
    lines += ["## Stabilité par fenêtre", ""]
    rows = []
    for (name, fen), g in predictions.groupby(["modele", "fenetre"]):
        agg = g.groupby("unique_id")[["y", "y_pred"]].sum()
        met = compute_all_metrics(agg["y"], agg["y_pred"])
        met.update({"modele": name, "fenetre": fen})
        rows.append(met)
    par_fenetre = pd.DataFrame(rows)
    pivot = par_fenetre.pivot(index="modele", columns="fenetre", values="WAPE")
    pivot["ecart_type"] = pivot[list(range(1, len(windows) + 1))].std(axis=1)
    pivot = pivot.sort_values("ecart_type")
    lines.append(pivot.round(4).to_markdown())
    lines.append("")

    # --- Par catégorie, ABC, intermittence, récence, promo -----------------
    # `categorie` et `en_promotion` proviennent déjà de `test` (donc de
    # `predictions`) : pas besoin de les re-fusionner depuis `table`.
    joined = predictions.merge(segments, on=["unique_id", "fenetre"], how="left")

    for label, col in (
        ("catégorie", "categorie"), ("classe ABC (par fenêtre)", "classe_abc"),
        ("profil de demande (par fenêtre)", "profil_demande"), ("statut (par fenêtre)", "statut"),
        ("promotion", "en_promotion"),
    ):
        lines += [f"## Par {label}", "", "| modèle | " + col + " | WAPE | MAE | n |", "|---|---|---:|---:|---:|"]
        for (name, seg_val), g in joined.groupby(["modele", col], dropna=False):
            met = compute_all_metrics(g["y"], g["y_pred"])
            lines.append(f"| {name} | {seg_val} | {met['WAPE']:.4f} | {met['MAE']:.4f} | {len(g)} |")
        lines.append("")

    # --- Timing, échecs, replis ---------------------------------------------
    log_events = [json.loads(l) for l in LOG_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
    summaries = pd.DataFrame([e for e in log_events if e["type"] == "resume_modele_fenetre"])
    replis = pd.DataFrame([e for e in log_events if e["type"] == "repli"])

    lines += ["## Temps d'exécution et fiabilité", "", "| modèle | durée totale (s, 6 fenêtres) | "
              "séries OK | replis (exception) | replis (budget) | % replis |", "|---|---:|---:|---:|---:|---:|"]
    for name, g in summaries.groupby("modele"):
        n_tot = g["n_series"].sum()
        n_repli = g["n_repli_exception"].sum() + g["n_repli_budget"].sum()
        lines.append(
            f"| {name} | {g['duree_s'].sum():.1f} | {g['n_succes'].sum()} | "
            f"{g['n_repli_exception'].sum()} | {g['n_repli_budget'].sum()} | {100*n_repli/n_tot:.2f}% |"
        )
    lines.append("")

    if not replis.empty:
        lines += ["### Détail des replis (série, fenêtre, modèle, exception)", "",
                   replis[["modele", "fenetre", "serie", "exception", "repli", "raison"]]
                   .to_markdown(index=False), ""]
        for name, g in replis.groupby("modele"):
            n_tot = int(summaries[summaries.modele == name]["n_series"].sum())
            taux = 100 * len(g) / max(n_tot, 1)
            if taux > 5:
                lines.append(
                    f"> ⚠️ **{name}** : {taux:.1f}% de prédictions issues d'un repli Naive — "
                    "résultats à interpréter comme *Naive partiel*, pas comme le modèle nommé."
                )
    else:
        lines += ["_Aucun repli déclenché : tous les modèles ont convergé sur toutes les séries._", ""]

    # --- Synthèse finale ------------------------------------------------
    stat_models = {"AutoETS", "AutoARIMA", "CrostonOptimized", "TSB"}
    simple_models = {"Naive", "SeasonalNaive7", "WindowAverage28"}
    best_overall = resume_global.iloc[0]
    best_stat = resume_global[resume_global["modele"].isin(stat_models)].iloc[0]
    best_simple = resume_global[resume_global["modele"].isin(simple_models)].iloc[0]

    lines += [
        "## Synthèse",
        "",
        f"- **Meilleur modèle (toutes catégories) :** {best_overall['modele']} — WAPE {best_overall['WAPE']:.4f}",
        f"- **Meilleure baseline simple :** {best_simple['modele']} — WAPE {best_simple['WAPE']:.4f}",
        f"- **Meilleur modèle statistique :** {best_stat['modele']} — WAPE {best_stat['WAPE']:.4f}",
        "",
        f"**Seuil que LightGBM devra battre : WAPE < {best_overall['WAPE']:.4f}** "
        f"(modèle {best_overall['modele']}, métrique = quantité cumulée par produit sur h=30, poolée).",
        "",
        f"Fichiers de prédictions : `{CHECKPOINT_DIR.relative_to(PROJECT_ROOT)}/*.parquet` "
        f"({len(list(CHECKPOINT_DIR.glob('*.parquet')))} fichiers).",
        "",
        "Aucun modèle n'est sélectionné comme définitif à ce stade.",
    ]
    return "\n".join(lines)


def main() -> None:
    cfg = load_config()
    setup_logging(level=cfg.get("logging.level", "INFO"))
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text("", encoding="utf-8")  # nouvelle exécution : log frais

    table = pd.read_parquet(PROJECT_ROOT / "data" / "processed" / "table_analytique.parquet")
    table["ds"] = pd.to_datetime(table["ds"])

    windows, predictions, segments = run_backtest(table)
    report = build_report(windows, predictions, segments, table)
    (PROJECT_ROOT / "reports" / "15_backtest_baselines.md").write_text(report, encoding="utf-8")
    predictions.to_parquet(PROJECT_ROOT / "reports" / "15_predictions_completes.parquet", index=False)
    logger.info("Backtest terminé. Rapport : reports/15_backtest_baselines.md")


if __name__ == "__main__":
    main()
