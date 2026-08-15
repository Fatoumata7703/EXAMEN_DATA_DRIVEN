"""Normalisation des types après lecture.

Deux backends, deux représentations différentes des dates et des nombres, ni
l'une ni l'autre exploitable telle quelle par pandas :

* **API REST** (PostgREST) : transport JSON — dates en chaînes ISO, nombres
  déjà en `float`/`int` natifs (JSON n'a pas de type décimal) ;
* **PostgreSQL direct** (psycopg2) : le driver renvoie des objets Python
  natifs ``datetime.date``/``datetime.datetime`` pour les colonnes date, et
  ``decimal.Decimal`` pour les colonnes ``numeric`` — que
  ``pd.DataFrame(rows, ...)`` place en colonnes ``object`` sans les convertir.

Sans reconversion, une colonne `date` serait confondue avec du texte libre, et
une colonne `numeric` (prix, coût, montant) ferait échouer toute arithmétique
mêlée à des `float` (``TypeError: unsupported operand type(s) for -: 'float'
and 'decimal.Decimal'``) — ou pire, échouerait silencieusement selon l'ordre
des opérandes.
"""

from __future__ import annotations

import datetime as _dt
import decimal
import re

import pandas as pd

from src.utils.logging_utils import get_logger

logger = get_logger(__name__)

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2})?)?")


def coerce_decimal_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Convertit les colonnes ``decimal.Decimal`` (psycopg2/numeric) en `float64`.

    Conservateur comme `coerce_datetime_columns` : seules les colonnes ``object``
    dont l'échantillon non nul est entièrement composé de `Decimal` sont
    converties.
    """
    if df.empty:
        return df
    out = df
    for col in df.columns:
        if df[col].dtype != object:
            continue
        sample = df[col].dropna().head(200)
        if sample.empty or not all(isinstance(v, decimal.Decimal) for v in sample):
            continue
        if out is df:
            out = df.copy()
        out[col] = df[col].astype(float)
        logger.debug("Colonne %s convertie de Decimal vers float64.", col)
    return out


def coerce_datetime_columns(df: pd.DataFrame, sample_size: int = 200) -> pd.DataFrame:
    """Convertit en datetime les colonnes date, quelle que soit leur origine.

    Conservateur : une colonne n'est convertie que si **toutes** les valeurs
    non nulles d'un échantillon sont des dates (chaînes ISO ou objets natifs
    ``date``/``datetime``), et si la conversion réussit sur la quasi-totalité
    des lignes. Les colonnes numériques (clés de dimension comme
    ``date_key``) ne sont jamais touchées.
    """
    if df.empty:
        return df
    out = df
    for col in df.columns:
        if df[col].dtype != object:
            continue
        sample = df[col].dropna().head(sample_size)
        if sample.empty:
            continue

        if all(isinstance(v, str) for v in sample):
            if not all(_ISO_DATE.match(v) for v in sample):
                continue
            converted = pd.to_datetime(df[col], errors="coerce", format="ISO8601")
        elif all(isinstance(v, (_dt.date, _dt.datetime)) for v in sample):
            converted = pd.to_datetime(df[col], errors="coerce")
        else:
            continue

        if converted.notna().sum() >= 0.99 * df[col].notna().sum():
            if out is df:
                out = df.copy()
            out[col] = converted
            logger.debug("Colonne %s convertie en datetime.", col)
    return out
