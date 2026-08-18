from __future__ import annotations

from datetime import date
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, StrictStr, field_validator

Identifier = Annotated[StrictStr, Field(min_length=1, max_length=128, pattern=r"^\S(?:.*\S)?$")]
KValue = Annotated[StrictInt, Field(ge=1, le=50)]
Discount = Annotated[StrictFloat | StrictInt, Field(ge=0, le=100)]
FeatureValue = StrictFloat | StrictInt


class StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


def _unique(values: list[str] | list[float | int], field_name: str):
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} ne doit contenir aucun doublon")
    return values


class GeneralRecommendationRequest(StrictModel):
    client_key: Identifier | None = None
    k: KValue = 10
    exclude_product_keys: list[Identifier] = Field(default_factory=list, max_length=500)
    eligible_product_keys: list[Identifier] = Field(default_factory=list, max_length=5000)

    @field_validator("exclude_product_keys", "eligible_product_keys")
    @classmethod
    def unique_products(cls, values: list[str], info):
        return _unique(values, info.field_name)


class BasketRecommendationRequest(StrictModel):
    product_keys: list[Identifier] = Field(min_length=1, max_length=100)
    k: KValue = 10
    eligible_product_keys: list[Identifier] = Field(default_factory=list, max_length=5000)

    @field_validator("product_keys", "eligible_product_keys")
    @classmethod
    def unique_products(cls, values: list[str], info):
        return _unique(values, info.field_name)


class PricingSimulationRequest(StrictModel):
    product_key: Identifier
    decision_date: Annotated[date, Field(strict=False)]
    candidate_discounts_pct: list[Discount] = Field(min_length=1, max_length=20)
    features: dict[Identifier, FeatureValue]

    @field_validator("candidate_discounts_pct")
    @classmethod
    def unique_discounts(cls, values: list[float | int]):
        return _unique(values, "candidate_discounts_pct")


class RecommendationItem(StrictModel):
    rank: int
    product_key: str
    score: float
    reason: str


class RecommendationResponse(StrictModel):
    request_id: str
    recommendations: list[RecommendationItem]
    model_name: str
    model_status: str
    personalization_validated: bool
    catalog_coverage_warning: bool


class BasketRecommendationResponse(RecommendationResponse):
    fallback_used: bool


class PricingCandidateResult(StrictModel):
    discount_pct: float
    catalog_price_xof: float
    simulated_price_xof: float
    cost_xof: float
    predicted_quantity: float
    expected_revenue_xof: float
    expected_margin_xof: float
    margin_rate: float
    support_status: str
    simulation_status: str


class PricingSimulationResponse(StrictModel):
    request_id: str
    product_key: str
    decision_date: date
    simulations: list[PricingCandidateResult]
    model_name: str
    model_status: str
    automatic_application_allowed: bool
    human_validation_required: bool
    causal_effect_estimated: bool
    pricing_wape: float
    pricing_bias: float
