"""Construction de la table analytique produit × jour.

Décisions structurantes, toutes traçables dans les rapports d'audit et de
validation :

* **Cible** ``y`` = **quantité vendue observée** par produit et par jour.
  Ce n'est **pas** la demande : sans donnée de stock ni de disponibilité, un
  ``y = 0`` ne peut pas être distingué d'une rupture. Cf. README §Limites.
* **Fenêtre d'activité** (règle A) : borne gauche = ``max(date de début de
  validité du produit, première date disponible dans les données)``, plafonnée
  par la première vente observée ; borne droite = **dernière date globale** du
  jeu de données, identique pour toutes les séries. Hors de cette fenêtre, il
  n'y a pas « vente = 0 » mais **absence d'observation** : aucune ligne n'est
  créée.
* **Prix** : le prix catalogue et le prix attendu (catalogue moins remise
  planifiée) sont connus à l'avance ; le prix réalisé (``ca / y``) est observé
  a posteriori et reste manquant les jours sans vente.
* **Web** : agrégé par produit × jour, accompagné de ``web_data_observed`` qui
  distingue « aucun événement » de « aucune donnée disponible ».

Principe transverse : **aucun repli silencieux**. Toute colonne indispensable
non résolue, toute collision de renommage lève une exception explicite.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


class ColumnCollisionError(ValueError):
    """Deux colonnes sources viseraient le même nom final, ou l'inverse."""


class UnresolvedColumnError(ValueError):
    """Une colonne indispensable n'a pas pu être résolue dans le schéma réel."""


def resolve_attribute_mapping(
    mapping: Mapping[str, str] | Iterable[tuple[str, str]],
    available: Sequence[str],
    required: Sequence[str] | None = None,
) -> dict[str, str]:
    """Valide un plan de renommage ``source -> destination``.

    Garde-fous (à l'origine d'un défaut réel : ``categorie`` avait été renommée
    en ``product_id``, faisant disparaître la catégorie du jeu de données) :

    * une même source ne peut pas viser **deux destinations** ;
    * deux sources ne peuvent pas produire le **même nom final** ;
    * une source déclarée ``required`` mais absente lève une erreur, au lieu
      d'être ignorée en silence.

    Les sources optionnelles absentes du schéma sont simplement écartées.
    """
    pairs = list(mapping.items()) if isinstance(mapping, Mapping) else list(mapping)

    # Une source -> deux destinations
    by_source: dict[str, set[str]] = {}
    for source, dest in pairs:
        if source is None or dest is None:
            continue
        by_source.setdefault(source, set()).add(dest)
    for source, dests in by_source.items():
        if len(dests) > 1:
            raise ColumnCollisionError(
                f"La colonne source '{source}' viserait deux destinations : "
                f"{sorted(dests)}. Corrigez le mapping avant de poursuivre."
            )

    present = {s: next(iter(d)) for s, d in by_source.items() if s in set(available)}

    # Deux sources -> une destination
    by_dest: dict[str, list[str]] = {}
    for source, dest in present.items():
        by_dest.setdefault(dest, []).append(source)
    collisions = {d: s for d, s in by_dest.items() if len(s) > 1}
    if collisions:
        details = "; ".join(f"{sorted(s)} -> '{d}'" for d, s in collisions.items())
        raise ColumnCollisionError(
            f"Plusieurs colonnes sources produiraient le même nom final : {details}."
        )

    missing = [c for c in (required or []) if c not in present]
    if missing:
        raise UnresolvedColumnError(
            f"Colonne(s) indispensable(s) non résolue(s) dans le schéma réel : "
            f"{missing}. Colonnes disponibles : {sorted(available)}."
        )
    return present


@dataclass
class DatasetSpec:
    """Description des colonnes sources nécessaires à la construction."""

    sales_table: str
    product_key: str
    date_key: str
    quantity: str
    amount: str
    promo_key: str | None
    product_dim_key: str
    product_natural_id: str | None
    category: str | None
    brand: str | None
    label: str | None
    catalog_price: str | None
    validity_start: str | None
    web_product_key: str | None = None
    web_date_key: str | None = None
    web_event_type: str | None = None

    def require(self, *fields: str) -> None:
        """Échoue explicitement si un champ indispensable n'est pas renseigné."""
        missing = [f for f in fields if not getattr(self, f, None)]
        if missing:
            raise UnresolvedColumnError(
                f"Champs de spécification non résolus : {missing}. "
                "Renseignez-les dans config/config.yaml (section schema_mapping)."
            )


