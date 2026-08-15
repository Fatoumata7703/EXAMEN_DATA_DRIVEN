"""Reconstruction du calendrier promotionnel produit × jour.

Pourquoi ne pas se contenter de la clé de promotion portée par la ligne de vente ?

1. **Les jours sans vente n'ont pas de ligne** : l'information « ce produit était
   en promotion ce jour-là » disparaîtrait précisément là où elle est la plus
   informative (une promo sans vente est un signal, pas une absence de signal).
2. **On ne peut pas prévoir avec une variable qui n'existe qu'a posteriori** :
   la clé de promotion d'une vente future est inconnue. En revanche, une
   promotion *planifiée* a des dates de début et de fin connues à l'avance,
   ce qui en fait une variable exogène future légitime.

Le calendrier est donc dérivé de la dimension promotion (portée + cible +
fenêtre de dates), puis **vérifié** contre les promotions effectivement
observées sur les ventes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


def resolve_scope_attributes(
    promotions: pd.DataFrame,
    products: pd.DataFrame,
    scope_col: str,
    target_col: str,
    unique_scopes: set[str] | None = None,
    min_overlap: float = 0.5,
) -> dict[str, str]:
    """Associe chaque portée de promotion à l'attribut produit qu'elle cible.

    **Chaque portée est résolue avec ses seules cibles.** Mélanger les cibles de
    toutes les portées est une erreur qui s'est réellement produite ici : les
    cibles de portée `category` sont des noms de catégories et couvrent 100 %
    des valeurs de ``dim_produit.categorie``, si bien que la catégorie était
    retenue comme identifiant produit — faisant disparaître la vraie catégorie
    du jeu de données.

    ``unique_scopes`` liste les portées qui désignent un produit individuel :
    pour celles-ci, l'attribut retenu doit être **unique** dans la dimension.
    Par défaut, la portée « produit » est déduite du nom.
    """
    if unique_scopes is None:
        unique_scopes = {
            s
            for s in promotions[scope_col].dropna().unique()
            if str(s).lower() in {"product", "produit", "sku", "article"}
        }

    mapping: dict[str, str] = {}
    for scope in promotions[scope_col].dropna().unique():
        targets = set(promotions.loc[promotions[scope_col] == scope, target_col].dropna().astype(str))
        if not targets:
            continue
        best, best_rate = None, 0.0
        for col in products.columns:
            values = products[col].dropna().astype(str)
            if values.empty:
                continue
            # Une portée « produit » exige un identifiant : une colonne dont
            # les valeurs se répètent ne peut pas désigner un produit.
            if scope in unique_scopes and not values.is_unique:
                continue
            rate = len(targets & set(values)) / len(targets)
            if rate > best_rate:
                best, best_rate = col, rate
        if best and best_rate >= min_overlap:
            mapping[scope] = best
            logger.info(
                "Portée promo '%s' -> attribut produit '%s' (recouvrement %.0f%%)",
                scope,
                best,
                100 * best_rate,
            )
        else:
            logger.warning(
                "Portée promo '%s' non résolue : aucun attribut produit ne couvre "
                "ses cibles (meilleur recouvrement %.0f%%). Les promotions de cette "
                "portée seront absentes du calendrier.",
                scope,
                100 * best_rate,
            )
    return mapping


@dataclass
class PromotionSchema:
    """Colonnes de la dimension promotion et leur rôle."""

    key: str
    scope: str
    target: str
    start: str
    end: str
    discount: str
    # Valeurs de `scope` et l'attribut produit auquel la cible se rapporte.
    scope_to_product_attribute: dict[str, str]


def build_promo_calendar(
    promotions: pd.DataFrame,
    products: pd.DataFrame,
    schema: PromotionSchema,
    product_id_col: str,
    calendar_dates: pd.DatetimeIndex | None = None,
) -> pd.DataFrame:
    """Déplie les promotions en une grille produit × jour.

    Renvoie une ligne par (produit, jour, promotion applicable). Plusieurs
    promotions peuvent se recouvrir : l'agrégation est faite ensuite par
    :func:`aggregate_promo_calendar`.
    """
    rows: list[pd.DataFrame] = []
    for scope_value, attribute in schema.scope_to_product_attribute.items():
        subset = promotions[promotions[schema.scope] == scope_value]
        if subset.empty:
            continue
        if attribute not in products.columns:
            logger.warning(
                "Portée '%s' ignorée : attribut produit '%s' absent de la dimension.",
                scope_value,
                attribute,
            )
            continue
        # Produits concernés par chaque promotion de cette portée
        link = subset.merge(
            products[[product_id_col, attribute]],
            left_on=schema.target,
            right_on=attribute,
            how="inner",
        )
        if link.empty:
            logger.warning(
                "Portée '%s' : aucune cible ne correspond à `%s`.", scope_value, attribute
            )
            continue
        expanded = link.assign(
            ds=[
                pd.date_range(start, end, freq="D")
                for start, end in zip(link[schema.start], link[schema.end])
            ]
        ).explode("ds")
        rows.append(
            expanded[[product_id_col, "ds", schema.key, schema.discount]].assign(
                portee=scope_value
            )
        )

    if not rows:
        return pd.DataFrame(columns=[product_id_col, "ds", schema.key, schema.discount, "portee"])

    calendar = pd.concat(rows, ignore_index=True)
    calendar["ds"] = pd.to_datetime(calendar["ds"]).dt.normalize()
    if calendar_dates is not None:
        calendar = calendar[calendar["ds"].isin(calendar_dates)]
    return calendar


def aggregate_promo_calendar(
    calendar: pd.DataFrame,
    schema: PromotionSchema,
    product_id_col: str,
) -> pd.DataFrame:
    """Agrège les promotions concurrentes en une ligne par produit × jour.

    Règle retenue, explicite et configurable : lorsqu'un produit est couvert par
    plusieurs promotions le même jour, **la remise la plus forte l'emporte**
    (hypothèse commerciale usuelle : le client bénéficie de la meilleure offre).
    Le nombre de promotions concurrentes est conservé comme variable.
    """
    if calendar.empty:
        return pd.DataFrame(
            columns=[product_id_col, "ds", "en_promotion", "remise_pct", "n_promotions", "portee_promo"]
        )
    ordered = calendar.sort_values(schema.discount, ascending=False)
    best = ordered.drop_duplicates(subset=[product_id_col, "ds"], keep="first")
    counts = (
        calendar.groupby([product_id_col, "ds"]).size().rename("n_promotions").reset_index()
    )
    out = best.merge(counts, on=[product_id_col, "ds"], how="left")
    out = out.rename(columns={schema.discount: "remise_pct", "portee": "portee_promo"})
    out["en_promotion"] = 1
    return out[[product_id_col, "ds", "en_promotion", "remise_pct", "n_promotions", "portee_promo"]]


def verify_promo_calendar(
    sales: pd.DataFrame,
    promo_calendar: pd.DataFrame,
    product_col: str,
    date_col: str,
    sale_promo_key: str,
) -> dict[str, Any]:
    """Confronte le calendrier reconstruit aux promotions réellement observées.

    Deux taux comptent :

    * **rappel** : part des ventes marquées en promotion que le calendrier
      couvre bien (un rappel faible signifie que la reconstruction rate des
      promotions réelles) ;
    * **précision apparente** : part des couples produit×jour marqués en
      promotion par le calendrier qui portent effectivement une vente promue.
      Elle est structurellement < 100 % puisqu'une promotion peut couvrir un
      jour sans vente, ou une vente au prix plein.
    """
    sold = sales[[product_col, date_col, sale_promo_key]].copy()
    sold["_promue"] = sold[sale_promo_key].notna()
    merged = sold.merge(
        promo_calendar[[product_col, "ds", "en_promotion"]],
        left_on=[product_col, date_col],
        right_on=[product_col, "ds"],
        how="left",
    )
    merged["en_promotion"] = merged["en_promotion"].fillna(0).astype(int)

    promoted = merged[merged["_promue"]]
    recall = float((promoted["en_promotion"] == 1).mean()) if len(promoted) else float("nan")
    covered = merged[merged["en_promotion"] == 1]
    precision = float(covered["_promue"].mean()) if len(covered) else float("nan")
    return {
        "n_ventes_promues": int(len(promoted)),
        "rappel_calendrier": recall,
        "n_ventes_couvertes_par_calendrier": int(len(covered)),
        "precision_apparente": precision,
    }
