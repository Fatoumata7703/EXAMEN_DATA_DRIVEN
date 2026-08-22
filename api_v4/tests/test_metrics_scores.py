"""Tests de la route `/metrics` et de la coherence des scores affiches.

Exigence centrale : aucune valeur de score ne doit etre inventee ni ecrite en
dur. Chaque nombre servi doit provenir des metadonnees finales, et une
metrique absente doit valoir `null` plutot que zero.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from api_v4.config import MODELS_DIR, STATIC_DIR
from api_v4.main import app
from src.config.settings import PROJECT_ROOT

client = TestClient(app)

CIBLES_PRICING = ("units_sold_window_7j", "revenue_window_xof_7j", "margin_window_xof_7j")


@pytest.fixture(scope="module")
def scores() -> dict:
    return client.get("/metrics").json()


@pytest.fixture(scope="module")
def final_status() -> dict:
    return json.loads((MODELS_DIR / "FINAL_STATUS.json").read_text(encoding="utf-8"))


# ------------------------------------------------------------- structure


def test_metrics_expose_les_trois_domaines(scores):
    for domaine in ("forecasting", "pricing", "recommendation"):
        assert domaine in scores, f"domaine manquant dans /metrics : {domaine}"


def test_metrics_conserve_les_compteurs_operationnels(scores):
    """Les compteurs restent disponibles, deplaces sous la clef `service`."""
    assert "service" in scores
    assert "requests_total" in scores["service"]


# ------------------------------------------------------------ forecasting


def test_forecasting_reprend_exactement_la_decision_v2(scores):
    statut = json.loads(
        (PROJECT_ROOT / "models" / "FINAL_STATUS.json").read_text(encoding="utf-8"))["status"]
    f = scores["forecasting"]
    assert f["planning_model"] == statut["forecasting_30d_model"] == "LightGBM_direct_per_horizon"
    assert f["daily_model"] == statut["forecasting_daily_model"] == "CrostonOptimized"
    assert f["wape30_macro"] == statut["forecasting_wape30_macro"] == 0.25831
    assert f["forecast_bias_macro"] == statut["forecasting_bias"] == -0.02589


def test_forecasting_ne_revendique_pas_une_exactitude_de_90_pour_cent(scores):
    assert "90" in scores["forecasting"]["note"]


# ---------------------------------------------------------------- pricing


def test_pricing_present_dans_metrics(scores):
    p = scores["pricing"]
    assert p["model"] == "baseline_mediane_produit"
    assert p["status"] == "simulation_only"
    assert set(p["targets"]) == set(CIBLES_PRICING)


def test_pricing_present_dans_metadata(final_status):
    cibles = {e["target"] for e in final_status["models"] if e["domain"] == "pricing"}
    assert cibles == set(CIBLES_PRICING)


def test_pricing_ne_revendique_ni_causalite_ni_prix_optimal(scores):
    p = scores["pricing"]
    assert p["causal_effect_estimated"] is False
    assert p["automatic_optimal_price"] is False


def test_scores_pricing_identiques_aux_metadonnees(scores, final_status):
    """Coherence stricte : chaque WAPE et biais servi doit egaler la valeur
    enregistree dans les metadonnees, sans arrondi ni recalcul."""
    par_cible = {e["target"]: e["metrics"] for e in final_status["models"]
                 if e["domain"] == "pricing"}
    for cible in CIBLES_PRICING:
        servi = scores["pricing"]["targets"][cible]
        attendu = par_cible[cible]
        assert servi["wape_macro"] == attendu["wape_macro"]
        assert servi["bias_macro"] == attendu["bias"]


def test_aucune_valeur_pricing_inventee(scores):
    """Chaque metrique servie existe reellement dans les metadonnees, ou vaut
    `null`. Aucune ne doit valoir zero par defaut."""
    for cible in CIBLES_PRICING:
        c = scores["pricing"]["targets"][cible]
        assert c["disponible"] is True
        for clef in ("wape_macro", "bias_macro"):
            assert c[clef] is not None, f"{cible}.{clef} absent"
        # une WAPE nulle serait suspecte : elle signalerait une valeur par defaut
        assert c["wape_macro"] > 0, f"{cible} : WAPE nulle, valeur de remplacement probable"


# --------------------------------------------------------- recommandation


def test_recommandation_expose_les_trois_roles(scores):
    assert set(scores["recommendation"]) == {"purchase", "add_to_cart", "view"}


def test_recommandation_modeles_et_gains_conformes_aux_metadonnees(scores, final_status):
    par_cible = {e["target"]: e for e in final_status["models"]
                 if e["domain"] == "recommendation" and e.get("sha256")}
    attendu = {
        "purchase": ("purchased_after", "CatBoostRanker", "validated_academic"),
        "add_to_cart": ("added_to_cart_after", "pointwise_conversion", "validated_academic"),
        "view": ("viewed_after_impression", "CatBoostRanker", "exploratory"),
    }
    for role, (cible, modele, statut) in attendu.items():
        servi = scores["recommendation"][role]
        assert servi["model"] == modele
        assert servi["status"] == statut
        assert servi["ndcg10_gain_relative"] == par_cible[cible]["metrics"]["relative_ndcg_gain"]
        assert servi["holm_pvalue_independent"] == \
            par_cible[cible]["metrics"]["p_value_holm_independante"]


def test_gains_recommandation_correspondent_aux_valeurs_publiees(scores):
    """Verifie les ordres de grandeur publies dans les rapports V4."""
    assert scores["recommendation"]["purchase"]["ndcg10_gain_relative"] == pytest.approx(0.0857, abs=1e-4)
    assert scores["recommendation"]["purchase"]["holm_pvalue_independent"] == pytest.approx(0.00075, abs=1e-5)
    assert scores["recommendation"]["add_to_cart"]["ndcg10_gain_relative"] == pytest.approx(0.0770, abs=1e-4)
    assert scores["recommendation"]["add_to_cart"]["holm_pvalue_independent"] == pytest.approx(0.0015, abs=1e-5)
    assert scores["recommendation"]["view"]["ndcg10_gain_relative"] == pytest.approx(0.0557, abs=1e-4)


def test_le_modele_de_consultation_reste_exploratoire_et_non_par_defaut(scores):
    vue = scores["recommendation"]["view"]
    assert vue["status"] == "exploratory"
    assert vue["used_by_default"] is False
    assert vue["fallback"] == "popularite_globale_v1"


# ------------------------------------------------------------- interface


def test_la_console_ne_code_aucun_score_en_dur():
    """Les scores affiches doivent venir de l'API, pas du script."""
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    for valeur in ("0.25831", "0,25831", "0.02589", "0,02589",
                   "0.0857", "0,0857", "0.00075", "0,00075",
                   "0.1342", "0,1342", "0.077", "0,077"):
        assert valeur not in script, (
            f"score {valeur} ecrit en dur dans la console ; il doit etre lu depuis l'API")


def test_la_console_affiche_les_trois_domaines():
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    for titre in ('bloc("Forecasting")', 'bloc("Pricing")', 'bloc("Recommandation")'):
        assert titre in script, f"domaine absent de la console : {titre}"


def test_la_console_propose_des_liens_vers_docs_et_metrics():
    page = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    assert 'href="/metrics"' in page
    assert 'href="/docs"' in page


def test_la_console_ne_reference_aucun_endpoint_v2():
    """Aucun appel a l'ancienne API V2 ne doit subsister."""
    for fichier in ("app.js", "index.html"):
        contenu = (STATIC_DIR / fichier).read_text(encoding="utf-8")
        assert "/api/v1" not in contenu, f"reference a l'API V2 dans {fichier}"
        assert "/ready" not in contenu, f"sonde V2 referencee dans {fichier}"
        assert "examen-data-driven.onrender.com" not in contenu


def test_la_console_utilise_des_badges_de_statut():
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    for statut in ("validated_academic", "exploratory", "simulation_only", "validated"):
        assert statut in script, f"badge manquant pour le statut {statut}"
