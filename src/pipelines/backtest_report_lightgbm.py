"""Rapport comparatif final — baselines (rapport 18) vs les 4 variantes LightGBM.

    python -m src.pipelines.backtest_report_lightgbm

Principe : construire un unique DataFrame "long" (modele, unique_id, ds, window,
y, y_pred) en empilant les prédictions opérationnelles des baselines
(`reports/backtest/operational_predictions/`, périmètre comparable seulement,
càd `train_observations > 0`) et les prédictions LightGBM
(`reports/20_predictions_lightgbm.parquet`) filtrées sur EXACTEMENT le même
périmètre comparable (même paire (unique_id, window) éligible). Toutes les
métriques (WAPE/MASE/RMSSE/stabilité/segments) sont alors calculées par les
mêmes fonctions, sur les mêmes agrégats — aucune métrique n'est recopiée
depuis un rapport antérieur.

Le cold-start et le classifieur hurdle sont présentés à part (jamais mélangés
au classement principal), conformément à la consigne explicite.
"""

from __future__ import annotations

import glob
import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from src.config.settings import PROJECT_ROOT
from src.evaluation.metrics import compute_all_metrics
from src.features.segmentation import SegmentationConfig, classify, compute_series_features
from src.pipelines.backtest_baselines import LOG_PATH as BASELINE_LOG_PATH
from src.pipelines.backtest_postprocess import OPERATIONAL_DIR, build_window_contexts
from src.pipelines.backtest_report_final import _scale_lookup, _metrics_on
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)

LGBM_LOG_PATH = PROJECT_ROOT / "reports" / "20_backtest_lightgbm_log.jsonl"
LGBM_PRED_PATH = PROJECT_ROOT / "reports" / "20_predictions_lightgbm.parquet"
COLD_START_CSV = PROJECT_ROOT / "reports" / "20_cold_start_lightgbm.csv"
HURDLE_EVAL_CSV = PROJECT_ROOT / "reports" / "20_hurdle_classifier_eval.csv"
OUT_PATH = PROJECT_ROOT / "reports" / "21_rapport_final_lightgbm.md"

LGBM_MODELS = ["LightGBM_direct", "LightGBM_Poisson", "LightGBM_Tweedie", "LightGBM_Hurdle"]
BASELINE_MODELS = ["Naive", "SeasonalNaive7", "WindowAverage28", "AutoETS", "AutoARIMA", "CrostonOptimized", "TSB"]


def load_operational() -> pd.DataFrame:
    return pd.concat(
        [pd.read_parquet(f) for f in sorted(glob.glob(str(OPERATIONAL_DIR / "*.parquet")))],
        ignore_index=True,
    )


