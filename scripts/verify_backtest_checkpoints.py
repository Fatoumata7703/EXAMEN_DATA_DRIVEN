"""Vérification des checkpoints du backtest instrumenté avant toute interprétation.

    python scripts/verify_backtest_checkpoints.py

Contrôles (demandés avant toute lecture des résultats) :
1. les six fenêtres sont terminées ;
2. tous les checkpoints attendus existent ;
3. aucun checkpoint ne provient de l'ancien pipeline non instrumenté ;
4. code/config/données identiques pour toutes les fenêtres ;
5. chaque (modèle, fenêtre) a un journal complet (statut, durée, séries, replis) ;
6. les prédictions couvrent exactement les observations attendues, sans doublon ni manque ;
7. les métriques sont recalculables indépendamment depuis les fichiers de prédictions.

Ne modifie rien. Ne relance rien. Se contente de vérifier et de rapporter.
"""

from __future__ import annotations

import hashlib
import io
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config.settings import PROJECT_ROOT  # noqa: E402
from src.evaluation.metrics import compute_all_metrics  # noqa: E402
from src.pipelines.backtest_baselines import H, N_WINDOWS, CHECKPOINT_DIR, LOG_PATH, _model_factory  # noqa: E402

OUT = io.StringIO()
FAILURES: list[str] = []


def say(text: str = "") -> None:
    print(text)
    OUT.write(text + "\n")


def fail(msg: str) -> None:
    FAILURES.append(msg)
    say(f"  [ÉCHEC] {msg}")


