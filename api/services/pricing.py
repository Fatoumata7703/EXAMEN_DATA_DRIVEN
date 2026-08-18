from __future__ import annotations

from datetime import date

import numpy as np

from api.errors import ApiError
from api.schemas import PricingCandidateResult
from api.services.model_loader import ModelRegistry

MIN_MARGIN_RATE = 0.05
FORBIDDEN_FEATURES = frozenset({"n_lignes", "quantite", "ca_xof", "marge_xof",
                                "prix_unitaire_paye_xof", "niveau_stock"})


def simulate(
    registry: ModelRegistry,
    product_key: str,
    decision_date: date,
    discounts: list[float | int],
    request_features: dict[str, float | int],
) -> list[PricingCandidateResult]:
    catalog = registry.catalog["pricing_catalog"]
    if product_key not in catalog:
        raise ApiError(404, "unknown_product", "Produit inconnu")
    if "stock_at_cutoff" not in request_features:
        raise ApiError(400, "missing_required_features", "La feature stock_at_cutoff est obligatoire")
    forbidden = set(request_features) & FORBIDDEN_FEATURES
    if forbidden:
        raise ApiError(400, "forbidden_features", "Une feature contemporaine ou cible est interdite",
                       {"features": sorted(forbidden)})

    allowed = set(registry.pricing_artifact["features"])
    unknown = set(request_features) - allowed
    if unknown:
        raise ApiError(400, "unknown_features", "Features non inscrites au registre honnête",
                       {"features": sorted(unknown)})
    row = catalog[product_key]
    supported = {float(value) for value in row["supported_discounts_pct"]}
    unsupported = sorted(float(value) for value in discounts if float(value) not in supported)
    if unsupported:
        raise ApiError(409, "unsupported_discount", "Remise non supportée historiquement",
                       {"discounts_pct": unsupported})

    snapshot = dict(row["feature_snapshot"])
    for name, raw_value in request_features.items():
        value = float(raw_value)
        minimum, maximum = row["feature_ranges"][name]
        if value < minimum or value > maximum:
            raise ApiError(
                409,
                "feature_extrapolation",
                f"{name} hors support historique",
                {"feature": name, "supported_range": [minimum, maximum]},
            )
    snapshot.update({key: float(value) for key, value in request_features.items()})
    price = float(row["catalog_price_xof"])
    cost = float(row["cost_xof"])
    model = registry.pricing_artifact["model"]
    features = registry.pricing_artifact["features"]
    results: list[PricingCandidateResult] = []

    for raw_discount in discounts:
        discount = float(raw_discount)
        simulated_price = price * (1 - discount / 100)
        if simulated_price < cost:
            raise ApiError(409, "price_below_cost", "Le prix simulé serait inférieur au coût",
                           {"discount_pct": discount})
        margin_rate = (simulated_price - cost) / simulated_price if simulated_price else 0.0
        if margin_rate < MIN_MARGIN_RATE:
            raise ApiError(409, "margin_below_floor", "La marge simulée serait inférieure à 5 %",
                           {"discount_pct": discount})

        values = dict(snapshot)
        values.update({
            "remise_pct": discount,
            "planned_paid_price_xof": simulated_price,
            "unit_margin_before_xof": price - cost,
            "unit_margin_after_xof": simulated_price - cost,
            "margin_rate_after": margin_rate,
            "discount_x_category": discount * float(values["category_code"]),
            "discount_x_product": discount * float(values["product_code"]),
            "dow": float(decision_date.weekday()),
            "week": float(decision_date.isocalendar().week),
            "month": float(decision_date.month),
            "weekend": float(decision_date.weekday() >= 5),
        })
        matrix = np.asarray([[values[name] for name in features]], dtype=float)
        predictor = getattr(model, "booster_", model)
        quantity = max(0.0, float(predictor.predict(matrix)[0]))
        revenue = simulated_price * quantity
        margin = (simulated_price - cost) * quantity
        results.append(PricingCandidateResult(
            discount_pct=discount,
            catalog_price_xof=round(price, 2),
            simulated_price_xof=round(simulated_price, 2),
            cost_xof=round(cost, 2),
            predicted_quantity=round(quantity, 4),
            expected_revenue_xof=round(revenue, 2),
            expected_margin_xof=round(margin, 2),
            margin_rate=round(margin_rate, 4),
            support_status="supported",
            simulation_status="exploratory",
        ))
    return results
