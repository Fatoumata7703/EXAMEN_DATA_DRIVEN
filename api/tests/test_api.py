from __future__ import annotations

from fastapi.testclient import TestClient

from api.config import Settings
from api.main import create_app


def test_health_and_ready(client):
    assert client.get("/health").json() == {"status": "ok"}
    ready = client.get("/ready")
    assert ready.status_code == 200
    assert all(ready.json()["checks"].values())


def test_models_status(client):
    response = client.get("/api/v1/models/status")
    assert response.status_code == 200
    assert response.json()["pricing"]["metrics"] == {"wape": 0.5526, "forecast_bias": 0.0013}
    assert set(response.json()["artifact_sha256"]) == {
        "metadata.json", "catalog.json", "pricing_model.joblib"
    }


def test_general_recommendation(client):
    response = client.post("/api/v1/recommendations/general", json={"k": 10})
    body = response.json()
    assert response.status_code == 200
    assert body["model_name"] == "popularite_globale"
    assert body["personalization_validated"] is False
    assert len(body["recommendations"]) == 10


def test_basket_baseline_excludes_context(client, registry):
    product = registry.catalog["recommendation_popularity"][0]["product_key"]
    response = client.post("/api/v1/recommendations/basket", json={"product_keys": [product], "k": 10})
    body = response.json()
    assert response.status_code == 200
    assert body["model_status"] == "baseline_only"
    assert product not in {item["product_key"] for item in body["recommendations"]}


def test_valid_pricing(client, valid_pricing_payload):
    response = client.post("/api/v1/pricing/simulate", json=valid_pricing_payload)
    body = response.json()
    assert response.status_code == 200
    assert body["model_status"] == "exploratory_non_causal"
    assert body["automatic_application_allowed"] is False


def test_unknown_product(client, valid_pricing_payload):
    valid_pricing_payload["product_key"] = "UNKNOWN"
    response = client.post("/api/v1/pricing/simulate", json=valid_pricing_payload)
    assert response.status_code == 404


def test_invalid_pricing(client, valid_pricing_payload):
    valid_pricing_payload["candidate_discounts_pct"] = [99]
    response = client.post("/api/v1/pricing/simulate", json=valid_pricing_payload)
    assert response.status_code == 409


def test_api_key(model_root):
    app = create_app(Settings(model_root=model_root, api_key="secret-test-key"))
    with TestClient(app) as protected:
        assert protected.get("/health").status_code == 200
        assert protected.get("/api/v1/models/status").status_code == 401
        authenticated = protected.get(
            "/api/v1/models/status", headers={"X-API-Key": "secret-test-key"}
        )
        assert authenticated.status_code == 200


def test_session_is_stable_501(client):
    response = client.post("/api/v1/recommendations/session")
    assert response.status_code == 501
    assert response.json()["session_model_status"] == "non_utilisable"


def test_internal_error_is_scrubbed(model_root, monkeypatch):
    def explode(*args, **kwargs):
        raise RuntimeError("secret /local/path connection-string")
    monkeypatch.setattr("api.main.recommend", explode)
    app = create_app(Settings(model_root=model_root))
    with TestClient(app, raise_server_exceptions=False) as value:
        response = value.post("/api/v1/recommendations/general", json={"k": 1})
    assert response.status_code == 500
    text = response.text
    assert "secret" not in text
    assert "local/path" not in text