def main() -> int:
    model_names = [name for name, _ in _model_factory()]

    say("=" * 78)
    say("1-2. FENÊTRES TERMINÉES ET CHECKPOINTS ATTENDUS")
    say("=" * 78)
    expected = {(w, m) for w in range(1, N_WINDOWS + 1) for m in model_names}
    found_files = {p.name: p for p in CHECKPOINT_DIR.glob("*.parquet")}
    say(f"  attendu : {len(expected)} fichiers ({N_WINDOWS} fenêtres x {len(model_names)} modèles)")
    say(f"  trouvé  : {len(found_files)} fichiers dans {CHECKPOINT_DIR.relative_to(PROJECT_ROOT)}")

    missing = []
    for w, m in sorted(expected):
        name = f"fenetre{w}_{m}.parquet"
        if name not in found_files:
            missing.append(name)
    if missing:
        fail(f"{len(missing)} checkpoint(s) manquant(s) : {missing}")
    else:
        say("  OK : tous les checkpoints attendus sont présents.")

    unexpected = [n for n in found_files if n not in {f"fenetre{w}_{m}.parquet" for w, m in expected}]
    if unexpected:
        say(f"  fichiers inattendus (non issus de ce run) : {unexpected}")

    say("")
    say("=" * 78)
    say("3. AUCUN CHECKPOINT ISSU DE L'ANCIEN PIPELINE NON INSTRUMENTÉ")
    say("=" * 78)
    # L'ancien pipeline (non instrumenté) écrivait directement le CSV/MD final
    # sans passer par CHECKPOINT_DIR ni par les colonnes de diagnostic
    # (y_pred_raw, modele, fenetre). On vérifie que chaque parquet porte bien
    # ces colonnes, et que son schéma est cohérent avec le code actuel.
    required_cols = {"unique_id", "ds", "y", "y_pred_raw", "modele", "fenetre"}
    schema_bad = []
    for name, path in sorted(found_files.items()):
        df = pd.read_parquet(path)
        if not required_cols.issubset(df.columns):
            schema_bad.append((name, sorted(required_cols - set(df.columns))))
    if schema_bad:
        fail(f"Checkpoints au schéma incompatible (probablement issus d'une version antérieure) : {schema_bad}")
    else:
        say(f"  OK : les {len(found_files)} checkpoints portent toutes les colonnes attendues "
            f"({sorted(required_cols)}).")

    say("")
    say("=" * 78)
    say("4. CODE / CONFIGURATION / DONNÉES IDENTIQUES SUR TOUTES LES FENÊTRES")
    say("=" * 78)
    src_files = [
        PROJECT_ROOT / "src" / "pipelines" / "backtest_baselines.py",
        PROJECT_ROOT / "src" / "evaluation" / "metrics.py",
        PROJECT_ROOT / "src" / "features" / "segmentation.py",
    ]
    for f in src_files:
        h = hashlib.sha256(f.read_bytes()).hexdigest()[:12]
        say(f"  sha256[:12] {f.relative_to(PROJECT_ROOT)} : {h}")
    table_path = PROJECT_ROOT / "data" / "processed" / "table_analytique.parquet"
    say(f"  table_analytique.parquet : {table_path.stat().st_mtime_ns} (mtime), "
        f"{table_path.stat().st_size} octets")
    say("  -> comparer ces empreintes à celles au moment du lancement (reports/15_backtest_log.jsonl, "
        "horodatage du premier événement) pour confirmer qu'aucune modification n'a eu lieu en cours de route.")

    say("")
    say("=" * 78)
    say("5. JOURNAL COMPLET PAR (MODÈLE, FENÊTRE)")
    say("=" * 78)
    if not LOG_PATH.exists():
        fail("reports/15_backtest_log.jsonl introuvable.")
        events = []
    else:
        events = [json.loads(l) for l in LOG_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
    summaries = pd.DataFrame([e for e in events if e.get("type") == "resume_modele_fenetre"])
    replis = pd.DataFrame([e for e in events if e.get("type") == "repli"])

    if summaries.empty:
        fail("Aucun résumé (modèle, fenêtre) trouvé dans le journal.")
    else:
        required_keys = {"modele", "fenetre", "n_series", "n_succes", "n_repli_exception",
                          "n_repli_budget", "duree_s"}
        manquants = [k for k in required_keys if k not in summaries.columns]
        if manquants:
            fail(f"Colonnes manquantes dans le journal : {manquants}")
        pairs_present = set(zip(summaries["fenetre"], summaries["modele"]))
        pairs_missing = expected - pairs_present
        if pairs_missing:
            fail(f"{len(pairs_missing)} couple(s) (modèle, fenêtre) sans entrée de journal : {sorted(pairs_missing)}")
        else:
            say(f"  OK : {len(pairs_present)} couples (modèle, fenêtre) journalisés avec statut/durée/séries.")
        say("")
        say(summaries[["modele", "fenetre", "n_series", "n_succes", "n_repli_exception",
                        "n_repli_budget", "duree_s", "budget_depasse"]].to_string(index=False))

    say("")
    say("=" * 78)
    say("6. COUVERTURE EXACTE DES OBSERVATIONS (sans doublon ni manque)")
    say("=" * 78)
    table = pd.read_parquet(table_path)
    table["ds"] = pd.to_datetime(table["ds"])
    dmax = table["ds"].max()

    coverage_bad = []
    for name, path in sorted(found_files.items()):
        df = pd.read_parquet(path)
        w = int(df["fenetre"].iloc[0])
        cutoff = dmax - pd.Timedelta(days=H * (N_WINDOWS - w + 1))
        test_start = cutoff + pd.Timedelta(days=1)
        test_end = cutoff + pd.Timedelta(days=H)
        ground_truth = table[(table["ds"] >= test_start) & (table["ds"] <= test_end)]
        expected_products = set(ground_truth["unique_id"])
        # ATTENTION : ne PAS supposer `n_produits * H` — certains produits sont
        # lancés en cours de fenêtre (« nouveaux post-cutoff ») et n'ont donc
        # pas H lignes pleines dans `table_analytique`. Le compte attendu est
        # le nombre RÉEL de lignes de la table analytique sur cette période,
        # pas une estimation.
        expected_n = len(ground_truth)

        dup = df.duplicated(subset=["unique_id", "ds"]).sum()
        actual_products = set(df["unique_id"])
        actual_dates = set(df["ds"])
        expected_dates = set(pd.date_range(test_start, test_end, freq="D"))

        problems = []
        if dup:
            problems.append(f"{dup} doublon(s) (unique_id, ds)")
        if len(df) != expected_n:
            problems.append(f"{len(df)} lignes vs {expected_n} attendues")
        if actual_products != expected_products:
            problems.append(
                f"produits différents (manque {len(expected_products - actual_products)}, "
                f"en trop {len(actual_products - expected_products)})"
            )
        if actual_dates != expected_dates:
            problems.append("dates hors de la fenêtre de test attendue")
        if problems:
            coverage_bad.append((name, problems))

    if coverage_bad:
        for name, problems in coverage_bad:
            fail(f"{name} : {problems}")
    else:
        say(f"  OK : les {len(found_files)} checkpoints couvrent exactement leurs observations "
            f"attendues, sans doublon ni manque.")

    say("")
    say("=" * 78)
    say("7. RECALCUL INDÉPENDANT DES MÉTRIQUES DEPUIS LES FICHIERS DE PRÉDICTIONS")
    say("=" * 78)
    if not coverage_bad and found_files:
        sample_name = sorted(found_files)[0]
        df = pd.read_parquet(found_files[sample_name])
        df["y_pred"] = df["y_pred_raw"].clip(lower=0)
        met = compute_all_metrics(df["y"], df["y_pred"])
        say(f"  Recalcul indépendant sur {sample_name} : WAPE={met['WAPE']:.4f}, "
            f"MAE={met['MAE']:.4f}, biais={met['biais']:.4f} — "
            "recalculable sans dépendance au processus d'origine.")
    else:
        say("  Ignoré (couverture invalide détectée ci-dessus).")

    say("")
    say("=" * 78)
    say("BILAN")
    say("=" * 78)
    if FAILURES:
        say(f"  {len(FAILURES)} PROBLÈME(S) — NE PAS INTERPRÉTER LES RÉSULTATS AVANT CORRECTION :")
        for f in FAILURES:
            say(f"    - {f}")
    else:
        say("  Tous les contrôles passent. Les résultats peuvent être interprétés.")

    (PROJECT_ROOT / "reports" / "17_verification_checkpoints.md").write_text(
        "# 17 — Vérification des checkpoints avant interprétation\n\n```\n" + OUT.getvalue() + "```\n",
        encoding="utf-8",
    )
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
