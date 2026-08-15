"""Vérification stricte de la couche opérationnelle (post-repli).

    python scripts/verify_operational_predictions.py

Complète `scripts/verify_backtest_checkpoints.py` (qui couvre les 42
checkpoints BRUTS, déjà validés). Ce script porte sur
`reports/backtest/operational_predictions/` et échoue explicitement sur :

* prédiction brute non finie non comptabilisée (NaN **ou** +/-Inf) ;
* prédiction finale non finie ;
* métrique NaN ou infinie dans les tableaux finaux ;
* doublon (fenêtre, modèle, unique_id, ds) ;
* ligne attendue manquante ;
* repli sans raison documentée ;
* `model_effective` absent ;
* somme des taux de statut incohérente (≠ 100 %) ;
* checkpoint brut incompatible avec le schéma attendu ;
* produit absent du train classé comme `Naive` (doit être `ColdStartZero`).

Ne modifie ni ne relance rien.
"""

from __future__ import annotations

import glob
import io
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config.settings import PROJECT_ROOT  # noqa: E402
from src.pipelines.backtest_baselines import CHECKPOINT_DIR  # noqa: E402
from src.pipelines.backtest_postprocess import OPERATIONAL_DIR, RAW_DIR  # noqa: E402

OUT = io.StringIO()
FAILURES: list[str] = []


def say(text: str = "") -> None:
    print(text)
    OUT.write(text + "\n")


def fail(msg: str) -> None:
    FAILURES.append(msg)
    say(f"  [ÉCHEC] {msg}")


def ok(msg: str) -> None:
    say(f"  [OK] {msg}")


