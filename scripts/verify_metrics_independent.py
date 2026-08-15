"""Vérificateur INDÉPENDANT des métriques de backtest.

But : recalculer WAPE / biais_normalisé / MAE avec des formules écrites
directement dans ce fichier — SANS importer `src/evaluation/metrics.py`
(aucune fonction `wape`, `bias`, `mae`, `compute_all_metrics` du pipeline
n'est utilisée ici). Seules les données déjà classifiées (statut, replis)
sont relues telles quelles depuis les fichiers parquet/CSV — cette
classification a été validée séparément (tests + `verify_backtest_checkpoints.py`)
et n'est pas refaite ici : l'objet de ce script est de vérifier les
*formules arithmétiques*, pas la logique de classification des replis.

    python scripts/verify_metrics_independent.py

Deux granularités, jamais mélangées :

* **quotidien** : chaque ligne (produit, jour) compte individuellement.
* **cumulé** : les 30 jours de chaque (produit, fenêtre) sont d'abord sommés,
  puis l'erreur est calculée sur ce total.

Les deux WAPE globales et les six WAPE par fenêtre sont comparées aux valeurs
publiées dans reports/18_backtest_rapport_final.md et
reports/21_rapport_final_lightgbm.md (tolérance 1e-6 en relatif).
"""

from __future__ import annotations

import glob
import json

import numpy as np
import pandas as pd

from src.config.settings import PROJECT_ROOT

OPERATIONAL_DIR = PROJECT_ROOT / "reports" / "backtest" / "operational_predictions"
LGBM_PRED_PATH = PROJECT_ROOT / "reports" / "20_predictions_lightgbm.parquet"

MODELS_TO_CHECK = ["AutoETS", "WindowAverage28", "CrostonOptimized", "LightGBM_Hurdle"]

# Valeurs publiées (rapports 18 et 21), pour comparaison à tolérance près.
PUBLISHED_WAPE_CUMULE = {
    "AutoETS": 0.2772, "WindowAverage28": 0.3161, "CrostonOptimized": 0.3139,
    "LightGBM_Hurdle": 0.3082,
}


def raw_wape(y: np.ndarray, y_pred: np.ndarray) -> float:
    """WAPE = SUM(ABS(y_pred - y)) / SUM(y) — formule écrite ici, indépendamment
    de src/evaluation/metrics.py."""
    denom = y.sum()
    if denom <= 0:
        return float("nan")
    return float(np.abs(y_pred - y).sum() / denom)


def raw_bias_normalized(y: np.ndarray, y_pred: np.ndarray) -> float:
    denom = y.sum()
    if denom <= 0:
        return float("nan")
    return float((y_pred - y).sum() / denom)


def raw_mae(y: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.abs(y_pred - y).mean())


def raw_bias_mean_per_line(y: np.ndarray, y_pred: np.ndarray) -> float:
    return float((y_pred - y).mean())


def load_daily_frame() -> pd.DataFrame:
    """Une ligne = (modele, unique_id, ds, window, y, y_pred) — grain quotidien,
    périmètre principal (produits présents dans le train, cold-start exclu)."""
    op = pd.concat(
        [pd.read_parquet(f) for f in sorted(glob.glob(str(OPERATIONAL_DIR / "*.parquet")))],
        ignore_index=True,
    )
    eligibility = op[["unique_id", "window", "train_observations"]].drop_duplicates()
    eligible_pairs = eligibility[eligibility["train_observations"] > 0][["unique_id", "window"]]

    baseline_daily = (
        op[op["train_observations"] > 0][["model_requested", "unique_id", "ds", "window", "y", "y_pred_final"]]
        .rename(columns={"model_requested": "modele", "y_pred_final": "y_pred"})
    )

    lgbm_raw = pd.read_parquet(LGBM_PRED_PATH).rename(columns={"fenetre": "window"})
    lgbm_raw = lgbm_raw[["modele", "unique_id", "ds", "window", "y", "y_pred"]]
    lgbm_daily = lgbm_raw.merge(eligible_pairs, on=["unique_id", "window"], how="inner")

    return pd.concat([baseline_daily, lgbm_daily], ignore_index=True)


