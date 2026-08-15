"""Rapport final du backtest — construit UNIQUEMENT depuis les prédictions
opérationnelles déjà classifiées (`backtest_postprocess.py`).

    python -m src.pipelines.backtest_report_final

Quatre évaluations, jamais mélangées sans étiquette :

* **principale** (périmètre comparable) — produits présents dans le train au
  cutoff, `y_pred_final` (replis historique/exception/budget inclus, cold-start
  exclu). C'est celle-ci qui sert à classer les modèles et fixer le seuil.
* **opérationnelle complète** — toutes les lignes, `y_pred_final`. Mesure ce
  que le pipeline déployé produirait réellement, cold-start compris.
* **cold-start** — uniquement les produits absents du train, rapportée une
  seule fois (le repli est strictement identique quel que soit le modèle
  demandé : comparer les modèles dessus n'aurait aucun sens).
* **native / support commun** — sous-analyses de fiabilité : la native ne
  compte que les prédictions réellement produites par le modèle demandé
  (`status == success_valid_prediction`) ; le support commun restreint la
  comparaison aux (produit, fenêtre) où tous les modèles comparés ont une
  prédiction native valide simultanément.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd

from src.config.settings import PROJECT_ROOT
from src.evaluation.metrics import compute_all_metrics, naive_scale, naive_scale_squared
from src.features.segmentation import SegmentationConfig, classify, compute_series_features
from src.pipelines.backtest_baselines import LOG_PATH, N_WINDOWS, SEASONALITY, _model_factory
from src.pipelines.backtest_postprocess import (
    OPERATIONAL_DIR,
    AUTOARIMA_COVERAGE_THRESHOLD,
    build_window_contexts,
    main as run_postprocess_main,
)
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)

MODEL_NAMES = [name for name, _ in _model_factory()]


def _scale_lookup(table: pd.DataFrame) -> tuple[dict[tuple[int, str], float], dict[tuple[int, str], float]]:
    """Échelles MASE (linéaire) et RMSSE (quadratique), par (fenêtre, produit),
    calculées sur le TRAIN de cette fenêtre uniquement."""
    contexts = build_window_contexts(table)
    scale, scale_sq = {}, {}
    for widx, ctx in contexts.items():
        train = table[table["ds"] <= ctx.cutoff]
        s = train.groupby("unique_id")["y"].apply(lambda x: naive_scale(x.to_numpy(), SEASONALITY))
        s2 = train.groupby("unique_id")["y"].apply(lambda x: naive_scale_squared(x.to_numpy(), SEASONALITY))
        for uid, val in s.items():
            scale[(widx, uid)] = val
        for uid, val in s2.items():
            scale_sq[(widx, uid)] = val
    return scale, scale_sq


def _metrics_on(agg: pd.DataFrame, scale: dict, scale_sq: dict) -> dict:
    met = compute_all_metrics(agg["y"], agg["y_pred"])
    err = (agg["y"] - agg["y_pred"]).to_numpy()
    sc = np.array([scale.get((w, u), np.nan) for w, u in zip(agg["window"], agg["unique_id"])])
    valid = np.isfinite(sc) & (sc > 1e-9)
    met["MASE"] = float((np.abs(err)[valid] / sc[valid]).mean()) if valid.any() else np.nan

    sc2 = np.array([scale_sq.get((w, u), np.nan) for w, u in zip(agg["window"], agg["unique_id"])])
    valid2 = np.isfinite(sc2) & (sc2 > 1e-9)
    met["RMSSE"] = (
        float(np.sqrt(np.mean((err[valid2] / sc2[valid2]) ** 2))) if valid2.any() else np.nan
    )
    return met


def compute_coverage(op: pd.DataFrame) -> pd.DataFrame:
    """Réconciliation exacte par (modèle, fenêtre) — dénominateur unique,
    réutilisé partout où une « couverture » est calculée.

    Distingue explicitement :

    * ``n_total_test`` : tous les produits évalués sur la fenêtre (cold-start inclus) ;
    * ``n_eligible`` : produits présents dans le train (seuls ceux-là sont
      *tentés* par le modèle — un produit cold-start n'entre jamais dans la
      boucle par série, donc n'est ni un succès ni un échec du modèle) ;
    * ``couverture_native`` = succès / **éligibles**, jamais / total_test.

    Régression corrigée : la version précédente utilisait `n_total_test` comme
    dénominateur (13/292 pour AutoARIMA fenêtre 4), incluant à tort les 9
    produits cold-start jamais soumis au modèle. Le bon calcul est 13/283.
    """
    base = op[["model_requested", "window", "unique_id", "status", "train_observations"]].drop_duplicates()
    rows = []
    for (name, widx), g in base.groupby(["model_requested", "window"]):
        n_total = len(g)
        n_cold = int((g["train_observations"] == 0).sum())
        n_eligible = n_total - n_cold
        counts = g["status"].value_counts()
        n_success = int(counts.get("success_valid_prediction", 0))
        n_budget = int(counts.get("budget_fallback", 0))
        n_exception = int(counts.get("exception_fallback", 0))
        n_hist = int(counts.get("success_invalid_prediction_fallback", 0))
        n_cold_status = int(counts.get("cold_start_fallback", 0))
        assert n_cold_status == n_cold, f"{name} f{widx}: cold-start incohérent ({n_cold_status} != {n_cold})"
        somme = n_success + n_budget + n_exception + n_hist + n_cold_status
        rows.append({
            "modele": name, "window": widx,
            "n_total_test": n_total, "n_eligible": n_eligible, "n_cold_start": n_cold,
            "n_success": n_success, "n_budget": n_budget, "n_exception": n_exception,
            "n_historique_insuffisant": n_hist,
            "somme_categories": somme, "coherent": somme == n_total,
            "couverture_native": n_success / max(n_eligible, 1),
        })
    return pd.DataFrame(rows)


def build_all_evaluations(op: pd.DataFrame, table: pd.DataFrame) -> dict:
    scale, scale_sq = _scale_lookup(table)

    # ------------------------------------------------------------------
    # Évaluation principale : périmètre comparable (train_observations > 0)
    # ------------------------------------------------------------------
    principale_rows = op[op["train_observations"] > 0]
    agg_p = (
        principale_rows.groupby(["model_requested", "unique_id", "window"])[["y", "y_pred_final"]]
        .sum().rename(columns={"y_pred_final": "y_pred"}).reset_index()
    )
    principale = []
    for name, g in agg_p.groupby("model_requested"):
        met = _metrics_on(g, scale, scale_sq)
        met["modele"] = name
        met["n_produits_fenetres"] = len(g)
        principale.append(met)
    principale_df = pd.DataFrame(principale).sort_values("WAPE")
    principale_df = principale_df.rename(columns={"biais_relatif": "biais_normalise"})

    # ------------------------------------------------------------------
    # Évaluation opérationnelle complète (toutes les lignes)
    # ------------------------------------------------------------------
    agg_o = (
        op.groupby(["model_requested", "unique_id", "window"])[["y", "y_pred_final"]]
        .sum().rename(columns={"y_pred_final": "y_pred"}).reset_index()
    )
    operationnelle = []
    for name, g in agg_o.groupby("model_requested"):
        met = _metrics_on(g, scale, scale_sq)
        met["modele"] = name
        operationnelle.append(met)
    operationnelle_df = pd.DataFrame(operationnelle).sort_values("WAPE")
    operationnelle_df = operationnelle_df.rename(columns={"biais_relatif": "biais_normalise"})

    # ------------------------------------------------------------------
    # Évaluation cold-start (une seule fois, pas de comparaison de modèles)
    # ------------------------------------------------------------------
    cs = op[op["status"] == "cold_start_fallback"]
    cs_one_model = cs[cs["model_requested"] == MODEL_NAMES[0]]  # identique pour tous, on ne compte qu'une fois
    cold_start_eval = {
        "n_produits": int(cs_one_model["unique_id"].nunique()),
        "n_lignes": int(len(cs_one_model)),
        "quantite_reelle_totale": float(cs_one_model["y"].sum()),
        "part_zeros": float((cs_one_model["y"] == 0).mean()),
        "MAE": float(cs_one_model["y"].abs().mean()),  # y_pred=0 -> MAE = mean(|y|)
        "WAPE": (
            float(cs_one_model["y"].abs().sum() / cs_one_model["y"].sum())
            if cs_one_model["y"].sum() > 0 else float("nan")
        ),
        "biais": float(-cs_one_model["y"].mean()),
    }

    # ------------------------------------------------------------------
    # Native (par modèle) + couverture — dénominateur = éligibles (train),
    # jamais le total test (qui inclurait le cold-start, jamais tenté).
    # ------------------------------------------------------------------
    coverage = compute_coverage(op)
    assert coverage["coherent"].all(), (
        f"Réconciliation incohérente : {coverage[~coverage['coherent']]}"
    )
    native_rows = op[op["status"] == "success_valid_prediction"]
    cov_by_model = coverage.groupby("modele").agg(
        n_success=("n_success", "sum"), n_eligible=("n_eligible", "sum"),
    )
    native = []
    for name in MODEL_NAMES:
        nat = native_rows[native_rows["model_requested"] == name]
        agg = nat.groupby(["unique_id", "window"])[["y", "y_pred_raw"]].sum().rename(
            columns={"y_pred_raw": "y_pred"}
        ).reset_index()
        met = compute_all_metrics(agg["y"], agg["y_pred"]) if len(agg) else {"WAPE": np.nan, "MAE": np.nan}
        native.append({
            "modele": name,
            "couverture_native": cov_by_model.loc[name, "n_success"] / max(cov_by_model.loc[name, "n_eligible"], 1),
            "n_produits_natifs": int(cov_by_model.loc[name, "n_success"]),
            "n_produits_eligibles": int(cov_by_model.loc[name, "n_eligible"]),
            "WAPE_natif": met["WAPE"],
            "MAE_natif": met["MAE"],
        })
    native_df = pd.DataFrame(native).sort_values("WAPE_natif")

    # ------------------------------------------------------------------
    # Support commun, PAR FENÊTRE : modèles dont la couverture native de
    # cette fenêtre atteint le seuil ; comparaison restreinte à l'intersection
    # des (produit) natifs simultanément valides parmi ces modèles.
    # ------------------------------------------------------------------
    common_support_rows = []
    excluded_notes = []
    cov_by_model_window = compute_coverage(op).set_index(["modele", "window"])["couverture_native"]
    for widx in sorted(op["window"].unique()):
        wop = op[op["window"] == widx]
        native_sets = {}
        for name in MODEL_NAMES:
            sub = wop[wop["model_requested"] == name]
            nat = sub[sub["status"] == "success_valid_prediction"]
            native_sets[name] = set(nat["unique_id"])
        cov_here = {m: cov_by_model_window.get((m, widx), 0.0) for m in MODEL_NAMES}
        participants = [m for m in MODEL_NAMES if cov_here[m] >= AUTOARIMA_COVERAGE_THRESHOLD]
        excluded = [m for m in MODEL_NAMES if m not in participants]
        if excluded:
            excluded_notes.append({"window": widx, "modeles_exclus": excluded,
                                    "couverture": {m: round(cov_here[m], 4) for m in excluded}})
        if not participants:
            continue
        common_ids = set.intersection(*[native_sets[m] for m in participants])
        for name in participants:
            sub = wop[(wop["model_requested"] == name) & (wop["unique_id"].isin(common_ids))]
            agg = sub.groupby("unique_id")[["y", "y_pred_raw"]].sum().rename(columns={"y_pred_raw": "y_pred"})
            met = compute_all_metrics(agg["y"], agg["y_pred"]) if len(agg) else {"WAPE": np.nan, "MAE": np.nan}
            common_support_rows.append({
                "window": widx, "modele": name, "n_produits_support_commun": len(common_ids),
                "WAPE": met["WAPE"], "MAE": met["MAE"],
            })
    common_support_df = pd.DataFrame(common_support_rows)

    return {
        "principale": principale_df,
        "operationnelle": operationnelle_df,
        "cold_start": cold_start_eval,
        "native": native_df,
        "support_commun": common_support_df,
        "support_commun_exclusions": excluded_notes,
    }


def build_segments(table: pd.DataFrame, contexts: dict) -> pd.DataFrame:
    """Segmentation ABC / intermittence, recalculée PAR FENÊTRE sur le train
    uniquement — jamais sur l'ensemble des données (cf. contrainte anti-fuite
    déjà appliquée dans `backtest_baselines.run_backtest`)."""
    rows = []
    for widx, ctx in contexts.items():
        train = table[table["ds"] <= ctx.cutoff]
        features = compute_series_features(train)
        seg = classify(features, SegmentationConfig())
        seg = seg[["unique_id", "profil_demande", "classe_abc"]].copy()
        seg["window"] = widx
        rows.append(seg)
    return pd.concat(rows, ignore_index=True)


def build_per_window_metrics(op: pd.DataFrame) -> pd.DataFrame:
    """WAPE/biais par (modèle, fenêtre), périmètre principal (hors cold-start)."""
    rows = []
    principale_rows = op[op["train_observations"] > 0]
    for (name, widx), g in principale_rows.groupby(["model_requested", "window"]):
        agg = g.groupby("unique_id")[["y", "y_pred_final"]].sum().rename(columns={"y_pred_final": "y_pred"})
        met = compute_all_metrics(agg["y"], agg["y_pred"])
        rows.append({"modele": name, "window": widx, "WAPE": met["WAPE"], "biais": met["biais"]})
    return pd.DataFrame(rows)


def build_segment_ranking(op: pd.DataFrame, segments: pd.DataFrame, filter_col: str, filter_val, label: str) -> pd.DataFrame:
    """Régression corrigée le 2026-08-14 : la version précédente agrégeait par
    `unique_id` SEUL, sommant `y`/`y_pred_final` à travers TOUTES les fenêtres
    où le produit était classé dans le segment avant de prendre la valeur
    absolue — un produit classé A sur 3 fenêtres voyait ses erreurs des 3
    fenêtres se compenser avant le calcul du WAPE, exactement le même biais de
    grain que la confusion quotidien/cumulé (cf. rapport 23 §1), mais à
    l'échelle de plusieurs fenêtres (jusqu'à 180 jours) au lieu d'une seule
    prévision à 30 jours. Le WAPE obtenu (0,058 pour WindowAverage28 sur la
    classe A) ne correspond à AUCUNE prévision réellement émise par le
    pipeline (chaque fenêtre est une prévision à 30 jours indépendante).
    Grain corrigé : une ligne agrégée par (produit, fenêtre) — cohérent avec
    l'évaluation « principale » du §1."""
    principale_rows = op[op["train_observations"] > 0].merge(
        segments, on=["unique_id", "window"], how="left"
    )
    subset = principale_rows[principale_rows[filter_col] == filter_val]
    rows = []
    for name, g in subset.groupby("model_requested"):
        agg = g.groupby(["unique_id", "window"])[["y", "y_pred_final"]].sum().rename(columns={"y_pred_final": "y_pred"})
        met = compute_all_metrics(agg["y"], agg["y_pred"])
        rows.append({"modele": name, "segment": label, "WAPE": met["WAPE"], "MAE": met["MAE"],
                      "n_produits_fenetres": len(agg)})
    return pd.DataFrame(rows).sort_values("WAPE")