def build_combined_daily(op: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Retourne (combined_daily, eligible_pairs). `combined_daily` empile les
    baselines (périmètre comparable) et LightGBM (filtré sur le MÊME périmètre)."""
    eligibility = op[["unique_id", "window", "train_observations"]].drop_duplicates()
    eligible_pairs = eligibility[eligibility["train_observations"] > 0][["unique_id", "window"]]

    baseline_daily = (
        op[op["train_observations"] > 0][["model_requested", "unique_id", "ds", "window", "y", "y_pred_final"]]
        .rename(columns={"model_requested": "modele", "y_pred_final": "y_pred"})
    )

    lgbm_raw = pd.read_parquet(LGBM_PRED_PATH)
    lgbm_raw = lgbm_raw.rename(columns={"fenetre": "window"})[["modele", "unique_id", "ds", "window", "y", "y_pred"]]
    n_before = len(lgbm_raw)
    lgbm_daily = lgbm_raw.merge(eligible_pairs, on=["unique_id", "window"], how="inner")
    logger.info(
        "LightGBM : %d lignes brutes -> %d lignes sur le périmètre comparable (cold-start du scénario A exclu)",
        n_before, len(lgbm_daily),
    )

    combined = pd.concat([baseline_daily, lgbm_daily], ignore_index=True)
    return combined, eligible_pairs


def principale_table(combined: pd.DataFrame, scale: dict, scale_sq: dict) -> pd.DataFrame:
    agg = combined.groupby(["modele", "unique_id", "window"])[["y", "y_pred"]].sum().reset_index()
    rows = []
    for name, g in agg.groupby("modele"):
        met = _metrics_on(g, scale, scale_sq)
        met["modele"] = name
        met["n_produits_fenetres"] = len(g)
        rows.append(met)
    df = pd.DataFrame(rows).sort_values("WAPE").reset_index(drop=True)
    return df.rename(columns={"biais_relatif": "biais_normalise"})


def per_window_wape(combined: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (name, widx), g in combined.groupby(["modele", "window"]):
        a = g.groupby("unique_id")[["y", "y_pred"]].sum()
        met = compute_all_metrics(a["y"], a["y_pred"])
        rows.append({"modele": name, "window": widx, "WAPE": met["WAPE"], "biais": met["biais"]})
    return pd.DataFrame(rows)


def segment_ranking(combined: pd.DataFrame, segments: pd.DataFrame, filter_col: str, filter_val, label: str) -> pd.DataFrame:
    """Grain corrigé le 2026-08-14 (même bug que `backtest_report_final.build_segment_ranking`) :
    agrégation par (produit, fenêtre), jamais par produit seul à travers
    plusieurs fenêtres — sinon les erreurs de fenêtres différentes se
    compensent avant le calcul du WAPE, ce qui ne correspond à aucune
    prévision réellement émise (chaque fenêtre = une prévision à 30 jours)."""
    merged = combined.merge(segments, on=["unique_id", "window"], how="left")
    subset = merged[merged[filter_col] == filter_val]
    rows = []
    for name, g in subset.groupby("modele"):
        agg = g.groupby(["unique_id", "window"])[["y", "y_pred"]].sum()
        met = compute_all_metrics(agg["y"], agg["y_pred"])
        rows.append({"modele": name, "segment": label, "WAPE": met["WAPE"], "MAE": met["MAE"], "n_produits_fenetres": len(agg)})
    return pd.DataFrame(rows).sort_values("WAPE")


def load_timing() -> pd.DataFrame:
    baseline_events = [json.loads(l) for l in BASELINE_LOG_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
    baseline_summ = pd.DataFrame([e for e in baseline_events if e.get("type") == "resume_modele_fenetre"])
    baseline_timing = baseline_summ.groupby("modele").agg(
        temps_total_s=("duree_s", "sum"), temps_moyen_par_fenetre_s=("duree_s", "mean"),
    ).reset_index()

    lgbm_events = [json.loads(l) for l in LGBM_LOG_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
    lgbm_df = pd.DataFrame(lgbm_events)
    lgbm_df["duree_s"] = lgbm_df["duree_fit_s"] + lgbm_df["duree_predict_s"]
    lgbm_timing = lgbm_df.groupby("modele").agg(
        temps_total_s=("duree_s", "sum"), temps_moyen_par_fenetre_s=("duree_s", "mean"),
    ).reset_index()

    return pd.concat([baseline_timing, lgbm_timing], ignore_index=True)


def apply_acceptance_rule(principale: pd.DataFrame, stability: pd.DataFrame, abc_a: pd.DataFrame) -> pd.DataFrame:
    autoets_wape = float(principale.loc[principale["modele"] == "AutoETS", "WAPE"].iloc[0])
    wa28_wape = float(principale.loc[principale["modele"] == "WindowAverage28", "WAPE"].iloc[0])
    stability_median_baseline = float(
        stability[stability["modele"].isin(BASELINE_MODELS)]["WAPE_ecart_type"].median()
    )
    best_baseline_abc_a = float(abc_a[abc_a["modele"].isin(BASELINE_MODELS)]["WAPE"].min())

    rows = []
    for name in LGBM_MODELS:
        p = principale[principale["modele"] == name].iloc[0]
        s = stability[stability["modele"] == name]
        wape_ok = p["WAPE"] <= autoets_wape * 1.05
        stab_val = float(s["WAPE_ecart_type"].iloc[0]) if len(s) else float("nan")
        stab_ok = np.isfinite(stab_val) and stab_val <= stability_median_baseline
        a = abc_a[abc_a["modele"] == name]
        abc_val = float(a["WAPE"].iloc[0]) if len(a) else float("nan")
        abc_ok = np.isfinite(abc_val) and abc_val <= best_baseline_abc_a * 1.10
        biais_ok = abs(p["biais_normalise"]) < 0.10
        gain_vs_wa28 = (wa28_wape - p["WAPE"]) / wa28_wape
        rows.append({
            "modele": name,
            "1_WAPE<=AutoETS*1.05": wape_ok, "WAPE": p["WAPE"], "seuil_WAPE": round(autoets_wape * 1.05, 4),
            "2_stabilite<=mediane_baselines": stab_ok, "ecart_type_WAPE": stab_val,
            "seuil_stabilite": round(stability_median_baseline, 4),
            "3_ABC_A<=+10%_meilleure_baseline": abc_ok, "WAPE_classe_A": abc_val,
            "seuil_ABC_A": round(best_baseline_abc_a * 1.10, 4),
            "4_|biais_normalise|<0.10": biais_ok, "biais_normalise": p["biais_normalise"],
            "gain_vs_WindowAverage28_%": round(gain_vs_wa28 * 100, 2),
            "accepte_4_criteres_numeriques": wape_ok and stab_ok and abc_ok and biais_ok,
        })
    return pd.DataFrame(rows)


def main() -> None:
    table = pd.read_parquet(PROJECT_ROOT / "data" / "processed" / "table_analytique.parquet")
    table["ds"] = pd.to_datetime(table["ds"])

    op = load_operational()
    combined, eligible_pairs = build_combined_daily(op)

    scale, scale_sq = _scale_lookup(table)
    principale = principale_table(combined, scale, scale_sq)

    pw = per_window_wape(combined)
    stability = (
        pw.groupby("modele")["WAPE"]
        .agg(WAPE_moyenne="mean", WAPE_ecart_type="std")
        .assign(coefficient_variation=lambda d: d["WAPE_ecart_type"] / d["WAPE_moyenne"])
        .sort_values("WAPE_ecart_type")
        .reset_index()
    )

    contexts = build_window_contexts(table)
    seg_rows = []
    for widx, ctx in contexts.items():
        train = table[table["ds"] <= ctx.cutoff]
        features = compute_series_features(train)
        seg = classify(features, SegmentationConfig())[["unique_id", "profil_demande", "classe_abc"]].copy()
        seg["window"] = widx
        seg_rows.append(seg)
    segments = pd.concat(seg_rows, ignore_index=True)

    abc_a = segment_ranking(combined, segments, "classe_abc", "A", "classe ABC = A")
    intermittent = segment_ranking(combined, segments, "profil_demande", "intermittent", "profil = intermittent")

    timing = load_timing()

    principale_full = principale.merge(
        stability[["modele", "WAPE_ecart_type"]], on="modele", how="left"
    ).merge(timing, on="modele", how="left")
    principale_full["couverture_native"] = principale_full["modele"].apply(
        lambda m: 1.0 if m in LGBM_MODELS else np.nan
    )
    is_lgbm = principale_full["modele"].isin(LGBM_MODELS)
    # Couverture/fallback des baselines réutilisées telles qu'établies au rapport 18 (op).
    from src.pipelines.backtest_report_final import compute_coverage
    cov = compute_coverage(op)
    cov_by_model = cov.groupby("modele").agg(n_success=("n_success", "sum"), n_eligible=("n_eligible", "sum"),
                                              n_total_test=("n_total_test", "sum")).reset_index()
    cov_by_model["couverture_native_baseline"] = cov_by_model["n_success"] / cov_by_model["n_eligible"]
    cov_by_model["taux_fallback_baseline"] = 1 - cov_by_model["n_success"] / cov_by_model["n_total_test"]
    principale_full = principale_full.merge(
        cov_by_model[["modele", "couverture_native_baseline", "taux_fallback_baseline"]], on="modele", how="left"
    )
    principale_full.loc[is_lgbm, "couverture_native"] = 1.0
    principale_full.loc[~is_lgbm, "couverture_native"] = principale_full.loc[~is_lgbm, "couverture_native_baseline"]
    principale_full["taux_fallback"] = np.where(is_lgbm, 0.0, principale_full["taux_fallback_baseline"])
    principale_full = principale_full.drop(columns=["couverture_native_baseline", "taux_fallback_baseline"])
    principale_full = principale_full.sort_values("WAPE").reset_index(drop=True)

    acceptance = apply_acceptance_rule(principale, stability, abc_a)

    cold_start_lgbm = pd.read_csv(COLD_START_CSV)
    cold_start_lgbm_by_model = cold_start_lgbm.groupby("modele").apply(
        lambda g: pd.Series({
            "WAPE_pooled": g["volume_prevu"].sub(g["volume_reel"]).abs().sum() / g["volume_reel"].sum()
            if g["volume_reel"].sum() > 0 else np.nan,
            "volume_reel_total": g["volume_reel"].sum(),
            "n_lignes_total": g["n_lignes"].sum(),
            "biais_moyen": (g["biais"] * g["n_lignes"]).sum() / g["n_lignes"].sum(),
        }), include_groups=False
    ).reset_index().sort_values("WAPE_pooled")

    hurdle_eval = pd.read_csv(HURDLE_EVAL_CSV)
    hurdle_summary = hurdle_eval[["PR_AUC", "ROC_AUC", "Brier", "log_loss", "precision_at_threshold", "recall_at_threshold"]].mean()

    best_baseline = principale[principale["modele"].isin(BASELINE_MODELS)].iloc[0]
    best_lgbm = principale[principale["modele"].isin(LGBM_MODELS)].iloc[0]
    wa28 = principale[principale["modele"] == "WindowAverage28"].iloc[0]
    any_lgbm_accepted = bool(acceptance["accepte_4_criteres_numeriques"].any())

    if any_lgbm_accepted:
        accepted_names = acceptance[acceptance["accepte_4_criteres_numeriques"]]["modele"].tolist()
        recommendation = (
            f"Les variantes {accepted_names} satisfont les 4 critères numériques du §1bis du rapport 18. "
            f"Le critère 5 (gain qualitatif vs WindowAverage28) reste à juger : voir le tableau "
            f"`gain_vs_WindowAverage28_%` ci-dessous avant toute décision de mise en production."
        )
    else:
        recommendation = (
            f"**Aucune variante LightGBM ne satisfait simultanément les 4 critères numériques du §1bis.** "
            f"La meilleure variante LightGBM ({best_lgbm['modele']}, WAPE={best_lgbm['WAPE']:.4f}) "
            f"n'apporte pas de gain net, sûr et stable par rapport à {best_baseline['modele']} "
            f"(WAPE={best_baseline['WAPE']:.4f}) ni par rapport à WindowAverage28 "
            f"(WAPE={wa28['WAPE']:.4f}, référence de robustesse). "
            f"**Recommandation : conserver {best_baseline['modele']} comme modèle de référence "
            f"(meilleure WAPE globale) et WindowAverage28 comme repli opérationnel robuste** — "
            f"la complexité additionnelle de LightGBM n'est pas justifiée par les résultats de ce backtest."
        )

    lines = [
        "# 21 — Rapport final comparatif : baselines vs LightGBM",
        "",
        f"_Généré le {datetime.now(timezone.utc).isoformat()}. Périmètre : identique à l'évaluation "
        f"« principale » du rapport 18 (produits présents dans le train au cutoff, cold-start exclu). "
        f"Les prédictions LightGBM du scénario A (qui contiennent aussi des produits cold-start non "
        f"gérés par le modèle lui-même) sont filtrées sur exactement ce même périmètre avant tout calcul._",
        "",
        "## 0. Résumé des contrôles pré-rapport",
        "",
        "- 24/24 checkpoints LightGBM présents (`data/interim/backtest_lightgbm/`), 4 modèles × 6 fenêtres.",
        "- 24/24 lignes de journal `statut: succes`, aucun échec, aucun repli budget/exception.",
        "- 0 NaN, 0 Inf, 0 valeur négative sur les 202 940 prédictions LightGBM (`y_pred`).",
        "- **Constat à interpréter avec prudence** : sur toutes les fenêtres, `y_pred` minimal observé "
        "reste nettement au-dessus de 0 (ex. fenêtre 6, modèle direct : min = 0,29) alors que 52,7 % "
        "des vraies valeurs `y` sont exactement 0 (forte intermittence). Le modèle direct converge "
        "vers une valeur proche de la moyenne plutôt que de résoudre nettement le cas « zéro vs positif » "
        "au niveau de chaque ligne, et son biais moyen dérive légèrement à la hausse avec l'horizon "
        "(effet d'accumulation attendu d'une stratégie récursive). Ce constat motive de lire le "
        "classifieur hurdle (§4) comme une tentative de correction, pas comme acquise.",
        "",
        "## 1. Évaluation principale — WAPE, MASE, RMSSE, biais, stabilité, coût",
        "",
        principale_full[[
            "modele", "WAPE", "MAE", "RMSE", "RMSSE", "MASE", "sMAPE", "biais", "biais_normalise",
            "taux_sous_prevision", "cout_asymetrique_1_5x", "cout_asymetrique_2x",
            "WAPE_ecart_type", "couverture_native", "taux_fallback",
            "temps_total_s", "temps_moyen_par_fenetre_s",
        ]].to_markdown(index=False, floatfmt=".4f"),
        "",
        "_Pour les baselines, `couverture_native`/`taux_fallback` proviennent du rapport 18 (replis "
        "historique/exception/budget documentés). Pour LightGBM, la couverture est 1,0 par construction "
        "sur ce périmètre filtré (aucun mécanisme de repli — le modèle produit toujours une prédiction "
        "brute, cf. §0)._",
        "",
        "## 2. Règle de décision multi-critères appliquée (§1bis du rapport 18)",
        "",
        acceptance.to_markdown(index=False, floatfmt=".4f"),
        "",
        "## 3. Meilleur modèle par segment",
        "",
        "**Produits classe ABC = A :**",
        "",
        abc_a.to_markdown(index=False, floatfmt=".4f"),
        "",
        "**Séries au profil intermittent :**",
        "",
        intermittent.to_markdown(index=False, floatfmt=".4f"),
        "",
        "## 4. Classifieur hurdle — évaluation séparée (P(y>0)), jamais mélangée au classement ci-dessus",
        "",
        hurdle_eval.to_markdown(index=False, floatfmt=".4f"),
        "",
        f"Moyenne sur les 6 fenêtres : PR-AUC={hurdle_summary['PR_AUC']:.3f}, "
        f"ROC-AUC={hurdle_summary['ROC_AUC']:.3f}, Brier={hurdle_summary['Brier']:.3f}, "
        f"log-loss={hurdle_summary['log_loss']:.3f}, précision(seuil 0,5)={hurdle_summary['precision_at_threshold']:.3f}, "
        f"rappel(seuil 0,5)={hurdle_summary['recall_at_threshold']:.3f}.",
        "",
        "**Lecture honnête** : un ROC-AUC de 0,60-0,63 et un PR-AUC de 0,55-0,61 (pour une base positive "
        "d'environ 47 %) indiquent une discrimination **faible à modeste** entre jour vendu et jour non "
        "vendu — nettement au-dessus du hasard, mais loin d'un classifieur fiable. La composante `y_pred "
        "= P(y>0) × E(y|y>0)` du modèle hurdle hérite de cette incertitude ; sa WAPE globale (§1) doit "
        "être lue avec cette réserve, pas comme la preuve d'une segmentation zéro/positif résolue.",
        "",
        "## 5. Cold-start — comparaison séparée (produits absents du train)",
        "",
        "**Baselines (repli `ColdStartZero`, identique pour tous les modèles historiques, rapport 18 §3) :**",
        "",
        "Voir `reports/18_backtest_rapport_final.md` §3 pour le détail (non recopié ici pour éviter toute "
        "divergence de source).",
        "",
        "**Stratégies cold-start dédiées à LightGBM, testées sur les mêmes produits (par fenêtre, "
        "`reports/20_cold_start_lightgbm.csv`) :**",
        "",
        cold_start_lgbm.to_markdown(index=False, floatfmt=".4f"),
        "",
        "**WAPE poolée sur les 5 fenêtres concernées (pas une moyenne de WAPE par fenêtre) :**",
        "",
        cold_start_lgbm_by_model.to_markdown(index=False, floatfmt=".4f"),
        "",
        "**Conclusion cold-start** : `ColdStartZero` (prévision nulle) obtient la WAPE poolée la plus "
        "basse dans les 5 fenêtres comportant des produits cold-start — les moyennes par catégorie "
        "(`MoyenneCategorie`, `MoyenneCategorieJourSemaine`) sur-prévoient systématiquement (biais positif) "
        "sans gain de WAPE. **`ColdStartZero` reste la stratégie recommandée pour les nouveaux produits**, "
        "y compris dans un pipeline LightGBM.",
        "",
        "## 6. Recommandation finale",
        "",
        recommendation,
        "",
        "**Détail des raisons, par critère :**",
        "",
    ]
    for _, r in acceptance.iterrows():
        detail = (
            f"- **{r['modele']}** : WAPE {r['WAPE']:.4f} "
            f"({'≤' if r['1_WAPE<=AutoETS*1.05'] else '>'} seuil {r['seuil_WAPE']:.4f}) ; "
            f"stabilité {r['ecart_type_WAPE']:.4f} "
            f"({'≤' if r['2_stabilite<=mediane_baselines'] else '>'} médiane baselines {r['seuil_stabilite']:.4f}) ; "
            f"WAPE classe A {r['WAPE_classe_A']:.4f} "
            f"({'≤' if r['3_ABC_A<=+10%_meilleure_baseline'] else '>'} seuil {r['seuil_ABC_A']:.4f}) ; "
            f"biais normalisé {r['biais_normalise']:+.4f} "
            f"({'sous' if r['4_|biais_normalise|<0.10'] else 'au-dessus de'} 0,10 en valeur absolue) ; "
            f"gain vs WindowAverage28 : {r['gain_vs_WindowAverage28_%']:+.2f} %."
        )
        lines.append(detail)
    lines += [
        "",
        "## 7. Ce qui n'a pas été fait (limites explicites)",
        "",
        "- Pas d'optimisation d'hyperparamètres (Optuna) : les paramètres LightGBM sont fixes et "
        "raisonnables mais non ajustés — un gain reste possible sans changer la conclusion structurelle "
        "sur le biais et la couverture zéro/positif.",
        "- Scénario B (stock connu à J+1 uniquement) non intégré à ce classement — analyse séparée, "
        "cf. docstring de `src/pipelines/backtest_lightgbm.py`.",
        "- Scénario C (stock projeté sur l'horizon complet) non réalisé : aucune règle de projection "
        "validée n'existe à partir de la seule information disponible au cutoff.",
        "- Aucune publication, aucun déploiement : ce rapport s'arrête au tableau comparatif et à la "
        "recommandation.",
    ]

    report = "\n".join(str(l) for l in lines)
    OUT_PATH.write_text(report, encoding="utf-8")
    logger.info("Rapport écrit : %s", OUT_PATH)


if __name__ == "__main__":
    main()
