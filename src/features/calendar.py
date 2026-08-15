"""Variables calendaires — **connues à l'avance**, donc utilisables sans décalage.

Ce sont les seules variables exogènes que l'on peut renseigner pour des dates
futures sans risque de fuite : le calendrier est déterministe.

Contexte sénégalais : la librairie ``holidays`` couvre le Sénégal (code ``SN``),
Korité (Aïd el-Fitr), Tabaski (Aïd el-Adha), Tamxarit, Maouloud, Grand Magal de
Touba, plus les fêtes civiles et chrétiennes. Le Ramadan n'y figure pas comme
jour férié : sa fenêtre est reconstruite à partir de la date de Korité
(Korité marque la fin du Ramadan).

Attention : certaines dates islamiques sont marquées « estimé » par la
librairie (elles dépendent de l'observation lunaire). Cette incertitude est
signalée par la colonne ``fete_estimee``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable

import numpy as np
import pandas as pd

from src.utils.logging_utils import get_logger

logger = get_logger(__name__)

RAMADAN_LENGTH_DAYS = 30  # 29 ou 30 jours ; on retient la borne haute (prudent)

# Fêtes à effet commercial marqué : on crée des fenêtres « avant / après »
MAJOR_EVENTS = {
    "korite": ["korité", "korite"],
    "tabaski": ["tabaski"],
    "magal": ["magal"],
    "maouloud": ["maouloud"],
    "tamxarit": ["tamxarit"],
    "noel": ["noël", "noel"],
    "nouvel_an": ["jour de l'an"],
    "independance": ["indépendance", "independance"],
}


@dataclass
class CalendarConfig:
    country: str = "SN"
    pre_event_days: int = 7   # fenêtre d'anticipation d'achat avant une fête
    post_event_days: int = 3  # creux post-fête
    ramadan_window: bool = True


def _normalize(text: str) -> str:
    import unicodedata

    t = unicodedata.normalize("NFKD", str(text)).lower()
    return "".join(c for c in t if not unicodedata.combining(c))


def get_holidays(years: Iterable[int], country: str = "SN") -> pd.DataFrame:
    """Table des jours fériés du pays, avec indicateur d'estimation."""
    import holidays as holidays_lib

    years = sorted(set(int(y) for y in years))
    try:
        hol = holidays_lib.country_holidays(country, years=years)
    except NotImplementedError:
        logger.warning(
            "Pays '%s' non supporté par la librairie holidays : "
            "aucun jour férié ne sera généré.",
            country,
        )
        return pd.DataFrame(columns=["ds", "nom_ferie", "fete_estimee"])

    rows = []
    for day, name in sorted(hol.items()):
        norm = _normalize(name)
        rows.append(
            {
                "ds": pd.Timestamp(day),
                "nom_ferie": name,
                "fete_estimee": "estim" in norm,
                "_norm": norm,
            }
        )
    return pd.DataFrame(rows)


