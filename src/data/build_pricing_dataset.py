"""Construction du dataset pricing — grain produit × jour.

Distinction stricte entre les grandeurs, jamais mélangées (cf.
`reports/07_reprise_chaine_data.md` §8) :

* **prix catalogue** (connu à l'avance) vs **prix payé** (observé a posteriori) ;
* **remise planifiée** (calendrier `dim_promotion`) vs **remise appliquée**
  (déduite du prix réellement payé) ;
* **chiffre d'affaires** vs **coût** vs **marge**.

Garde-fous imposés par le diagnostic de faisabilité (`reports/11_verdict_faisabilite.md`) :
aucune élasticité causale n'est calculée ici — seulement les grandeurs
descriptives et les variables nécessaires à un simulateur de remise sous
contrainte de marge. Le prix catalogue ne variant pour aucun produit, aucune
variable de « prix optimal » n'est produite.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


@dataclass
class PricingReport:
    n_rows: int = 0
    n_products: int = 0
    marge_totale_xof: float = 0.0
    n_marge_negative: int = 0
    notes: list[str] | None = None

    def to_dict(self) -> dict:
        return {
            "n_lignes": self.n_rows,
            "n_produits": self.n_products,
            "marge_totale_xof": self.marge_totale_xof,
            "n_lignes_marge_negative": self.n_marge_negative,
            "notes": self.notes or [],
        }


def build_pricing_dataset(
    table_analytique: pd.DataFrame,
    cout_par_produit: pd.Series | None = None,
) -> tuple[pd.DataFrame, PricingReport]:
    """Dérive le dataset pricing depuis la table analytique déjà construite.

    Toutes les colonnes nécessaires (`ca`, `prix_catalogue`, `prix_realise`,
    `remise_pct`, `en_promotion`) existent déjà dans la table analytique.
    ``cout_par_produit`` : série indexée par ``unique_id`` -> coût unitaire
    (absent de la table analytique, à fournir depuis `dim_produit`).
    """
    df = table_analytique.copy()
    notes: list[str] = []

    out = pd.DataFrame(
        {
            "unique_id": df["unique_id"],
            "ds": df["ds"],
            "categorie": df["categorie"],
            "marque": df["marque"],
            "quantite_vendue": df["y"],
            "chiffre_affaires_net_xof": df["ca"],
            "prix_catalogue_xof": df["prix_catalogue"],
            # Prix réellement payé : NaN les jours sans vente (non observable).
            "prix_unitaire_paye_xof": df["prix_realise"],
            "remise_planifiee_pct": df["remise_pct"],
            "en_promotion": df["en_promotion"],
            "n_promotions_concurrentes": df["n_promotions"],
        }
    )

    # Remise réellement appliquée : déduite du prix payé, uniquement définie
    # les jours avec vente (le prix payé n'existe pas sinon).
    out["remise_appliquee_pct"] = 100 * (
        1 - out["prix_unitaire_paye_xof"] / out["prix_catalogue_xof"]
    )

    if cout_par_produit is None:
        notes.append("Coût unitaire non fourni : marge non calculée.")
        report = PricingReport(n_rows=len(out), n_products=out["unique_id"].nunique(), notes=notes)
        return out, report

    out["cout_unitaire_xof"] = out["unique_id"].map(cout_par_produit)
    out["marge_unitaire_xof"] = out["prix_unitaire_paye_xof"] - out["cout_unitaire_xof"]
    out["marge_totale_xof"] = out["chiffre_affaires_net_xof"] - (
        out["cout_unitaire_xof"] * out["quantite_vendue"]
    )
    out["taux_marge"] = out["marge_unitaire_xof"] / out["prix_unitaire_paye_xof"]

    n_neg = int((out["marge_unitaire_xof"] < 0).sum())
    notes.append(
        f"{n_neg} ligne(s) à marge unitaire négative ({n_neg/max((out['quantite_vendue']>0).sum(),1):.2%} "
        "des jours avec vente) — arithmétiquement attendu quand la remise appliquée "
        "dépasse la marge catalogue brute, pas une anomalie de données."
    )

    report = PricingReport(
        n_rows=len(out),
        n_products=out["unique_id"].nunique(),
        marge_totale_xof=float(out["marge_totale_xof"].sum(skipna=True)),
        n_marge_negative=n_neg,
        notes=notes,
    )
    return out, report
