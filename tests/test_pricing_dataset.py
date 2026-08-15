"""Tests du dataset pricing — séparation stricte des grandeurs de prix."""

from __future__ import annotations

import pandas as pd
import pytest

from src.data.build_pricing_dataset import build_pricing_dataset


@pytest.fixture
def table() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "unique_id": ["P1", "P1", "P2"],
            "ds": pd.to_datetime(["2025-01-01", "2025-01-02", "2025-01-01"]),
            "categorie": ["Maison", "Maison", "Sport"],
            "marque": ["A", "A", "B"],
            "y": [2.0, 0.0, 1.0],
            "ca": [1900.0, 0.0, 800.0],
            "prix_catalogue": [1000.0, 1000.0, 1000.0],
            "prix_realise": [950.0, float("nan"), 800.0],
            "remise_pct": [5.0, 0.0, 20.0],
            "en_promotion": [1, 0, 1],
            "n_promotions": [1, 0, 1],
        }
    )


@pytest.fixture
def couts() -> pd.Series:
    return pd.Series({"P1": 600.0, "P2": 750.0})


def test_prix_catalogue_et_prix_paye_restent_distincts(table, couts):
    out, _ = build_pricing_dataset(table, couts)
    assert (out["prix_catalogue_xof"] == 1000.0).all()
    assert out.loc[0, "prix_unitaire_paye_xof"] == 950.0
    assert out["prix_catalogue_xof"].iloc[0] != out["prix_unitaire_paye_xof"].iloc[0]


def test_prix_paye_manquant_les_jours_sans_vente(table, couts):
    out, _ = build_pricing_dataset(table, couts)
    assert pd.isna(out.loc[1, "prix_unitaire_paye_xof"])


def test_remise_appliquee_deduite_du_prix_paye(table, couts):
    out, _ = build_pricing_dataset(table, couts)
    # 950 / 1000 = 0.95 -> remise appliquée 5%, cohérente avec la remise planifiée
    assert out.loc[0, "remise_appliquee_pct"] == pytest.approx(5.0)


def test_marge_calculee_seulement_si_cout_fourni(table):
    out, report = build_pricing_dataset(table, cout_par_produit=None)
    assert "marge_unitaire_xof" not in out.columns
    assert report.marge_totale_xof == 0.0


def test_marge_totale_formule_exacte(table, couts):
    out, report = build_pricing_dataset(table, couts)
    # P1 jour 1 : ca=1900, cout=600, y=2 -> marge = 1900 - 600*2 = 700
    assert out.loc[0, "marge_totale_xof"] == pytest.approx(700.0)
    assert report.marge_totale_xof == pytest.approx(out["marge_totale_xof"].sum())


def test_aucune_ligne_perdue_ni_dupliquee(table, couts):
    out, _ = build_pricing_dataset(table, couts)
    assert len(out) == len(table)
