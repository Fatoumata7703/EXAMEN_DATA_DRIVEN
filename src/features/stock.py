"""Variables dérivées du stock — livraison `fact_stock` du 2026-08-13.

Un seul principe gouverne tout ce module : **`niveau_stock` est un stock de
fin de journée** (confirmé par le dictionnaire et par la reconciliation
stock/ventes, cf. `reports/12_conformite_nouvelle_livraison.md` §7). Le stock
du jour J n'est donc connu qu'*après* les ventes de J : l'utiliser comme
variable explicative de la vente de J serait une fuite. Seul le stock de la
**veille** (``lag=1``) peut être utilisé pour prévoir J.

Constat empirique important, mesuré sur la livraison actuelle et **non
supposé** : le stock ne descend jamais sous 21 unités (le réapprovisionnement
est déclenché le jour même dès que stock − vente ≤ 20) et la corrélation entre
le stock de la veille et la vente du jour est quasi nulle (−0,035). **Aucune
preuve de censure de la demande par rupture n'existe dans cette livraison.**
Les indicateurs ci-dessous sont néanmoins construits correctement — ils
resteront quasi constants tant que cette réalité ne change pas, mais le code
doit fonctionner sans modification si une future livraison contient de vraies
ruptures.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


@dataclass
class StockConfig:
    # Seuil documenté par le data engineer (dictionnaire) : réapprovisionnement
    # automatique quand le stock passe sous 20 unités.
    seuil_rupture: float = 20.0
    # Seuil d'alerte « stock faible », plus large, pour capter la tension
    # d'approvisionnement même en l'absence de rupture effective.
    seuil_stock_faible: float = 50.0
    rolling_windows: tuple[int, ...] = (7, 14, 28)


def build_stock_features(
    stock: pd.DataFrame,
    config: StockConfig | None = None,
    product_col: str = "unique_id",
    date_col: str = "ds",
    level_col: str = "niveau_stock",
) -> pd.DataFrame:
    """Construit les variables stock **utilisables sans fuite** pour prévoir J.

    Entrée : une ligne par (produit, jour), stock de fin de journée.
    Sortie : les mêmes clés, plus les variables ci-dessous — toutes calculées
    à partir du stock décalé d'au moins un jour.

    * ``stock_fin_jour`` : valeur brute, **contemporaine** — conservée pour
      audit et pour le dataset de pricing (qui n'a pas la même contrainte
      temporelle qu'un modèle de prévision), mais **jamais** à utiliser comme
      variable explicative de la vente du même jour.
    * ``stock_disponible_lag1`` : stock de la veille — la seule mesure de
      disponibilité connue avant les ventes du jour J.
    * ``indicateur_rupture_lag1`` : 1 si le stock de la veille est déjà sous
      le seuil documenté (rupture avérée en entrée de journée).
    * ``indicateur_stock_faible_lag1`` : 1 si sous le seuil d'alerte, plus
      permissif.
    * ``jours_depuis_derniere_rupture`` : ancienneté de la dernière rupture
      observée (stock de fin de journée sous le seuil), calculée sur le passé
      uniquement.
    * ``jours_depuis_dernier_reappro`` : ancienneté du dernier réapprovisionnement
      détecté (hausse de stock supérieure à la baisse attendue par les ventes).
    * ``jours_rupture_lag_7/14/28`` : nombre de jours de rupture dans la
      fenêtre glissante *précédente* (n'inclut jamais le jour courant).
    """
    cfg = config or StockConfig()
    df = stock[[product_col, date_col, level_col]].copy()
    df[date_col] = pd.to_datetime(df[date_col])
    df = df.sort_values([product_col, date_col]).reset_index(drop=True)
    df = df.rename(columns={level_col: "stock_fin_jour"})

    grp = df.groupby(product_col)["stock_fin_jour"]
    df["stock_disponible_lag1"] = grp.shift(1)

    df["indicateur_rupture_lag1"] = (
        df["stock_disponible_lag1"] <= cfg.seuil_rupture
    ).astype("Int64")
    df["indicateur_stock_faible_lag1"] = (
        df["stock_disponible_lag1"] <= cfg.seuil_stock_faible
    ).astype("Int64")
    # Non défini pour la toute première observation de chaque série (pas de veille).
    no_lag = df["stock_disponible_lag1"].isna()
    df.loc[no_lag, ["indicateur_rupture_lag1", "indicateur_stock_faible_lag1"]] = pd.NA

    # Rupture détectée sur le stock de FIN de journée passé (jamais le jour courant).
    est_rupture_historique = (df["stock_fin_jour"] <= cfg.seuil_rupture).astype(int)

    def _days_since_true(flags: pd.Series) -> pd.Series:
        """Jours écoulés depuis le dernier True, décalé de 1 (n'inclut pas J)."""
        shifted = flags.shift(1).fillna(0)
        out = np.full(len(shifted), np.nan)
        last_seen = np.nan
        for i, v in enumerate(shifted.to_numpy()):
            if i == 0:
                out[i] = np.nan
            else:
                out[i] = np.nan if np.isnan(last_seen) else out[i - 1]
            if v == 1:
                last_seen = i
                out[i] = 0
            elif not np.isnan(last_seen):
                out[i] = i - last_seen
        return pd.Series(out, index=flags.index)

    df["jours_depuis_derniere_rupture"] = df.groupby(product_col, group_keys=False)[
        "stock_fin_jour"
    ].apply(lambda s: _days_since_true((s <= cfg.seuil_rupture).astype(int)))

    # Réapprovisionnement : toute hausse de stock d'un jour sur l'autre.
    # Détection sur le stock seul (pas sur les ventes) : reste valable même
    # sans connaître la vente du jour.
    df["_est_reappro"] = (df.groupby(product_col)["stock_fin_jour"].diff() > 0).astype(int)
    df["jours_depuis_dernier_reappro"] = df.groupby(product_col, group_keys=False)[
        "_est_reappro"
    ].apply(_days_since_true)
    df = df.drop(columns=["_est_reappro"])

    df["_est_rupture"] = (df["stock_fin_jour"] <= cfg.seuil_rupture).astype(int)
    for window in cfg.rolling_windows:
        # Fenêtre glissante sur le passé strict : décalage de 1 avant le
        # rolling pour que le jour courant n'entre jamais dans son propre compte.
        df[f"jours_rupture_lag_{window}"] = df.groupby(product_col, group_keys=False)[
            "_est_rupture"
        ].apply(lambda s: s.shift(1).rolling(window, min_periods=1).sum())
    df = df.drop(columns=["_est_rupture"])

    return df


def censorship_mask(
    stock_features: pd.DataFrame,
    sales: pd.Series,
    product_col: str = "unique_id",
) -> pd.Series:
    """Masque ``jour_censure_stock`` : jours où le stock de la veille était
    déjà en rupture, donc où un ``y = 0`` pourrait refléter une contrainte
    d'offre plutôt qu'une absence de demande.

    Ne dépend que de ``indicateur_rupture_lag1`` (connu avant les ventes du
    jour) et de la valeur de la cible : un jour n'est marqué censuré que s'il
    est **à la fois** en rupture d'entrée de journée **et** à vente nulle —
    un jour de rupture avec vente positive n'est pas censuré, il montre
    justement qu'un réapprovisionnement en cours de journée a satisfait la
    demande.
    """
    rupture = stock_features["indicateur_rupture_lag1"].fillna(0).astype(int) == 1
    return (rupture & (sales.to_numpy() == 0)).astype(int)
