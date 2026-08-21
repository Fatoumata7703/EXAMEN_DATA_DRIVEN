"""API produit V4 : pricing (simulation) et recommandation (achat, panier).

Statut : `synthetic_academic_experiment`. Service de scoring academique sur
donnees synthetiques, distinct du produit V2 deja publie. Aucune ecriture
Supabase, aucun entrainement declenche par une requete, aucune application
automatique d'un prix ou d'une recommandation.
"""
from __future__ import annotations

import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from api_v4.registry import REGISTRY
from api_v4.schemas import (
    HealthResponse, PricingSimulationRequest, PricingSimulationResponse,
    RecommendationItem, RecommendationRequest, RecommendationResponse,
)
from api_v4.services import pricing as pricing_service
from api_v4.services import recommendation as recommendation_service

START_TIME = time.time()
METRICS = {"requests_total": 0, "fallback_triggered_total": 0, "errors_total": 0,
          "by_endpoint": {}}

app = FastAPI(
    title="API produit V4 - pricing et recommandation",
    version="1.0.0",
    description=(
        "Service de scoring academique sur donnees synthetiques "
        "(statut synthetic_academic_experiment). Aucune performance "
        "commerciale reelle n'est revendiquee, aucun resultat n'est "
        "presente comme causal, aucune action n'est appliquee "
        "automatiquement."
    ),
)


@app.middleware("http")
async def _count_requests(request: Request, call_next):
    METRICS["requests_total"] += 1
    endpoint = request.url.path
    METRICS["by_endpoint"][endpoint] = METRICS["by_endpoint"].get(endpoint, 0) + 1
    response = await call_next(request)
    if response.status_code >= 400:
        METRICS["errors_total"] += 1
    return response


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        product=REGISTRY.final_status.get("product", "v4_pricing_recommendation"),
        data_status=REGISTRY.final_status.get("status", "synthetic_academic_experiment"),
        models_loaded={
            "recommendation": sorted(REGISTRY.recommendation_models.keys()),
            "pricing": sorted(REGISTRY.pricing_models.keys()),
        },
        load_errors=dict(REGISTRY.load_errors),
        uptime_seconds=round(REGISTRY.uptime_seconds(), 3),
    )


@app.get("/metadata")
def metadata() -> dict:
    return REGISTRY.final_status


@app.get("/metrics")
def metrics() -> dict:
    return {**METRICS, "uptime_seconds": round(time.time() - START_TIME, 3)}


def _handle_recommendation(target: str, request: RecommendationRequest) -> RecommendationResponse:
    context = request.model_dump(exclude={"candidate_products"})
    try:
        outcome = recommendation_service.score_target(target, request.candidate_products, context)
    except recommendation_service.NoValidCandidatesError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if outcome.fallback_used:
        METRICS["fallback_triggered_total"] += 1
    return RecommendationResponse(
        target=outcome.target, model_used=outcome.model_used,
        fallback_used=outcome.fallback_used, fallback_reason=outcome.fallback_reason,
        status=outcome.status, version=outcome.version,
        dropped_products=outcome.dropped_products,
        results=[RecommendationItem(**row) for row in outcome.results],
    )


@app.post("/recommendations", response_model=RecommendationResponse)
def recommendations_achat(request: RecommendationRequest) -> RecommendationResponse:
    """Recommandation d'achat (`purchased_after`) : `CatBoostRanker`, repli
    automatique sur `popularite_globale_v1`."""
    return _handle_recommendation("purchased_after", request)


@app.post("/recommendations/cart", response_model=RecommendationResponse)
def recommendations_panier(request: RecommendationRequest) -> RecommendationResponse:
    """Recommandation d'ajout au panier (`added_to_cart_after`) :
    `pointwise_conversion`, repli automatique sur `popularite_globale_v1`."""
    return _handle_recommendation("added_to_cart_after", request)


@app.post("/pricing/simulation", response_model=PricingSimulationResponse)
def pricing_simulation(request: PricingSimulationRequest) -> PricingSimulationResponse:
    """Simulation pricing uniquement : baseline mediane produit, aucun prix
    optimal automatique, aucune application du resultat."""
    try:
        outcome = pricing_service.simulate(request.produit_key, request.discount_proposed)
    except pricing_service.UnknownProductError as exc:
        raise HTTPException(status_code=404, detail=f"produit inconnu du catalogue pricing : {exc}") from exc
    except pricing_service.PriceBelowCostError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"prix simule ({exc.prix_simule:.2f} XOF) inferieur au cout produit ({exc.cout:.2f} XOF)",
        ) from exc
    return PricingSimulationResponse(**outcome.__dict__)


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    METRICS["errors_total"] += 1
    return JSONResponse(status_code=500, content={"detail": "erreur interne inattendue"})
