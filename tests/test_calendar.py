"""Tests des variables calendaires (Sénégal)."""

from __future__ import annotations

import pandas as pd
import pytest

from src.features.calendar import (
    CalendarConfig,
    build_calendar_features,
    future_calendar,
    get_holidays,
    ramadan_periods,
)


@pytest.fixture(scope="module")
def calendar_2024_2025() -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", "2025-12-31", freq="D")
    return build_calendar_features(pd.Series(dates))


def test_senegal_holidays_are_available():
    hol = get_holidays([2024, 2025], country="SN")
    assert not hol.empty
    names = " ".join(hol["_norm"])
    for expected in ("korite", "tabaski", "independance", "magal"):
        assert expected in names


def test_basic_calendar_columns(calendar_2024_2025):
    cal = calendar_2024_2025
    row = cal[cal["ds"] == pd.Timestamp("2024-01-06")].iloc[0]  # samedi
    assert row["jour_semaine"] == 5
    assert row["est_weekend"] == 1
    assert row["mois"] == 1
    assert row["trimestre"] == 1


def test_independence_day_flagged(calendar_2024_2025):
    row = calendar_2024_2025[calendar_2024_2025["ds"] == pd.Timestamp("2024-04-04")].iloc[0]
    assert row["est_ferie"] == 1
    assert row["est_independance"] == 1


def test_korite_and_tabaski_2024(calendar_2024_2025):
    cal = calendar_2024_2025
    korite = cal[cal["ds"] == pd.Timestamp("2024-04-10")].iloc[0]
    tabaski = cal[cal["ds"] == pd.Timestamp("2024-06-17")].iloc[0]
    assert korite["est_korite"] == 1
    assert tabaski["est_tabaski"] == 1
    # Fenêtre d'anticipation d'achat
    assert cal[cal["ds"] == pd.Timestamp("2024-06-14")].iloc[0]["avant_tabaski"] == 1
    assert cal[cal["ds"] == pd.Timestamp("2024-06-18")].iloc[0]["apres_tabaski"] == 1


def test_ramadan_window_precedes_korite(calendar_2024_2025):
    cal = calendar_2024_2025
    # Korité 2024 = 10 avril => Ramadan couvre fin mars / début avril
    assert cal[cal["ds"] == pd.Timestamp("2024-03-25")].iloc[0]["est_ramadan"] == 1
    assert cal[cal["ds"] == pd.Timestamp("2024-04-09")].iloc[0]["est_ramadan"] == 1
    # Le jour de la Korité n'est pas dans le Ramadan
    assert cal[cal["ds"] == pd.Timestamp("2024-04-10")].iloc[0]["est_ramadan"] == 0
    # Fin du Ramadan = dernière semaine
    assert cal[cal["ds"] == pd.Timestamp("2024-04-09")].iloc[0]["fin_ramadan"] == 1


def test_ramadan_periods_do_not_overlap():
    hol = get_holidays(range(2020, 2027), country="SN")
    periods = ramadan_periods(hol)
    assert len(periods) >= 5
    for (s1, e1), (s2, e2) in zip(periods, periods[1:]):
        assert e1 < s2


def test_future_calendar_is_generated_without_history():
    fut = future_calendar(pd.Timestamp("2025-06-30"), horizon=30)
    assert len(fut) == 30
    assert fut["ds"].min() == pd.Timestamp("2025-07-01")
    assert fut["ds"].max() == pd.Timestamp("2025-07-30")
    # Les variables calendaires sont connues à l'avance : aucune valeur manquante
    assert fut.notna().all().all()


def test_unsupported_country_degrades_gracefully():
    cal = build_calendar_features(
        pd.Series(pd.date_range("2024-01-01", periods=10)),
        CalendarConfig(country="ZZ"),
    )
    assert (cal["est_ferie"] == 0).all()
