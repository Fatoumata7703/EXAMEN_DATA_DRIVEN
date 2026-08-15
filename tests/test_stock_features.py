"""Tests des variables stock — non-fuite, exactitude sur cas synthétiques.

`niveau_stock` est un stock de FIN de journée : le test le plus important de
ce fichier est celui qui vérifie qu'aucune variable utilisable pour prévoir J
ne dépend du stock du jour J lui-même.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.features.stock import StockConfig, build_stock_features, censorship_mask


def _stock_df(values: list[int], start: str = "2025-01-01") -> pd.DataFrame:
    dates = pd.date_range(start, periods=len(values), freq="D")
    return pd.DataFrame({"unique_id": "P1", "ds": dates, "niveau_stock": values})


# ---------------------------------------------------------------------------
# Non-fuite : le cœur du contrat de ce module
# ---------------------------------------------------------------------------
def test_stock_lag1_ne_contient_jamais_la_valeur_du_jour():
    df = _stock_df([100, 90, 80, 70, 60])
    out = build_stock_features(df)
    # stock_disponible_lag1(J) doit être stock_fin_jour(J-1), jamais celui de J
    attendu = out["stock_fin_jour"].shift(1)
    pd.testing.assert_series_equal(
        out["stock_disponible_lag1"], attendu, check_names=False
    )


def test_premiere_observation_sans_lag_est_manquante():
    df = _stock_df([100, 90, 80])
    out = build_stock_features(df)
    assert pd.isna(out["stock_disponible_lag1"].iloc[0])
    assert pd.isna(out["indicateur_rupture_lag1"].iloc[0])


def test_indicateur_rupture_utilise_le_seuil_documente():
    # Seuil = 20 : stock_veille de 15 -> rupture ; de 25 -> pas de rupture.
    df = _stock_df([15, 25, 10])
    out = build_stock_features(df, StockConfig(seuil_rupture=20))
    # J1 : lag=NaN. J2 : lag=15 -> rupture=1. J3 : lag=25 -> rupture=0.
    assert out["indicateur_rupture_lag1"].iloc[1] == 1
    assert out["indicateur_rupture_lag1"].iloc[2] == 0


def test_rolling_rupture_exclut_le_jour_courant():
    """Régression ciblée : une fenêtre glissante mal décalée inclurait J."""
    # Rupture les jours 0..3 (indices), stock au-dessus ensuite.
    df = _stock_df([5, 5, 5, 5, 100, 100])
    out = build_stock_features(df, StockConfig(seuil_rupture=20, rolling_windows=(3,)))
    # Au jour 4 (100, pas en rupture), la fenêtre de 3 jours précédents (1,2,3)
    # doit compter 3 jours de rupture passés, sans compter le jour 4 lui-même.
    assert out["jours_rupture_lag_3"].iloc[4] == 3
    # Au jour 0, aucune fenêtre passée : NaN (rien à décaler).
    assert pd.isna(out["jours_rupture_lag_3"].iloc[0]) or out["jours_rupture_lag_3"].iloc[0] == 0


def test_jours_depuis_derniere_rupture_ne_regarde_pas_le_futur():
    # Rupture au jour 1 (stock=10), puis stock sain ensuite.
    df = _stock_df([100, 10, 90, 90, 90])
    out = build_stock_features(df, StockConfig(seuil_rupture=20))
    # Au jour 2, on vient d'apprendre (via le stock de clôture du jour 1) que
    # la veille était en rupture : 0 jour d'écart, pas 1 — sans quoi la donnée
    # ne serait disponible qu'après le jour 2, ce qui serait une fuite inverse.
    assert out["jours_depuis_derniere_rupture"].iloc[2] == 0
    # Au jour 4, 2 jours se sont écoulés depuis cette observation (jour 2 -> jour 4).
    assert out["jours_depuis_derniere_rupture"].iloc[4] == 2


# ---------------------------------------------------------------------------
# Cas synthétique complet, avec vérité connue
# ---------------------------------------------------------------------------
def test_scenario_avec_reappro_connu():
    """Stock descend sous le seuil puis un réapprovisionnement le relève."""
    # J0=50, J1=30 (vente), J2=15 (vente, sous seuil 20), J3=200 (réappro), J4=190
    df = _stock_df([50, 30, 15, 200, 190])
    out = build_stock_features(df, StockConfig(seuil_rupture=20))

    assert out["indicateur_rupture_lag1"].iloc[3] == 1  # veille (J2=15) en rupture
    assert out["indicateur_rupture_lag1"].iloc[4] == 0  # veille (J3=200) saine
    # Le réapprovisionnement (hausse J2->J3) n'est observable qu'une fois le
    # stock de clôture de J3 connu, donc pas encore au jour J3 lui-même —
    # seulement à partir de J4 (0 jour d'écart), sans quoi ce serait une fuite.
    assert pd.isna(out["jours_depuis_dernier_reappro"].iloc[3])
    assert out["jours_depuis_dernier_reappro"].iloc[4] == 0


def test_censorship_mask_ne_marque_que_rupture_ET_vente_nulle():
    df = _stock_df([50, 10, 10, 10])  # veille en rupture à partir du jour 2
    features = build_stock_features(df, StockConfig(seuil_rupture=20))
    ventes = pd.Series([5, 0, 3, 0])  # vente positive malgré rupture au jour 2
    mask = censorship_mask(features, ventes)
    assert mask.iloc[0] == 0  # pas de lag -> jamais censuré
    assert mask.iloc[1] == 0  # veille=50, pas en rupture
    assert mask.iloc[2] == 0  # en rupture MAIS vente positive : pas censuré
    assert mask.iloc[3] == 1  # en rupture ET vente nulle : censuré


def test_plusieurs_produits_sont_traites_independamment():
    df = pd.concat(
        [
            _stock_df([100, 10, 100], start="2025-01-01").assign(unique_id="A"),
            _stock_df([5, 5, 5], start="2025-01-01").assign(unique_id="B"),
        ],
        ignore_index=True,
    )
    out = build_stock_features(df, StockConfig(seuil_rupture=20))
    a = out[out.unique_id == "A"].reset_index(drop=True)
    b = out[out.unique_id == "B"].reset_index(drop=True)
    assert a["indicateur_rupture_lag1"].iloc[1] == 0  # A : veille=100 -> pas rupture

    # Le produit B, toujours sous le seuil, ne doit jamais "hériter" de l'état de A.
    assert b["indicateur_rupture_lag1"].iloc[1] == 1
    assert b["indicateur_rupture_lag1"].iloc[2] == 1


# ---------------------------------------------------------------------------
# Validation contre les chiffres mesurés sur la livraison réelle
# ---------------------------------------------------------------------------
@pytest.mark.skipif(
    not (pd.io.common.file_exists if hasattr(pd.io.common, "file_exists") else lambda p: False)(
        "data/raw/fact_stock.parquet"
    ),
    reason="Nécessite data/raw/fact_stock.parquet (python -m src.pipelines.audit)",
)
def test_coherent_avec_le_constat_mesure_sur_la_livraison():
    """Non-régression du constat du 2026-08-13 : le stock ne descend jamais
    sous 21 dans cette livraison ; l'indicateur de rupture doit donc être
    quasi toujours à 0, pas une erreur de calcul."""
    from src.data.build_dataset import parse_date_key

    stock = pd.read_parquet("data/raw/fact_stock.parquet")
    stock["ds"] = parse_date_key(stock["date_key"])
    stock = stock.rename(columns={"produit_key": "unique_id"})
    out = build_stock_features(stock[["unique_id", "ds", "niveau_stock"]])
    taux_rupture = out["indicateur_rupture_lag1"].dropna().astype(int).mean()
    assert taux_rupture == 0.0, (
        "Le taux de rupture mesuré a changé : la livraison a peut-être été "
        "mise à jour. Revalider reports/13_validation_stock.md avant de "
        "continuer à supposer l'absence de censure."
    )
