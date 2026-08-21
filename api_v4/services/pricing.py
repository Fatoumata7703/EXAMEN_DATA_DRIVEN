"""Service de simulation pricing de l'API produit V4.

Simulation uniquement : aucune ecriture, aucune application automatique du
prix simule. Le modele retenu est la mediane par produit
(`baseline_mediane_produit`), seule reference issue de l'entrainement — aucun
prix optimal n'est calcule automatiquement, le point de depart est toujours
la remise proposee par l'appelant.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from api_v4.registry import REGISTRY
from src.pricing_v4.models import predict as predict_pricing


class UnknownProductError(Exception):
    """Le produit demande n'appartient pas au catalogue pricing connu."""


class PriceBelowCostError(Exception):
    """La remise proposee ferait tomber le prix simule sous le cout produit."""

    def __init__(self, prix_simule: float, cout: float) -> None:
        self.prix_simule = prix_simule
        self.cout = cout
        super().__init__(f"prix simule {prix_simule:.2f} XOF < cout {cout:.2f} XOF")


@dataclass
class PricingOutcome:
    produit_key: str
    categorie: str
    classe_abc: str
    prix_catalogue_xof: float
    cout_xof: float
    remise_proposee_pct: float
    prix_simule_xof: float
    volume_estime_unites_7j: float
    chiffre_affaires_estime_xof: float
    marge_estimee_xof: float
    modele: str
    version: str
    garde_fous: dict


def _predict_one(target: str, produit_key: str) -> float | None:
    model = REGISTRY.pricing_models.get(target)
    if model is None:
        return None
    frame = pd.DataFrame([{"produit_key": produit_key}])
    try:
        value = predict_pricing(model, frame)[0]
        return float(value) if pd.notna(value) else None
    except Exception:  # noqa: BLE001 - un echec de scoring ne doit pas faire tomber l'API
        return None


def simulate(produit_key: str, discount_proposed_pct: float) -> PricingOutcome:
    entry = REGISTRY.pricing_catalog.get(produit_key)
    if entry is None:
        raise UnknownProductError(produit_key)

    prix_catalogue = float(entry["prix_base_xof"])
    cout = float(entry["cout_xof"])
    prix_simule = prix_catalogue * (1.0 - discount_proposed_pct / 100.0)

    if prix_simule < cout:
        raise PriceBelowCostError(prix_simule, cout)

    volume = _predict_one("units_sold_window_7j", produit_key)
    revenue = _predict_one("revenue_window_xof_7j", produit_key)
    margin = _predict_one("margin_window_xof_7j", produit_key)

    volume = volume if volume is not None else 0.0
    revenue = revenue if revenue is not None else volume * prix_simule
    margin = margin if margin is not None else revenue - volume * cout

    version = REGISTRY.model_version("pricing", "units_sold_window_7j")
    modele_entry = REGISTRY.model_entry("pricing", "units_sold_window_7j")
    modele = modele_entry.get("model_name", "baseline_mediane_produit") if modele_entry else "baseline_mediane_produit"

    garde_fous = {
        "prix_sous_cout": False,
        "marge_negative": margin < 0,
    }

    return PricingOutcome(
        produit_key=produit_key, categorie=entry["categorie"], classe_abc=entry["classe_abc"],
        prix_catalogue_xof=prix_catalogue, cout_xof=cout, remise_proposee_pct=discount_proposed_pct,
        prix_simule_xof=round(prix_simule, 2), volume_estime_unites_7j=round(volume, 3),
        chiffre_affaires_estime_xof=round(revenue, 2), marge_estimee_xof=round(margin, 2),
        modele=modele, version=version, garde_fous=garde_fous,
    )