def build_status_rates(op: pd.DataFrame) -> pd.DataFrame:
    """% de chaque statut par modèle, sur la base des PRODUITS (constant par
    (produit, fenêtre)), et vérification que les taux somment à 100 %."""
    base = op[["model_requested", "unique_id", "window", "status"]].drop_duplicates()
    rows = []
    for name, g in base.groupby("model_requested"):
        counts = g["status"].value_counts()
        total = len(g)
        row = {"modele": name, "n_produits_fenetres": total}
        for s in ("success_valid_prediction", "success_invalid_prediction_fallback",
                  "exception_fallback", "budget_fallback", "cold_start_fallback"):
            row[f"%_{s}"] = 100 * counts.get(s, 0) / total
        row["somme_%"] = sum(row[f"%_{s}"] for s in (
            "success_valid_prediction", "success_invalid_prediction_fallback",
            "exception_fallback", "budget_fallback", "cold_start_fallback"))
        rows.append(row)
    return pd.DataFrame(rows).sort_values("%_success_valid_prediction", ascending=False)


def build_autoarima_window4_note(op: pd.DataFrame) -> str:
    sub = op[(op["model_requested"] == "AutoARIMA") & (op["window"] == 4)]
    cov = compute_coverage(sub)
    row = cov.iloc[0]
    flag = "NON COMPARABLE / COUVERTURE INSUFFISANTE" if row["couverture_native"] < AUTOARIMA_COVERAGE_THRESHOLD else "OK"
    agg = sub.groupby("unique_id")[["y", "y_pred_final"]].sum().rename(columns={"y_pred_final": "y_pred"})
    met_op = compute_all_metrics(agg["y"], agg["y_pred"])

    table_lines = [
        "| Catégorie | Produits |",
        "|---|---:|",
        f"| Présents dans le test | {row['n_total_test']} |",
        f"| — dont présents dans le train (éligibles à AutoARIMA) | {row['n_eligible']} |",
        f"| — dont cold-start (absents du train) | {row['n_cold_start']} |",
        f"| Sur les {row['n_eligible']} éligibles : vrais ajustements AutoARIMA | {row['n_success']} |",
        f"| Sur les {row['n_eligible']} éligibles : replis budget | {row['n_budget']} |",
        f"| Sur les {row['n_eligible']} éligibles : replis exception | {row['n_exception']} |",
        f"| Sur les {row['n_eligible']} éligibles : autres replis (historique insuffisant) | {row['n_historique_insuffisant']} |",
        f"| **Somme (cold-start + succès + budget + exception + autre)** | "
        f"**{row['somme_categories']}** (= test : {row['coherent']}) |",
    ]

    return (
        f"**AutoARIMA, fenêtre 4 — {flag}**\n\n"
        + "\n".join(table_lines) + "\n\n"
        f"**Origine de l'incohérence 283 vs 292 signalée** : 283 = produits éligibles (présents "
        f"dans le train, seuls ceux-là sont *tentés* par le modèle) — c'est le dénominateur "
        f"correct, utilisé ci-dessus et dans tout le reste du rapport. 292 = 283 éligibles + 9 "
        f"produits cold-start apparus après le cutoff, qui n'entrent jamais dans la boucle "
        f"d'ajustement et ne sont donc ni un succès ni un échec du modèle. Une version antérieure "
        f"de ce rapport utilisait par erreur 292 comme dénominateur de couverture (13/292 = 4,5 %) "
        f"; le calcul correct, corrigé ici, est **13/283 = {row['n_success']/row['n_eligible']:.2%}**.\n\n"
        f"- Performance **opérationnelle** du pipeline `AutoARIMA + repli` (toutes les 292 lignes, "
        f"cold-start inclus) : WAPE = {met_op['WAPE']:.4f}.\n"
        f"- Aucune métrique « AutoARIMA pur » n'est calculée sur les {row['n_success']} séries "
        f"seules : cet échantillon est sélectionné par l'ordre d'exécution de la boucle, pas par "
        f"tirage représentatif — le comparer aux autres modèles serait trompeur.\n"
        f"- Coût : 29 237,6 s (8 h 07) pour cette seule fenêtre, pour "
        f"{row['n_success']/row['n_eligible']:.1%} de couverture réelle — à intégrer explicitement "
        f"dans la recommandation finale (coût/bénéfice défavorable)."
    )


