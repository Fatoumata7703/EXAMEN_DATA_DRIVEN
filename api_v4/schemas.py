"""Schemas de requete et de reponse de l'API produit V4."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator

from api_v4.config import MAX_CANDIDATE_PRODUCTS


class RecommendationRequest(BaseModel):
    """Contexte fourni par l'appelant : le service ne lit aucune base client
    en direct, il applique le modele au contexte transmis. Les champs
    client sont optionnels et valent par defaut la convention « visiteur
    anonyme, sans historique » utilisee a l'entrainement.
    """

    client_id: Optional[str] = None
    candidate_products: list[str] = Field(..., min_length=1, max_length=MAX_CANDIDATE_PRODUCTS)
    device: Optional[str] = None
    source: Optional[str] = None
    channel: Optional[str] = None
    client_purchase_count_before: float = Field(0.0, ge=0.0)
    client_recency_days: float = Field(9999.0, ge=0.0)
    client_frequency_90d: float = Field(0.0, ge=0.0)
    client_category_affinity: float = Field(0.0, ge=0.0)

    @field_validator("candidate_products")
    @classmethod
    def _no_duplicates(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("candidate_products contient des doublons : chaque produit ne doit apparaitre qu'une fois")
        if any(not p or not p.strip() for p in value):
            raise ValueError("candidate_products ne peut pas contenir de valeur vide")
        return value


class RecommendationItem(BaseModel):
    product_id: str
    score: float
    rank: int


class RecommendationResponse(BaseModel):
    target: str
    model_used: str
    fallback_used: bool
    fallback_reason: Optional[str] = None
    status: str
    version: str
    dropped_products: list[str] = Field(default_factory=list)
    results: list[RecommendationItem]
    avertissement: str = (
        "Resultat academique sur donnees synthetiques : ne constitue ni une "
        "revendication de performance commerciale reelle, ni un effet causal."
    )


class PricingSimulationRequest(BaseModel):
    produit_key: str
    discount_proposed: float = Field(
        0.0, ge=0.0, le=100.0,
        description="Remise proposee en points de pourcentage (0 a 100), pas une fraction.")


class PricingSimulationResponse(BaseModel):
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
    avertissement: str = (
        "Simulation academique sur donnees synthetiques : aucune revendication "
        "causale, aucune application automatique du prix simule. Volume, chiffre "
        "d'affaires et marge estimes sont des medianes historiques par produit "
        "(baseline_mediane_produit) : ils ne varient PAS avec la remise proposee "
        "ci-dessus, car aucun modele valide ne relie la remise a ces cibles sur "
        "cette experience synthetique (remise confondue avec l'identite produit, "
        "cf. reports/v4_training/01_pricing_results.md). Seul le prix simule et le "
        "controle de garde-fou repondent a la remise proposee."
    )


class HealthResponse(BaseModel):
    status: str
    product: str
    data_status: str
    models_loaded: dict
    load_errors: dict
    uptime_seconds: float
