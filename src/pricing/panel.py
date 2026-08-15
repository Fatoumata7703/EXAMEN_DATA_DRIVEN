"""Panel produit x jour pour l'analyse pricing — une seule construction,
réutilisée par les baselines, les 4 méthodes d'uplift, les tables de
confusion et le simulateur, pour éviter toute divergence entre sections.

Variables clairement distinguées (jamais mélangées) :

* ``prix_catalogue_xof`` — connu à l'avance, fixe (cf. rapport 26 §1).
* ``remise_planifiee_pct`` — remise du calendrier promotionnel, connue à
  l'avance pour une date donnée.
* ``remise_appliquee_pct`` — remise réellement observée / estimée depuis le
  prix payé, disponible seulement a posteriori (jours avec vente).
* ``prix_unitaire_paye_xof`` — observé a posteriori seulement.
* ``cout_unitaire_xof`` — fixe par produit (`dim_produit.cout_xof`).
* ``quantite_vendue`` — cible.
* ``stock_disponible_lag1`` — connu la veille, jamais contemporain (aucune
  fuite : c'est la même colonne, avec la même garantie, que celle utilisée
  côté forecasting).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.config.settings import PROJECT_ROOT


def build_panel() -> pd.DataFrame:
    pricing = pd.read_parquet(PROJECT_ROOT / "data" / "processed" / "table_pricing.parquet")
    pricing["ds"] = pd.to_datetime(pricing["ds"])
    table = pd.read_parquet(PROJECT_ROOT / "data" / "processed" / "table_analytique.parquet")
    table["ds"] = pd.to_datetime(table["ds"])

    stock_cols = [c for c in ("stock_disponible_lag1", "indicateur_rupture_lag1", "indicateur_stock_faible_lag1") if c in table.columns]
    panel = pricing.merge(table[["unique_id", "ds"] + stock_cols], on=["unique_id", "ds"], how="left")

    panel["jour_semaine"] = panel["ds"].dt.dayofweek
    panel["weekend"] = panel["jour_semaine"].isin([5, 6])
    panel["mois"] = panel["ds"].dt.month
    panel["annee_mois"] = panel["ds"].dt.to_period("M").astype(str)
    panel["remise_planifiee_pct"] = panel["remise_planifiee_pct"].fillna(0.0)
    panel["log1p_y"] = np.log1p(panel["quantite_vendue"].to_numpy(dtype="float64"))
    return panel


def observed_discount_grid(panel: pd.DataFrame, exclude_thin: bool = True, min_support: int = 50) -> list[float]:
    """Grille des niveaux de remise réellement observés — jamais extrapolée
    au-delà. `exclude_thin` retire les niveaux à support insuffisant
    (déjà identifié : 40 % avec 11 lignes, cf. rapport 26 §3-4)."""
    promo = panel[panel["en_promotion"] == True]  # noqa: E712
    counts = promo["remise_planifiee_pct"].value_counts()
    if exclude_thin:
        counts = counts[counts >= min_support]
    return sorted(counts.index.tolist())