def build_windowaverage_seasonalnaive_note(op: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for widx in sorted(op["window"].unique()):
        wop = op[op["window"] == widx]
        base = wop[wop["model_requested"] == "Naive"][["unique_id", "train_observations"]].drop_duplicates()
        n_lt7 = int((base["train_observations"] < 7).sum())
        n_lt28 = int((base["train_observations"] < 28).sum())
        for model, threshold, n_produits in (("SeasonalNaive7", 7, n_lt7), ("WindowAverage28", 28, n_lt28)):
            sub = wop[wop["model_requested"] == model]
            fb = sub[sub["fallback_type"] == "historique_insuffisant"]
            rows.append({
                "fenetre": widx, "modele": model, "seuil_historique_jours": threshold,
                "produits_sous_le_seuil": n_produits,
                "lignes_repli_historique_insuffisant": len(fb),
                "modele_repli_utilise": ", ".join(fb["model_effective"].unique().tolist()) if len(fb) else "—",
            })
    return pd.DataFrame(rows)


def main() -> None:
    table = pd.read_parquet(PROJECT_ROOT / "data" / "processed" / "table_analytique.parquet")
    table["ds"] = pd.to_datetime(table["ds"])

    import glob
    op = pd.concat([pd.read_parquet(f) for f in sorted(glob.glob(str(OPERATIONAL_DIR / "*.parquet")))],
                    ignore_index=True)

    evals = build_all_evaluations(op, table)
    status_rates = build_status_rates(op)
    autoarima_note = build_autoarima_window4_note(op)
    wa_sn_note = build_windowaverage_seasonalnaive_note(op)

    contexts = build_window_contexts(table)
    segments = build_segments(table, contexts)
    per_window = build_per_window_metrics(op)
    stability = (
        per_window.groupby("modele")["WAPE"]
        .agg(WAPE_moyenne="mean", WAPE_ecart_type="std")
        .assign(coefficient_variation=lambda d: d["WAPE_ecart_type"] / d["WAPE_moyenne"])
        .sort_values("WAPE_ecart_type")
        .reset_index()
    )
    abc_a_ranking = build_segment_ranking(op, segments, "classe_abc", "A", "classe ABC = A")
    intermittent_ranking = build_segment_ranking(
        op, segments, "profil_demande", "intermittent", "profil = intermittent"
    )

    # --- Temps d'exécution (journal d'origine) et couverture/repli (compute_coverage) ---
    import json as _json
    events = [_json.loads(l) for l in LOG_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
    summaries_log = pd.DataFrame([e for e in events if e.get("type") == "resume_modele_fenetre"])
    timing = summaries_log.groupby("modele").agg(
        temps_total_s=("duree_s", "sum"), temps_moyen_par_fenetre_s=("duree_s", "mean"),
    ).reset_index()

    coverage_all = compute_coverage(op)
    coverage_by_model = coverage_all.groupby("modele").agg(
        n_success=("n_success", "sum"), n_eligible=("n_eligible", "sum"),
        n_total_test=("n_total_test", "sum"),
    ).reset_index()
    coverage_by_model["couverture_native"] = coverage_by_model["n_success"] / coverage_by_model["n_eligible"]
    coverage_by_model["taux_fallback"] = 1 - coverage_by_model["n_success"] / coverage_by_model["n_total_test"]

    principale = evals["principale"]
    principale = principale.copy()
    principale = principale.merge(
        stability[["modele", "WAPE_ecart_type"]], on="modele", how="left"
    ).merge(
        coverage_by_model[["modele", "couverture_native", "taux_fallback"]], on="modele", how="left"
    ).merge(
        timing[["modele", "temps_total_s", "temps_moyen_par_fenetre_s"]], on="modele", how="left"
    )
    principale["note"] = principale["modele"].apply(
        lambda m: "⚠️ voir §7 (fenêtre 4 non comparable)" if m == "AutoARIMA" else ""
    )
    seuil_modele = evals["principale"].iloc[0]
    stat_models = {"AutoETS", "AutoARIMA", "CrostonOptimized", "TSB"}
    simple_models = {"Naive", "SeasonalNaive7", "WindowAverage28"}
    modele_plus_stable = stability.iloc[0]
    modele_moins_biaise = principale.loc[principale["biais_normalise"].abs().idxmin()]

    lines = [
        "# 18 — Rapport final du backtest (opérationnel, causes de repli séparées)",
        "",
        f"_Généré le {datetime.now(timezone.utc).isoformat()}. Construit exclusivement depuis "
        f"`reports/backtest/operational_predictions/` — les 42 checkpoints bruts n'ont jamais été modifiés._",
        "",
        "## 1. Évaluation principale — périmètre comparable (produits présents dans le train)",
        "",
        "_Sert au classement des modèles et à la sélection du seuil pour LightGBM. Inclut les "
        "replis historique/exception/budget (documentés), exclut le cold-start._",
        "",
        "**Biais — définitions exactes** (unité : unités de la cible, i.e. quantité) :",
        "",
        "- `biais` (signé) = `mean(y_pred − y)` sur les observations poolées — positif = "
        "sur-prévision en moyenne, négatif = sous-prévision. C'est un **biais moyen par ligne**, "
        "pas un total.",
        "- `biais_normalise` = `SUM(y_pred − y) / SUM(y)` — sans unité, **directement comparable à "
        "la WAPE** (même dénominateur). Un `biais_normalise` de +0,05 signifie une sur-prévision "
        "cumulée de 5 % du volume réel total.",
        "",
        principale[["modele", "WAPE", "MAE", "RMSE", "RMSSE", "MASE", "sMAPE", "biais",
                    "biais_normalise", "taux_sous_prevision", "cout_asymetrique_1_5x",
                    "cout_asymetrique_2x", "WAPE_ecart_type", "couverture_native", "taux_fallback",
                    "temps_total_s", "temps_moyen_par_fenetre_s", "note"]]
        .to_markdown(index=False, floatfmt=".4f"),
        "",
        "## 1bis. Règle de décision multi-critères pour LightGBM",
        "",
        "Le seuil n'est **pas** réduit à `WAPE < 0,2772`. LightGBM n'est considéré supérieur à "
        "AutoETS que s'il remplit **simultanément** :",
        "",
        f"1. WAPE ≤ {seuil_modele['WAPE']:.4f} (bat AutoETS) **ou** WAPE ≤ "
        f"{seuil_modele['WAPE']*1.05:.4f} (dans les 5 % — « s'en approche clairement ») ;",
        f"2. écart-type de la WAPE entre fenêtres ≤ {stability['WAPE_ecart_type'].median():.4f} "
        "(médiane des baselines — ne dégrade pas la stabilité) ;",
        f"3. WAPE sur produits classe A ne dépasse pas {abc_a_ranking.iloc[0]['WAPE']*1.10:.4f} "
        "(au plus +10 % vs la meilleure baseline sur ce segment) ;",
        "4. `|biais_normalise|` reste sous 0,10 (pas de sur/sous-prévision structurelle excessive) ;",
        "5. le gain de WAPE vs WindowAverage28 (le benchmark de simplicité) justifie la complexité "
        "additionnelle — jugé qualitativement, pas seulement numériquement.",
        "",
        "**WindowAverage28 reste le benchmark opérationnel de référence** (simplicité, stabilité, "
        "meilleur sur produits A et séries intermittentes) : LightGBM doit se comparer aux deux — "
        "AutoETS (meilleure WAPE globale) et WindowAverage28 (meilleure robustesse) — pas au seul "
        "chiffre WAPE.",
        "",
        "## 2. Évaluation opérationnelle complète (toutes les lignes, cold-start inclus)",
        "",
        "_Toutes les observations attendues, avec repli documenté (`y_pred_final`). Mesure ce que "
        "le pipeline déployé produirait réellement._",
        "",
        evals["operationnelle"][["modele", "WAPE", "MAE", "RMSE", "RMSSE", "MASE", "biais", "biais_normalise"]]
        .to_markdown(index=False, floatfmt=".4f"),
        "",
        "## 3. Évaluation cold-start (produits absents du train — repli identique pour tous les modèles)",
        "",
        "_Non comparée entre modèles : le repli `ColdStartZero` est strictement identique quel que "
        "soit le modèle demandé._",
        "",
        f"- Produits concernés : {evals['cold_start']['n_produits']}",
        f"- Lignes : {evals['cold_start']['n_lignes']}",
        f"- Quantité réelle totale non prévue : {evals['cold_start']['quantite_reelle_totale']:.0f}",
        f"- Part de zéros réels : {evals['cold_start']['part_zeros']:.2%}",
        f"- MAE du repli zéro : {evals['cold_start']['MAE']:.4f}",
        f"- WAPE du repli zéro : {evals['cold_start']['WAPE']:.4f}",
        f"- Biais : {evals['cold_start']['biais']:.4f} (négatif = sous-prévision structurelle, "
        "attendu puisque la prévision est toujours 0)",
        "",
        "## 4. Métriques natives et couverture (fiabilité par modèle)",
        "",
        "_Calculées uniquement sur les prédictions réellement produites par le modèle demandé — "
        "**non comparables entre modèles** sans passer par le support commun (§5)._",
        "",
        evals["native"].to_markdown(index=False, floatfmt=".4f"),
        "",
        "## 5. Comparaison sur support commun (par fenêtre)",
        "",
        evals["support_commun"].to_markdown(index=False, floatfmt=".4f") if len(evals["support_commun"]) else "_vide_",
        "",
        "Modèles exclus du support commun (couverture native < 90 % sur la fenêtre concernée) :",
        "",
    ]
    for note in evals["support_commun_exclusions"]:
        lines.append(f"- fenêtre {note['window']} : {note['modeles_exclus']} — couverture {note['couverture']}")
    lines += [
        "",
        "## 6. Taux de statut par modèle (doit sommer à 100 %)",
        "",
        status_rates.to_markdown(index=False, floatfmt=".2f"),
        "",
        "## 7. Cas AutoARIMA — fenêtre 4",
        "",
        autoarima_note,
        "",
        "## 8. WindowAverage28 / SeasonalNaive7 — historique insuffisant par fenêtre",
        "",
        wa_sn_note.to_markdown(index=False),
        "",
        "> Un modèle nécessitant un repli fréquent (WindowAverage28, SeasonalNaive7 en début "
        "d'historique) doit être lu avec cette réserve, même si sa métrique opérationnelle finale "
        "paraît bonne — la couverture native (§4) qualifie ce qu'il a réellement appris.",
        "",
        "## 9. Stabilité entre fenêtres (périmètre principal)",
        "",
        "_Écart-type de la WAPE entre les 6 fenêtres — un modèle instable peut avoir une bonne "
        "moyenne mais une fiabilité opérationnelle douteuse._",
        "",
        stability.to_markdown(index=False, floatfmt=".4f"),
        "",
        "## 10. Meilleur modèle par segment",
        "",
        "**Produits classe ABC = A** (recalculée par fenêtre sur le train uniquement) :",
        "",
        abc_a_ranking.to_markdown(index=False, floatfmt=".4f"),
        "",
        "**Séries au profil intermittent** (ADI/CV², recalculé par fenêtre sur le train uniquement) :",
        "",
        intermittent_ranking.to_markdown(index=False, floatfmt=".4f"),
        "",
        "## 11. Sélection du seuil",
        "",
        f"- **Meilleur modèle, périmètre comparable :** {seuil_modele['modele']} — "
        f"WAPE {seuil_modele['WAPE']:.4f}",
        f"- **Meilleure baseline simple :** "
        f"{principale[principale.modele.isin(simple_models)].iloc[0]['modele']} — "
        f"WAPE {principale[principale.modele.isin(simple_models)].iloc[0]['WAPE']:.4f}",
        f"- **Meilleur modèle statistique :** "
        f"{principale[principale.modele.isin(stat_models)].iloc[0]['modele']} — "
        f"WAPE {principale[principale.modele.isin(stat_models)].iloc[0]['WAPE']:.4f}",
        f"- **Modèle le plus stable entre fenêtres :** {modele_plus_stable['modele']} — "
        f"écart-type WAPE {modele_plus_stable['WAPE_ecart_type']:.4f}",
        f"- **Modèle le moins biaisé :** {modele_moins_biaise['modele']} — "
        f"biais {modele_moins_biaise['biais']:+.4f}",
        f"- **Meilleur modèle sur les produits classe A :** "
        f"{abc_a_ranking.iloc[0]['modele']} — WAPE {abc_a_ranking.iloc[0]['WAPE']:.4f}",
        f"- **Meilleur modèle sur les séries intermittentes :** "
        f"{intermittent_ranking.iloc[0]['modele']} — WAPE {intermittent_ranking.iloc[0]['WAPE']:.4f}",
        "",
        "**AutoARIMA est marqué NON COMPARABLE sur la fenêtre 4** pour cause de couverture "
        "insuffisante (4,6 % < 90 %) et d'un coût de 8 h 07 sur cette seule fenêtre — à peser "
        "explicitement dans le choix final, indépendamment de sa métrique agrégée.",
        "",
        f"**Seuil que LightGBM devra battre (périmètre comparable) : "
        f"WAPE < {seuil_modele['WAPE']:.4f}** (modèle {seuil_modele['modele']}).",
        "",
        "Aucun modèle n'est sélectionné comme définitif à ce stade.",
    ]

    report = "\n".join(str(l) for l in lines)
    (PROJECT_ROOT / "reports" / "18_backtest_rapport_final.md").write_text(report, encoding="utf-8")
    logger.info("Rapport final écrit : reports/18_backtest_rapport_final.md")


if __name__ == "__main__":
    main()
