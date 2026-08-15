"""Tests de normalisation des types après lecture — deux backends, deux formats.

Régression du 2026-08-13 : le backend PostgreSQL direct renvoie des objets
``datetime.date`` natifs (pas des chaînes ISO comme l'API REST). La première
version de `coerce_datetime_columns` ne reconnaissait que les chaînes et
laissait ces colonnes en `object`, ce qui faisait échouer silencieusement la
détection de `valid_from` comme date de début de validité.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pandas as pd
import pytest

from src.data.coercion import coerce_datetime_columns, coerce_decimal_columns


def test_chaines_iso_sont_converties():
    """Cas REST : dates transportées en JSON, donc en chaînes."""
    df = pd.DataFrame({"valid_from": ["2025-02-01", "2025-03-15", None]})
    out = coerce_datetime_columns(df)
    assert pd.api.types.is_datetime64_any_dtype(out["valid_from"])
    assert out["valid_from"].iloc[0] == pd.Timestamp("2025-02-01")


def test_objets_date_natifs_sont_convertis():
    """Cas PostgreSQL direct : le driver renvoie des `datetime.date`."""
    df = pd.DataFrame(
        {"valid_from": [dt.date(2025, 2, 1), dt.date(2025, 3, 15), None]}
    )
    assert df["valid_from"].dtype == object  # avant conversion
    out = coerce_datetime_columns(df)
    assert pd.api.types.is_datetime64_any_dtype(out["valid_from"])
    assert out["valid_from"].iloc[0] == pd.Timestamp("2025-02-01")


def test_objets_datetime_natifs_sont_convertis():
    df = pd.DataFrame(
        {"event_ts": [dt.datetime(2025, 2, 1, 8, 30), dt.datetime(2025, 2, 1, 9, 0)]}
    )
    out = coerce_datetime_columns(df)
    assert pd.api.types.is_datetime64_any_dtype(out["event_ts"])


def test_cles_numeriques_textuelles_ne_sont_pas_converties():
    """`date_key` ('20250201') ne doit jamais devenir une date : c'est une clé."""
    df = pd.DataFrame({"date_key": ["20250201", "20250202"]})
    out = coerce_datetime_columns(df)
    assert out["date_key"].dtype == object


def test_texte_libre_non_iso_est_preserve():
    df = pd.DataFrame({"categorie": ["Maison & Cuisine", "Beaute & Soins"]})
    out = coerce_datetime_columns(df)
    assert out["categorie"].dtype == object


def test_colonnes_numeriques_non_touchees():
    df = pd.DataFrame({"quantite": [1, 2, 3]})
    out = coerce_datetime_columns(df)
    assert out["quantite"].dtype != object


def test_dataframe_vide_ne_leve_pas():
    out = coerce_datetime_columns(pd.DataFrame())
    assert out.empty


# ---------------------------------------------------------------------------
# Régression du 2026-08-13 : psycopg2 renvoie `decimal.Decimal` pour les
# colonnes `numeric` (prix, coût, montant) — l'arithmétique mêlée à des
# `float` levait `TypeError: unsupported operand type(s) for -`.
# ---------------------------------------------------------------------------
def test_colonnes_decimal_sont_converties_en_float():
    df = pd.DataFrame({"cout_xof": [Decimal("1500.50"), Decimal("2000.00"), None]})
    assert df["cout_xof"].dtype == object
    out = coerce_decimal_columns(df)
    assert out["cout_xof"].dtype == "float64"
    assert out["cout_xof"].iloc[0] == pytest.approx(1500.50)


def test_arithmetique_float_moins_decimal_convertie_fonctionne():
    df = pd.DataFrame({"cout_xof": [Decimal("600.0")]})
    out = coerce_decimal_columns(df)
    resultat = 950.0 - out["cout_xof"].iloc[0]  # levait TypeError avant correction
    assert resultat == pytest.approx(350.0)


def test_decimal_ne_touche_pas_les_colonnes_non_decimal():
    df = pd.DataFrame({"categorie": ["Maison", "Sport"], "quantite": [1, 2]})
    out = coerce_decimal_columns(df)
    assert out["categorie"].dtype == object
    assert out["quantite"].dtype != object


def test_decimal_et_datetime_composables():
    """Les deux coercions doivent pouvoir s'enchaîner sans interférence."""
    df = pd.DataFrame(
        {
            "valid_from": [dt.date(2025, 2, 1)],
            "cout_xof": [Decimal("42.5")],
            "categorie": ["Maison"],
        }
    )
    out = coerce_decimal_columns(coerce_datetime_columns(df))
    assert pd.api.types.is_datetime64_any_dtype(out["valid_from"])
    assert out["cout_xof"].dtype == "float64"
    assert out["categorie"].dtype == object