def ramadan_periods(holidays_df: pd.DataFrame, length_days: int = RAMADAN_LENGTH_DAYS) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Fenêtres de Ramadan déduites des dates de Korité (fin du Ramadan).

    Hypothèse explicite et documentée : Ramadan = [Korité - length_days, Korité - 1].
    """
    if holidays_df.empty:
        return []
    korite = holidays_df[holidays_df["_norm"].str.contains("korite", na=False)]
    periods: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    for day in sorted(korite["ds"].dt.normalize().unique()):
        end = pd.Timestamp(day) - timedelta(days=1)
        start = end - timedelta(days=length_days - 1)
        # Korité peut apparaître 2 jours de suite (jour observé) : on déduplique
        if periods and abs((periods[-1][1] - end).days) <= 2:
            continue
        periods.append((start, end))
    return periods


def build_calendar_features(
    dates: pd.Series | pd.DatetimeIndex,
    config: CalendarConfig | None = None,
) -> pd.DataFrame:
    """Construit toutes les variables calendaires pour une série de dates.

    Renvoie un DataFrame indexé sur ``ds`` (dates uniques normalisées).
    """
    cfg = config or CalendarConfig()
    ds = pd.to_datetime(pd.Series(dates)).dt.normalize().dropna()
    if ds.empty:
        return pd.DataFrame()
    unique = pd.DatetimeIndex(sorted(ds.unique()))
    out = pd.DataFrame({"ds": unique})

    # --- Composantes calendaires de base ---------------------------------
    out["jour_semaine"] = out["ds"].dt.dayofweek          # 0 = lundi
    out["jour_mois"] = out["ds"].dt.day
    out["jour_annee"] = out["ds"].dt.dayofyear
    out["semaine"] = out["ds"].dt.isocalendar().week.astype(int)
    out["mois"] = out["ds"].dt.month
    out["trimestre"] = out["ds"].dt.quarter
    out["annee"] = out["ds"].dt.year
    out["est_weekend"] = (out["jour_semaine"] >= 5).astype(int)
    out["est_samedi"] = (out["jour_semaine"] == 5).astype(int)
    out["est_dimanche"] = (out["jour_semaine"] == 6).astype(int)
    out["debut_mois"] = out["ds"].dt.is_month_start.astype(int)
    out["fin_mois"] = out["ds"].dt.is_month_end.astype(int)
    out["debut_trimestre"] = out["ds"].dt.is_quarter_start.astype(int)
    out["fin_trimestre"] = out["ds"].dt.is_quarter_end.astype(int)
    # Les 5 premiers / 5 derniers jours du mois (effet paie)
    days_in_month = out["ds"].dt.days_in_month
    out["debut_mois_5j"] = (out["jour_mois"] <= 5).astype(int)
    out["fin_mois_5j"] = (out["jour_mois"] > days_in_month - 5).astype(int)

    # Encodages cycliques (utiles aux modèles à base d'arbres pour la continuité)
    out["sin_jour_semaine"] = np.sin(2 * np.pi * out["jour_semaine"] / 7)
    out["cos_jour_semaine"] = np.cos(2 * np.pi * out["jour_semaine"] / 7)
    out["sin_jour_annee"] = np.sin(2 * np.pi * out["jour_annee"] / 365.25)
    out["cos_jour_annee"] = np.cos(2 * np.pi * out["jour_annee"] / 365.25)

    # --- Jours fériés -----------------------------------------------------
    years = range(int(out["annee"].min()) - 1, int(out["annee"].max()) + 2)
    hol = get_holidays(years, country=cfg.country)
    if hol.empty:
        out["est_ferie"] = 0
        out["ferie_estime"] = 0
        out["nom_ferie"] = ""
        out["jours_depuis_ferie"] = 999
        out["jours_avant_ferie"] = 999
        out["fin_ramadan"] = 0
        for event in MAJOR_EVENTS:
            out[f"est_{event}"] = 0
            out[f"avant_{event}"] = 0
            out[f"apres_{event}"] = 0
        out["est_ramadan"] = 0
        out["jour_ramadan"] = 0
        return out

    # Deux fêtes peuvent tomber le même jour : on déduplique avant l'indexation.
    hol_map = hol.drop_duplicates(subset="ds", keep="first").set_index("ds")
    out["est_ferie"] = out["ds"].isin(hol_map.index).astype(int)
    out["ferie_estime"] = out["ds"].map(hol_map["fete_estimee"]).eq(True).astype(int)
    out["nom_ferie"] = out["ds"].map(hol_map["nom_ferie"]).fillna("")

    # Distance au férié le plus proche (avant / après)
    holiday_days = np.array(sorted(hol_map.index.values), dtype="datetime64[D]")
    target_days = out["ds"].to_numpy(dtype="datetime64[D]")
    diffs = (target_days[:, None] - holiday_days[None, :]).astype(int)
    out["jours_depuis_ferie"] = np.where(
        (diffs >= 0).any(axis=1), np.where(diffs >= 0, diffs, 10_000).min(axis=1), 999
    )
    out["jours_avant_ferie"] = np.where(
        (diffs <= 0).any(axis=1), np.where(diffs <= 0, -diffs, 10_000).min(axis=1), 999
    )

    # --- Grandes fêtes : fenêtres avant / après ---------------------------
    for event, patterns in MAJOR_EVENTS.items():
        mask = hol["_norm"].apply(lambda n: any(_normalize(p) in n for p in patterns))
        event_days = pd.DatetimeIndex(sorted(hol.loc[mask, "ds"].unique()))
        out[f"est_{event}"] = out["ds"].isin(event_days).astype(int)
        if len(event_days) == 0:
            out[f"avant_{event}"] = 0
            out[f"apres_{event}"] = 0
            continue
        ev = event_days.to_numpy(dtype="datetime64[D]")
        delta = (target_days[:, None] - ev[None, :]).astype(int)
        # avant_ : 1 dans les N jours qui précèdent la fête
        out[f"avant_{event}"] = (
            ((delta < 0) & (delta >= -cfg.pre_event_days)).any(axis=1).astype(int)
        )
        out[f"apres_{event}"] = (
            ((delta > 0) & (delta <= cfg.post_event_days)).any(axis=1).astype(int)
        )

    # --- Ramadan ----------------------------------------------------------
    out["est_ramadan"] = 0
    out["jour_ramadan"] = 0
    if cfg.ramadan_window:
        for start, end in ramadan_periods(hol):
            mask = (out["ds"] >= start) & (out["ds"] <= end)
            out.loc[mask, "est_ramadan"] = 1
            out.loc[mask, "jour_ramadan"] = (out.loc[mask, "ds"] - start).dt.days + 1
        # Dernière semaine du Ramadan : pic d'achats avant la Korité
        out["fin_ramadan"] = (
            (out["est_ramadan"] == 1) & (out["jour_ramadan"] >= RAMADAN_LENGTH_DAYS - 6)
        ).astype(int)

    return out


def future_calendar(last_date: pd.Timestamp, horizon: int, freq: str = "D", config: CalendarConfig | None = None) -> pd.DataFrame:
    """Calendrier des ``horizon`` pas futurs — utilisable en prédiction."""
    future_dates = pd.date_range(
        start=pd.Timestamp(last_date) + pd.tseries.frequencies.to_offset(freq),
        periods=horizon,
        freq=freq,
    )
    return build_calendar_features(pd.Series(future_dates), config)


CALENDAR_FEATURE_COLUMNS: list[str] = [
    "jour_semaine",
    "jour_mois",
    "jour_annee",
    "semaine",
    "mois",
    "trimestre",
    "est_weekend",
    "est_samedi",
    "est_dimanche",
    "debut_mois",
    "fin_mois",
    "debut_trimestre",
    "fin_trimestre",
    "debut_mois_5j",
    "fin_mois_5j",
    "sin_jour_semaine",
    "cos_jour_semaine",
    "sin_jour_annee",
    "cos_jour_annee",
    "est_ferie",
    "jours_depuis_ferie",
    "jours_avant_ferie",
    "est_ramadan",
    "jour_ramadan",
    "fin_ramadan",
] + [
    f"{prefix}_{event}"
    for event in MAJOR_EVENTS
    for prefix in ("est", "avant", "apres")
]