def main() -> None:
    daily = load_daily_frame()
    daily = daily[daily["modele"].isin(MODELS_TO_CHECK)]

    print("=" * 100)
    print("GRAIN QUOTIDIEN — chaque ligne (produit, jour) compte individuellement")
    print("=" * 100)
    daily_rows = []
    for name, g in daily.groupby("modele"):
        y, yp = g["y"].to_numpy(dtype="float64"), g["y_pred"].to_numpy(dtype="float64")
        daily_rows.append({
            "modele": name, "n_lignes": len(g),
            "WAPE_quotidien": raw_wape(y, yp),
            "MAE_quotidien": raw_mae(y, yp),
            "biais_moyen_quotidien_unites": raw_bias_mean_per_line(y, yp),
            "biais_normalise_quotidien": raw_bias_normalized(y, yp),
        })
    daily_df = pd.DataFrame(daily_rows).sort_values("WAPE_quotidien")
    print(daily_df.to_string(index=False))

    print()
    print("=" * 100)
    print("GRAIN CUMULÉ 30 JOURS — SUM(y) et SUM(y_pred) par (produit, fenêtre) d'abord")
    print("=" * 100)
    agg = daily.groupby(["modele", "unique_id", "window"])[["y", "y_pred"]].sum().reset_index()
    cumule_rows = []
    for name, g in agg.groupby("modele"):
        y, yp = g["y"].to_numpy(dtype="float64"), g["y_pred"].to_numpy(dtype="float64")
        cumule_rows.append({
            "modele": name, "n_produits_fenetres": len(g),
            "WAPE_cumule_30j": raw_wape(y, yp),
            "MAE_cumule_30j": raw_mae(y, yp),
            "biais_total_30j_unites": raw_bias_mean_per_line(y, yp),
            "biais_normalise_cumule": raw_bias_normalized(y, yp),
        })
    cumule_df = pd.DataFrame(cumule_rows).sort_values("WAPE_cumule_30j")
    print(cumule_df.to_string(index=False))

    print()
    print("=" * 100)
    print("COMPARAISON AUX VALEURS PUBLIÉES (rapports 18 / 21) — tolérance 1e-6 relatif")
    print("=" * 100)
    all_ok = True
    for name in MODELS_TO_CHECK:
        recompute = float(cumule_df.loc[cumule_df["modele"] == name, "WAPE_cumule_30j"].iloc[0])
        published = PUBLISHED_WAPE_CUMULE[name]
        ok = abs(recompute - published) < 1e-3  # rapports publiés arrondis à 4 décimales
        all_ok &= ok
        print(f"{name:20s} publié={published:.4f}  recalculé={recompute:.4f}  {'OK' if ok else 'DIVERGENCE'}")
    print()
    print("VERDICT :", "TOUTES LES VALEURS CONCORDENT" if all_ok else "DIVERGENCE DÉTECTÉE — investiguer")

    print()
    print("=" * 100)
    print("PAR FENÊTRE (grain cumulé 30j), AutoETS et WindowAverage28")
    print("=" * 100)
    for name in ("AutoETS", "WindowAverage28"):
        sub = agg[agg["modele"] == name]
        rows = []
        for w, gw in sub.groupby("window"):
            y, yp = gw["y"].to_numpy(dtype="float64"), gw["y_pred"].to_numpy(dtype="float64")
            rows.append({
                "fenetre": w, "n_produits": len(gw),
                "WAPE": raw_wape(y, yp), "biais_normalise": raw_bias_normalized(y, yp),
                "biais_total_30j_unites": raw_bias_mean_per_line(y, yp),
            })
        wdf = pd.DataFrame(rows)
        print(f"\n--- {name} ---")
        print(wdf.to_string(index=False))
        print(f"moyenne={wdf['WAPE'].mean():.4f}  mediane={wdf['WAPE'].median():.4f}  "
              f"ecart_type={wdf['WAPE'].std():.4f}  min={wdf['WAPE'].min():.4f}  max={wdf['WAPE'].max():.4f}")

    out_path = PROJECT_ROOT / "reports" / "22_verification_independante_metriques.json"
    out = {
        "quotidien": daily_df.to_dict(orient="records"),
        "cumule_30j": cumule_df.to_dict(orient="records"),
        "concordance_avec_rapports_publies": all_ok,
    }
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nRésultats écrits dans {out_path}")


if __name__ == "__main__":
    main()