@dataclass
class BuildReport:
    """Traçabilité de la construction (alimente rapports et artefacts)."""

    n_sales_rows: int = 0
    n_products: int = 0
    n_days: int = 0
    n_observed_points: int = 0
    n_filled_zeros: int = 0
    n_rows_total: int = 0
    date_min: pd.Timestamp | None = None
    date_max: pd.Timestamp | None = None
    zero_share: float = 0.0
    notes: list[str] = field(default_factory=list)
    promo_verification: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_lignes_ventes_source": self.n_sales_rows,
            "n_produits": self.n_products,
            "n_jours": self.n_days,
            "n_points_observes": self.n_observed_points,
            "n_zeros_completes": self.n_filled_zeros,
            "n_lignes_table_analytique": self.n_rows_total,
            "date_min": str(self.date_min.date()) if self.date_min is not None else None,
            "date_max": str(self.date_max.date()) if self.date_max is not None else None,
            "part_jours_a_zero": self.zero_share,
            "verification_calendrier_promo": self.promo_verification,
            "notes": self.notes,
        }


def parse_date_key(series: pd.Series) -> pd.Series:
    """Convertit une clé de date en date réelle.

    Gère les trois formes rencontrées en modèle en étoile : date native,
    entier/texte ``AAAAMMJJ``, ou chaîne ISO.
    """
    if pd.api.types.is_datetime64_any_dtype(series):
        return series.dt.normalize()
    as_text = series.astype("string").str.strip()
    if as_text.str.fullmatch(r"\d{8}").fillna(False).all():
        return pd.to_datetime(as_text, format="%Y%m%d").dt.normalize()
    return pd.to_datetime(series, errors="coerce").dt.normalize()


def aggregate_sales_daily(
    sales: pd.DataFrame, spec: DatasetSpec
) -> tuple[pd.DataFrame, BuildReport]:
    """Agrège les lignes de vente en une série produit × jour."""
    spec.require("product_key", "date_key", "quantity", "amount")
    report = BuildReport(n_sales_rows=len(sales))
    df = sales.copy()
    df["ds"] = parse_date_key(df[spec.date_key])
    invalid = int(df["ds"].isna().sum())
    if invalid:
        report.notes.append(f"{invalid} ligne(s) sans date exploitable, exclues.")
        df = df.dropna(subset=["ds"])

    df[spec.quantity] = pd.to_numeric(df[spec.quantity], errors="coerce")
    df[spec.amount] = pd.to_numeric(df[spec.amount], errors="coerce")

    negatives = int((df[spec.quantity] < 0).sum())
    zeros = int((df[spec.quantity] == 0).sum())
    if negatives or zeros:
        report.notes.append(
            f"Source : {negatives} quantité(s) négative(s) et {zeros} nulle(s), "
            "conservées telles quelles."
        )
    else:
        report.notes.append(
            "Aucune quantité nulle ni négative dans la source, et aucune colonne "
            "de statut : la quantité nette est égale à la quantité brute. "
            "Hypothèse à confirmer côté métier (les annulations et retours sont "
            "peut-être absents de la table de faits)."
        )

    agg = (
        df.groupby([spec.product_key, "ds"], as_index=False)
        .agg(
            y=(spec.quantity, "sum"),
            ca=(spec.amount, "sum"),
            n_transactions=(spec.quantity, "size"),
        )
        .rename(columns={spec.product_key: "unique_id"})
    )
    agg["unique_id"] = agg["unique_id"].astype(str)
    report.n_observed_points = len(agg)
    report.date_min, report.date_max = agg["ds"].min(), agg["ds"].max()
    return agg, report


