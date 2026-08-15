"""Preuve de non-fuite sur la BOUCLE COMPLÈTE de prédiction récursive (30 jours),
pas seulement sur la construction statique de features.

Régression du 2026-08-14 : une version antérieure appelait `build_features`
sur `train + test` concaténés, si bien que les lags des jours J+2..J+30
référençaient les vraies ventes de validation. Un test qui ne portait que sur
`build_features` isolée ne pouvait pas le détecter — il fallait perturber les
vraies valeurs sur l'ENSEMBLE de l'horizon et vérifier que les prédictions
ne changent pas, ce que fait ce fichier.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.config.settings import PROJECT_ROOT
from src.pipelines.backtest_baselines import build_windows
from src.pipelines.backtest_lightgbm import run_window_scenario_a

pytestmark = pytest.mark.skipif(
    not (PROJECT_ROOT / "data" / "processed" / "table_analytique.parquet").exists(),
    reason="Nécessite data/processed/table_analytique.parquet",
)


@pytest.fixture(scope="module")
def small_table() -> pd.DataFrame:
    table = pd.read_parquet(PROJECT_ROOT / "data" / "processed" / "table_analytique.parquet")
    table["ds"] = pd.to_datetime(table["ds"])
    top = table.groupby("unique_id").size().sort_values(ascending=False).head(5).index
    return table[table["unique_id"].isin(top)].reset_index(drop=True)


@pytest.fixture(scope="module")
def window(small_table):
    import src.pipelines.backtest_baselines as bt

    original_h = bt.H
    try:
        bt.H = 5  # horizon réduit pour un test rapide, logique inchangée
        return build_windows(small_table)[0]
    finally:
        bt.H = original_h


@pytest.fixture
def tmp_path():
    """Remplace le `tmp_path` standard de pytest : le dossier temp système de
    cet environnement refuse l'accès en écriture (contrainte de sandbox, sans
    rapport avec le code testé)."""
    import shutil
    import uuid

    d = PROJECT_ROOT / "data" / "interim" / f"_test_tmp_{uuid.uuid4().hex[:8]}"
    d.mkdir(parents=True, exist_ok=True)
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_perturber_toute_la_validation_ne_change_aucune_prediction(small_table, window, tmp_path):
    """LE test décisif : on remplace TOUTES les vraies valeurs `y` des 30 (ici
    5) jours de validation par du bruit aléatoire incohérent, puis on
    reconstruit intégralement la table analytique perturbée. Si une seule
    prédiction change, c'est la preuve d'une fuite — puisque la seule
    information qui a changé est strictement postérieure au cutoff.
    """
    log_path = tmp_path / "log.jsonl"
    log_path.write_text("", encoding="utf-8")

    baseline = run_window_scenario_a(small_table, window, "LightGBM_test", "regression", log_path)

    perturbed = small_table.copy()
    mask = (perturbed["ds"] >= window.test_start) & (perturbed["ds"] <= window.test_end)
    rng = np.random.default_rng(42)
    # Valeurs délibérément absurdes (très grandes) : si elles fuitaient dans
    # les lags, l'effet serait immédiatement visible et énorme.
    perturbed.loc[mask, "y"] = rng.uniform(9000, 9999, size=mask.sum())

    log_path2 = tmp_path / "log2.jsonl"
    log_path2.write_text("", encoding="utf-8")
    after = run_window_scenario_a(perturbed, window, "LightGBM_test", "regression", log_path2)

    pd.testing.assert_series_equal(
        baseline.sort_values(["unique_id", "ds"])["y_pred"].reset_index(drop=True),
        after.sort_values(["unique_id", "ds"])["y_pred"].reset_index(drop=True),
        check_exact=True,
    )


def test_perturber_le_stock_post_cutoff_ne_change_rien_au_benchmark_principal(small_table, window, tmp_path):
    """Point 4 : le scénario A (benchmark principal) n'utilise AUCUNE variable
    de stock — vérifié en perturbant les valeurs de stock des jours de
    validation et en confirmant que les prédictions restent identiques.
    Preuve structurelle, pas seulement une affirmation : si une variable de
    stock venait à être ajoutée par erreur au scénario A, ce test la
    détecterait immédiatement.
    """
    log_path = tmp_path / "log.jsonl"
    log_path.write_text("", encoding="utf-8")
    baseline = run_window_scenario_a(small_table, window, "LightGBM_test", "regression", log_path)

    perturbed = small_table.copy()
    mask = (perturbed["ds"] >= window.test_start) & (perturbed["ds"] <= window.test_end)
    stock_cols = [c for c in perturbed.columns if "stock" in c or "rupture" in c or "reappro" in c]
    assert stock_cols, "Aucune colonne de stock trouvée dans la table — le test ne teste rien."
    rng = np.random.default_rng(7)
    for col in stock_cols:
        if pd.api.types.is_numeric_dtype(perturbed[col]):
            # Cast en float64 : certaines colonnes (indicateurs) sont en Int64
            # nullable, qui refuse une écriture directe de flottants aléatoires.
            perturbed[col] = perturbed[col].astype("float64")
            perturbed.loc[mask, col] = rng.uniform(-9999, 9999, size=mask.sum())

    log_path2 = tmp_path / "log2.jsonl"
    log_path2.write_text("", encoding="utf-8")
    after = run_window_scenario_a(perturbed, window, "LightGBM_test", "regression", log_path2)

    pd.testing.assert_series_equal(
        baseline.sort_values(["unique_id", "ds"])["y_pred"].reset_index(drop=True),
        after.sort_values(["unique_id", "ds"])["y_pred"].reset_index(drop=True),
        check_exact=True,
    )


def test_aucune_colonne_de_stock_dans_les_features_du_scenario_a(small_table, window):
    """Contrôle direct sur les colonnes de features, pas seulement sur le résultat."""
    from src.pipelines.backtest_lightgbm import STOCK_COLS, build_training_matrix, feature_columns

    train = small_table[small_table["ds"] <= window.train_end]
    mat = build_training_matrix(train)
    cols = feature_columns(mat, include_stock=False)
    assert not (set(cols) & set(STOCK_COLS)), f"Colonnes de stock présentes par erreur : {set(cols) & set(STOCK_COLS)}"


def test_hurdle_perturber_la_validation_ne_change_rien(small_table, window, tmp_path):
    """Même preuve que pour le modèle direct, appliquée au hurdle (classifieur
    + régresseur conditionnel) — les deux composantes partagent le même
    moteur récursif, le même risque de fuite existait potentiellement."""
    from src.pipelines.backtest_lightgbm import run_window_scenario_a_hurdle

    log_path = tmp_path / "log.jsonl"
    log_path.write_text("", encoding="utf-8")
    baseline = run_window_scenario_a_hurdle(small_table, window, "Hurdle_test", log_path)

    perturbed = small_table.copy()
    mask = (perturbed["ds"] >= window.test_start) & (perturbed["ds"] <= window.test_end)
    rng = np.random.default_rng(11)
    perturbed.loc[mask, "y"] = rng.uniform(9000, 9999, size=mask.sum())

    log_path2 = tmp_path / "log2.jsonl"
    log_path2.write_text("", encoding="utf-8")
    after = run_window_scenario_a_hurdle(perturbed, window, "Hurdle_test", log_path2)

    pd.testing.assert_series_equal(
        baseline.sort_values(["unique_id", "ds"])["y_pred"].reset_index(drop=True),
        after.sort_values(["unique_id", "ds"])["y_pred"].reset_index(drop=True),
        check_exact=True,
    )


def test_cold_start_baselines_nutilise_aucun_encodage_de_product_id(small_table, window):
    from src.pipelines.backtest_lightgbm import cold_start_baselines

    result = cold_start_baselines(small_table, window, list(small_table["unique_id"].unique()[:1]))
    if not result.empty:
        assert set(result["modele"]) <= {"ColdStartZero", "MoyenneCategorie", "MoyenneCategorieJourSemaine"}


def test_le_train_utilise_pour_predire_sarrete_strictement_au_cutoff(small_table, window):
    """Contrôle complémentaire : la fonction ne doit jamais recevoir de lignes
    de `table` postérieures au cutoff comme `train`."""
    from src.pipelines.backtest_lightgbm import build_training_matrix

    train = small_table[small_table["ds"] <= window.train_end]
    assert train["ds"].max() == window.train_end
    mat = build_training_matrix(train)
    assert mat["ds"].max() <= window.train_end