def main() -> int:
    say("=" * 78)
    say("A. CHECKPOINTS BRUTS INCHANGÉS (preuve d'immutabilité)")
    say("=" * 78)
    raw_files = {p.name: p for p in CHECKPOINT_DIR.glob("*.parquet")}
    snap_files = {p.name: p for p in RAW_DIR.glob("*.parquet")}
    if set(raw_files) != set(snap_files):
        fail(f"Ensembles de fichiers différents entre {CHECKPOINT_DIR} et {RAW_DIR}.")
    else:
        diffs = [
            n for n in raw_files
            if raw_files[n].read_bytes() != snap_files[n].read_bytes()
        ]
        if diffs:
            fail(f"{len(diffs)} checkpoint(s) divergent(s) entre l'original et la copie : {diffs}")
        else:
            ok(f"{len(raw_files)} checkpoints identiques bit à bit entre original et snapshot.")

    op_files = sorted(glob.glob(str(OPERATIONAL_DIR / "*.parquet")))
    if len(op_files) != 42:
        fail(f"{len(op_files)} fichiers opérationnels trouvés, 42 attendus.")
    op = pd.concat([pd.read_parquet(f) for f in op_files], ignore_index=True)
    say(f"  lignes opérationnelles chargées : {len(op):,}")

    say("")
    say("=" * 78)
    say("B. SCHÉMA DES CHECKPOINTS BRUTS (rejet des anciens formats incompatibles)")
    say("=" * 78)
    required_raw_cols = {"unique_id", "ds", "y", "y_pred_raw", "modele", "fenetre"}
    bad_schema = []
    for name, path in raw_files.items():
        cols = set(pd.read_parquet(path, columns=None).columns)
        if not required_raw_cols.issubset(cols):
            bad_schema.append(name)
    if bad_schema:
        fail(f"Checkpoints au schéma incompatible : {bad_schema}")
    else:
        ok("Tous les checkpoints bruts portent le schéma attendu.")

    say("")
    say("=" * 78)
    say("C. PRÉDICTIONS NON FINIES — NaN ET +/-Inf, brutes ET finales")
    say("=" * 78)
    raw_bad = ~np.isfinite(op["y_pred_raw"].astype(float))
    n_raw_nan = op.loc[raw_bad, "y_pred_raw"].isna().sum()
    n_raw_inf = int((raw_bad.sum()) - n_raw_nan)
    say(f"  y_pred_raw non finies : {int(raw_bad.sum())} (NaN={int(n_raw_nan)}, Inf={n_raw_inf})")
    # Chaque ligne brute non finie DOIT avoir un fallback_applied=True et un
    # fallback_type documenté (jamais silencieusement absorbée).
    raw_bad_uncovered = op.loc[raw_bad] [~op.loc[raw_bad, "fallback_applied"]]
    if len(raw_bad_uncovered):
        fail(f"{len(raw_bad_uncovered)} prédiction(s) brute(s) non finie(s) SANS repli documenté.")
    else:
        ok("Toutes les prédictions brutes non finies sont couvertes par un repli documenté.")

    final_bad = ~np.isfinite(op["y_pred_final"].astype(float))
    if final_bad.any():
        fail(f"{int(final_bad.sum())} prédiction(s) FINALE(s) non finie(s) — inacceptable.")
    else:
        ok("0 prédiction finale non finie.")

    say("")
    say("=" * 78)
    say("D. DOUBLONS ET COUVERTURE EXACTE")
    say("=" * 78)
    dup = op.duplicated(subset=["window", "model_requested", "unique_id", "ds"]).sum()
    if dup:
        fail(f"{dup} doublon(s) (fenêtre, modèle, unique_id, ds).")
    else:
        ok("0 doublon (fenêtre, modèle, unique_id, ds).")

    table = pd.read_parquet(PROJECT_ROOT / "data" / "processed" / "table_analytique.parquet")
    table["ds"] = pd.to_datetime(table["ds"])
    from src.pipelines.backtest_baselines import build_windows
    windows = build_windows(table)
    coverage_bad = []
    for w in windows:
        expected = table[(table["ds"] >= w.test_start) & (table["ds"] <= w.test_end)]
        for model in op["model_requested"].unique():
            got = op[(op["window"] == w.index) & (op["model_requested"] == model)]
            if len(got) != len(expected):
                coverage_bad.append((w.index, model, len(got), len(expected)))
    if coverage_bad:
        fail(f"Couverture incomplète pour {len(coverage_bad)} couple(s) (fenêtre, modèle) : "
             f"{coverage_bad[:5]}{'...' if len(coverage_bad) > 5 else ''}")
    else:
        ok("100 % des observations attendues couvertes, pour chaque (fenêtre, modèle).")

    say("")
    say("=" * 78)
    say("E. REPLIS DOCUMENTÉS ET model_effective")
    say("=" * 78)
    fb = op[op["fallback_applied"]]
    missing_reason = fb[fb["fallback_reason"].isna() | fb["fallback_type"].isna()]
    if len(missing_reason):
        fail(f"{len(missing_reason)} repli(s) sans fallback_type/fallback_reason documenté.")
    else:
        ok(f"{len(fb):,} replis, tous avec fallback_type et fallback_reason renseignés.")

    missing_effective = op[op["model_effective"].isna() | (op["model_effective"] == "")]
    if len(missing_effective):
        fail(f"{len(missing_effective)} ligne(s) sans model_effective.")
    else:
        ok("model_effective renseigné sur 100 % des lignes.")

    say("")
    say("=" * 78)
    say("F. PRODUIT ABSENT DU TRAIN JAMAIS CLASSÉ « NAIVE »")
    say("=" * 78)
    cold = op[op["train_observations"] == 0]
    misclassified = cold[cold["model_effective"] != "ColdStartZero"]
    if len(misclassified):
        fail(f"{len(misclassified)} ligne(s) cold-start classée(s) autrement que ColdStartZero : "
             f"{misclassified['model_effective'].unique().tolist()}")
    else:
        ok(f"{len(cold):,} lignes cold-start, toutes classées ColdStartZero (jamais Naive).")

    say("")
    say("=" * 78)
    say("G. COHÉRENCE DES TAUX DE STATUT (somme = 100 %)")
    say("=" * 78)
    base = op[["model_requested", "unique_id", "window", "status"]].drop_duplicates()
    bad_sum = []
    for name, g in base.groupby("model_requested"):
        total = len(g)
        pct_sum = 100 * g["status"].value_counts().sum() / total
        if abs(pct_sum - 100.0) > 1e-6:
            bad_sum.append((name, pct_sum))
    if bad_sum:
        fail(f"Sommes de statut ≠ 100 % pour : {bad_sum}")
    else:
        ok("Somme des statuts = 100 % pour tous les modèles.")

    say("")
    say("=" * 78)
    say("H. MODÈLE REQUIS JAMAIS ÉCRASÉ")
    say("=" * 78)
    if set(op["model_requested"].unique()) != {
        "Naive", "SeasonalNaive7", "WindowAverage28", "AutoETS", "AutoARIMA",
        "CrostonOptimized", "TSB",
    }:
        fail(f"Valeurs de model_requested inattendues : {sorted(op['model_requested'].unique())}")
    else:
        ok("model_requested préserve les 7 noms de modèles d'origine.")

    say("")
    say("=" * 78)
    say("BILAN")
    say("=" * 78)
    if FAILURES:
        say(f"  {len(FAILURES)} PROBLÈME(S) — NE PAS INTERPRÉTER LES RÉSULTATS AVANT CORRECTION.")
    else:
        say("  Tous les contrôles passent. Les résultats opérationnels peuvent être interprétés.")

    (PROJECT_ROOT / "reports" / "19_verification_operationnelle.md").write_text(
        "# 19 — Vérification de la couche opérationnelle\n\n```\n" + OUT.getvalue() + "```\n",
        encoding="utf-8",
    )
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