def build_active_grid(
    daily: pd.DataFrame,
    products: pd.DataFrame,
    spec: DatasetSpec,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
    report: BuildReport,
    require_validity: bool = True,
) -> pd.DataFrame:
    """Grille produit × jour limitée à la fenêtre d'activité (**règle A**).

    * borne gauche = ``max(début de validité, première date des données)``,
      plafonnée par la première vente observée du produit ;
    * borne droite = ``end_date``, identique pour toutes les séries.

    C'est ici que se joue la distinction entre « pas de vente ce jour-là »
    (zéro légitime) et « aucune observation possible » (aucune ligne).

    L'écrêtage à ``start_date`` est essentiel : un début de validité antérieur
    au jeu de données ne permet pas d'affirmer que le produit ne s'est pas
    vendu avant — nous n'en savons simplement rien.
    """
    first_sale = daily.groupby("unique_id")["ds"].min().rename("premiere_vente")
    bounds = first_sale.to_frame()

    has_validity = bool(spec.validity_start) and spec.validity_start in products.columns
    if not has_validity:
        if require_validity:
            raise UnresolvedColumnError(
                "Aucune colonne de début de validité produit n'a été résolue alors "
                "que la politique de complétion 'active_window' l'exige. "
                f"Colonne recherchée : {spec.validity_start!r}. Renseignez "
                "schema_mapping.produit.validity_start dans config/config.yaml, "
                "ou passez target.fill_policy à 'first_sale'."
            )
        bounds["debut"] = bounds["premiere_vente"]
        report.notes.append(
            "Début de validité indisponible : la fenêtre démarre à la première "
            "vente observée de chaque produit."
        )
        return _expand(bounds, end_date)

    validity = (
        products.assign(**{spec.product_dim_key: products[spec.product_dim_key].astype(str)})
        .set_index(spec.product_dim_key)[spec.validity_start]
        .pipe(pd.to_datetime)
        .dt.normalize()
    )
    bounds["debut_validite"] = bounds.index.map(validity)
    n_missing = int(bounds["debut_validite"].isna().sum())
    if n_missing:
        report.notes.append(
            f"{n_missing} produit(s) sans début de validité : repli sur leur "
            "première vente observée."
        )

    # Règle A, en deux temps.
    clipped = bounds["debut_validite"].clip(lower=start_date)
    bounds["debut"] = clipped.fillna(bounds["premiere_vente"])
    # Garde-fou : la fenêtre ne peut jamais commencer après la première vente,
    # sous peine de perdre des ventes réelles.
    bounds["debut"] = bounds[["debut", "premiere_vente"]].min(axis=1)

    n_clipped = int((bounds["debut_validite"] < start_date).sum())
    if n_clipped:
        report.notes.append(
            f"{n_clipped} produit(s) ont un début de validité antérieur au jeu de "
            f"données ({start_date.date()}) : leur fenêtre est écrêtée à cette date, "
            "aucune ligne n'étant fabriquée là où rien n'a été observé."
        )
    return _expand(bounds, end_date)


def _expand(bounds: pd.DataFrame, end_date: pd.Timestamp) -> pd.DataFrame:
    frames = [
        pd.DataFrame({"unique_id": product, "ds": pd.date_range(start, end_date, freq="D")})
        for product, start in bounds["debut"].items()
    ]
    grid = pd.concat(frames, ignore_index=True)
    grid["unique_id"] = grid["unique_id"].astype(str)
    return grid


