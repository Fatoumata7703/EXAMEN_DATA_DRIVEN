"""Tests unitaires des garde-fous de construction (sans base ni artefacts)."""

from __future__ import annotations

import pandas as pd
import pytest

from src.data.build_dataset import (
    ColumnCollisionError,
    UnresolvedColumnError,
    resolve_attribute_mapping,
)
from src.data.mapping import best_join_column
from src.features.promotions import resolve_scope_attributes


# ---------------------------------------------------------------------------
# Collisions de renommage
# ---------------------------------------------------------------------------
def test_deux_sources_vers_une_meme_destination_est_refuse():
    """Régression : `categorie` et `product_id` visaient tous deux `product_id`."""
    with pytest.raises(ColumnCollisionError, match="même nom final"):
        resolve_attribute_mapping(
            {"categorie": "product_id", "product_id": "product_id"},
            available=["categorie", "product_id"],
        )


def test_une_source_vers_deux_destinations_est_refuse():
    with pytest.raises(ColumnCollisionError, match="deux destinations"):
        resolve_attribute_mapping(
            [("categorie", "categorie"), ("categorie", "product_id")],
            available=["categorie"],
        )


def test_mapping_valide_est_accepte():
    out = resolve_attribute_mapping(
        {"categorie": "categorie", "product_id": "product_id"},
        available=["categorie", "product_id", "marque"],
    )
    assert out == {"categorie": "categorie", "product_id": "product_id"}


def test_colonne_absente_est_ignoree_si_optionnelle():
    out = resolve_attribute_mapping(
        {"categorie": "categorie", "sous_categorie": "sous_categorie"},
        available=["categorie"],
    )
    assert out == {"categorie": "categorie"}


def test_colonne_indispensable_absente_leve_une_erreur():
    """Plus de repli silencieux : une colonne requise manquante doit échouer."""
    with pytest.raises(UnresolvedColumnError, match="quantite"):
        resolve_attribute_mapping(
            {"quantite": "y"}, available=["montant"], required=["quantite"]
        )


# ---------------------------------------------------------------------------
# Résolution des clés
# ---------------------------------------------------------------------------
def test_clef_de_jointure_choisie_sur_les_valeurs_pas_le_nom():
    """La clé de substitution joint ; la clé naturelle non."""
    faits = pd.Series(["PRD000001", "PRD000002", "PRD000003"])
    dim = pd.DataFrame(
        {
            "produit_key": ["PRD000001", "PRD000002", "PRD000003"],
            "product_id": ["P0001", "P0002", "P0003"],
        }
    )
    col, taux = best_join_column(faits, dim)
    assert col == "produit_key"
    assert taux == 1.0


def test_aucune_clef_si_recouvrement_insuffisant():
    faits = pd.Series(["X1", "X2"])
    dim = pd.DataFrame({"a": ["Y1", "Y2"], "b": ["Z1", "Z2"]})
    col, taux = best_join_column(faits, dim)
    assert col is None
    assert taux == 0.0


# ---------------------------------------------------------------------------
# Portées de promotion
# ---------------------------------------------------------------------------
@pytest.fixture
def produits() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "produit_key": ["PRD1", "PRD2", "PRD3", "PRD4"],
            "product_id": ["P1", "P2", "P3", "P4"],
            "categorie": ["Maison", "Maison", "Sport", "Sport"],
        }
    )


@pytest.fixture
def promotions() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "promo_key": ["PRM1", "PRM2"],
            "scope": ["category", "product"],
            "cible": ["Maison", "P3"],
        }
    )


def test_portees_resolues_separement(produits, promotions):
    """Chaque portée est résolue avec ses seules cibles.

    Régression : en mélangeant les cibles de toutes les portées, `categorie`
    obtenait 100 % de recouvrement et était retenue comme identifiant produit.
    """
    mapping = resolve_scope_attributes(promotions, produits, "scope", "cible")
    assert mapping["category"] == "categorie"
    assert mapping["product"] == "product_id"


def test_portee_produit_exige_une_colonne_unique(produits, promotions):
    """Une colonne non unique ne peut pas identifier un produit."""
    mapping = resolve_scope_attributes(
        promotions, produits, "scope", "cible", unique_scopes={"product"}
    )
    assert mapping["product"] == "product_id"
    assert mapping["product"] != "categorie"


def test_portee_inconnue_est_signalee(produits):
    promos = pd.DataFrame(
        {"promo_key": ["PRM9"], "scope": ["region"], "cible": ["Dakar"]}
    )
    mapping = resolve_scope_attributes(promos, produits, "scope", "cible")
    assert "region" not in mapping