def aggregate_web_daily(
    web: pd.DataFrame, spec: DatasetSpec
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compte les événements web par produit × jour, et décrit leur couverture.

    Renvoie ``(compteurs, couverture)`` où ``couverture`` donne, par produit, la
    première et la dernière date où des événements web ont été collectés. Cette
    fenêtre permet de distinguer **zéro événement** (dans la fenêtre) de
    **aucune donnée** (hors fenêtre, ou produit non suivi).
    """
    empty = pd.DataFrame(columns=["unique_id", "ds"]), pd.DataFrame(
        columns=["unique_id", "web_debut", "web_fin"]
    )
    if web is None or web.empty or not spec.web_event_type:
        return empty
    spec.require("web_product_key", "web_date_key", "web_event_type")

    df = web.copy()
    df["ds"] = parse_date_key(df[spec.web_date_key])
    df = df.dropna(subset=["ds"])
    df[spec.web_product_key] = df[spec.web_product_key].astype(str)

    pivot = (
        df.pivot_table(
            index=[spec.web_product_key, "ds"],
            columns=spec.web_event_type,
            aggfunc="size",
            fill_value=0,
        )
        .reset_index()
        .rename(columns={spec.web_product_key: "unique_id"})
    )
    pivot.columns.name = None
    event_cols = [c for c in pivot.columns if c not in ("unique_id", "ds")]
    pivot = pivot.rename(columns={c: f"web_{c}" for c in event_cols})
    pivot["web_total"] = pivot[[f"web_{c}" for c in event_cols]].sum(axis=1)

    coverage = (
        df.groupby(spec.web_product_key)["ds"]
        .agg(web_debut="min", web_fin="max")
        .reset_index()
        .rename(columns={spec.web_product_key: "unique_id"})
    )
    return pivot, coverage


def build_analytical_table(
    sales: pd.DataFrame,
    products: pd.DataFrame,
    spec: DatasetSpec,
    promo_calendar: pd.DataFrame | None = None,
    web: pd.DataFrame | None = None,
    require_validity: bool = True,
) -> tuple[pd.DataFrame, BuildReport]:
    """Assemble la table analytique finale."""
    daily, report = aggregate_sales_daily(sales, spec)
    start_date, end_date = report.date_min, report.date_max

    grid = build_active_grid(
        daily, products, spec, start_date, end_date, report, require_validity
    )
    table = grid.merge(daily, on=["unique_id", "ds"], how="left")
    # Seuls la cible et les compteurs de vente sont complétés par zéro.
    table["y"] = table["y"].fillna(0.0)
    table["ca"] = table["ca"].fillna(0.0)
    table["n_transactions"] = table["n_transactions"].fillna(0).astype(int)

    report.n_rows_total = len(table)
    report.n_filled_zeros = report.n_rows_total - report.n_observed_points
    report.n_products = int(table["unique_id"].nunique())
    report.n_days = int(table["ds"].nunique())
    report.zero_share = float((table["y"] == 0).mean())

    # --- Attributs produit (statiques, connus à l'avance) -----------------
    attr_pairs = [
        (spec.product_dim_key, "unique_id"),
        (spec.product_natural_id, "product_id"),
        (spec.category, "categorie"),
        (spec.brand, "marque"),
        (spec.label, "libelle"),
        (spec.catalog_price, "prix_catalogue"),
        (spec.validity_start, "date_debut_validite"),
    ]
    usable = resolve_attribute_mapping(
        attr_pairs,
        available=list(products.columns),
        required=[spec.product_dim_key],
    )
    dim = products[list(usable)].rename(columns=usable)
    dim["unique_id"] = dim["unique_id"].astype(str)
    if dim["unique_id"].duplicated().any():
        raise ColumnCollisionError(
            f"La clé produit '{spec.product_dim_key}' n'est pas unique dans la "
            "dimension : la jointure dupliquerait des lignes de vente."
        )
    table = table.merge(dim, on="unique_id", how="left")

    if "date_debut_validite" in table.columns:
        table["date_debut_validite"] = pd.to_datetime(
            table["date_debut_validite"]
        ).dt.normalize()
        # Ancienneté depuis le début de validité. Écrêtée à 0 : pour les produits
        # dont la validité précède le jeu de données, l'âge réel est inconnu.
        table["age_produit_jours"] = (
            (table["ds"] - table["date_debut_validite"]).dt.days.clip(lower=0)
        )

    # --- Prix : catalogue (a priori) vs réalisé (a posteriori) ------------
    if "prix_catalogue" in table.columns:
        table["prix_catalogue"] = pd.to_numeric(table["prix_catalogue"], errors="coerce")
    table["prix_realise"] = np.where(
        table["y"] > 0, table["ca"] / table["y"].replace(0, np.nan), np.nan
    )

    # --- Promotions (calendrier : défini aussi les jours sans vente) ------
    if promo_calendar is not None and not promo_calendar.empty:
        promo = promo_calendar.copy()
        promo["unique_id"] = promo["unique_id"].astype(str)
        table = table.merge(promo, on=["unique_id", "ds"], how="left")
        table["en_promotion"] = table["en_promotion"].fillna(0).astype(int)
        table["remise_pct"] = table["remise_pct"].fillna(0.0)
        table["n_promotions"] = table["n_promotions"].fillna(0).astype(int)
        table["portee_promo"] = table["portee_promo"].fillna("aucune")
    else:
        raise UnresolvedColumnError(
            "Aucun calendrier promotionnel n'a pu être construit. La promotion "
            "étant une variable exogène future essentielle, la construction "
            "s'arrête plutôt que de produire une table sans elle."
        )

    if "prix_catalogue" in table.columns:
        table["prix_attendu"] = table["prix_catalogue"] * (1 - table["remise_pct"] / 100.0)

    # --- Événements web + indicateur de disponibilité ---------------------
    web_counts, coverage = aggregate_web_daily(web, spec) if web is not None else (
        pd.DataFrame(),
        pd.DataFrame(),
    )
    if not web_counts.empty:
        table = table.merge(web_counts, on=["unique_id", "ds"], how="left")
        table = table.merge(coverage, on="unique_id", how="left")
        # Le suivi web est-il actif pour ce produit ce jour-là ?
        table["web_data_observed"] = (
            table["web_debut"].notna()
            & (table["ds"] >= table["web_debut"])
            & (table["ds"] <= table["web_fin"])
        ).astype(int)
        web_cols = [c for c in table.columns if c.startswith("web_") and c not in
                    ("web_debut", "web_fin", "web_data_observed")]
        observed = table["web_data_observed"] == 1
        # Dans la fenêtre de suivi : absence de ligne = zéro événement.
        table.loc[observed, web_cols] = table.loc[observed, web_cols].fillna(0)
        # Hors fenêtre : donnée absente, surtout pas zéro.
        table.loc[~observed, web_cols] = np.nan
        table = table.drop(columns=["web_debut", "web_fin"])
        report.notes.append(
            f"Événements web agrégés ({web_cols}) avec l'indicateur "
            "`web_data_observed` : 1 = suivi actif (un 0 signifie réellement "
            "aucun événement), 0 = aucune donnée disponible (compteurs à NaN). "
            "Ces colonnes sont contemporaines de la vente : elles ne peuvent "
            "servir de variables explicatives qu'après décalage."
        )

    table = table.sort_values(["unique_id", "ds"]).reset_index(drop=True)
    return table, report
