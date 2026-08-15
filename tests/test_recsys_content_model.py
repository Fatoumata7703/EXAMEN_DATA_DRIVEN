"""Test de non-régression sur le bug groupby().apply(lambda: dict) du
modèle ContentBased (2026-08-14) : `train_ventes.groupby("client_key")["categorie"]
.apply(lambda s: s.value_counts(normalize=True).to_dict())` fait "déplier"
silencieusement le dict retourné par pandas en un MultiIndex (client_key,
categorie) -> float, au lieu d'un objet {client_key: {categorie: proportion}}.
Conséquence concrète observée : `cat_pref.get(...)` levait une
`AttributeError: 'float' object has no attribute 'get'`, capturée nulle part,
si bien que 100% des clients tombaient silencieusement en repli popularité
globale — un vrai modèle contenu jamais réellement utilisé.

Le correctif utilise une boucle explicite (dict comprehension sur
`.groupby()`) plutôt que `.apply()` avec un dict de retour.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.recsys.models import ContentBased


@pytest.fixture
def petit_jeu_ventes() -> pd.DataFrame:
    """Exemple calculé à la main :
    - CLI_A achète 3x categorie X, 1x categorie Y -> profil {X: 0.75, Y: 0.25}
    - CLI_B achète 2x categorie Y -> profil {Y: 1.0}
    """
    return pd.DataFrame({
        "client_key": ["CLI_A", "CLI_A", "CLI_A", "CLI_A", "CLI_B", "CLI_B"],
        "produit_key": ["P1", "P1", "P1", "P2", "P3", "P3"],
        "categorie": ["X", "X", "X", "Y", "Y", "Y"],
        "prix_base_xof": [100.0, 100.0, 100.0, 200.0, 50.0, 50.0],
    })


def test_client_cats_achats_est_un_dict_de_dicts_pas_un_multiindex(petit_jeu_ventes):
    """Preuve directe de la régression : la valeur associée à un client doit
    être un dict `{categorie: proportion}`, jamais un float."""
    model = ContentBased().fit(petit_jeu_ventes, train_web=None)
    assert isinstance(model.client_cats_achats["CLI_A"], dict), (
        f"Régression du bug groupby().apply() : attendu un dict, obtenu "
        f"{type(model.client_cats_achats.get('CLI_A'))}"
    )
    assert set(model.client_cats_achats.keys()) == {"CLI_A", "CLI_B"}


def test_profil_categorie_correspond_au_calcul_manuel(petit_jeu_ventes):
    model = ContentBased().fit(petit_jeu_ventes, train_web=None)
    profil_a = model.client_cats_achats["CLI_A"]
    assert profil_a["X"] == pytest.approx(0.75)
    assert profil_a["Y"] == pytest.approx(0.25)

    profil_b = model.client_cats_achats["CLI_B"]
    assert profil_b["Y"] == pytest.approx(1.0)
    assert "X" not in profil_b


def test_score_candidates_ne_leve_pas_et_privilegie_la_categorie_preferee(petit_jeu_ventes):
    """Avant le correctif, cet appel levait `AttributeError` pour tout client
    ayant un historique d'achat (capturée nulle part dans le pipeline —
    seul un test direct la révèle)."""
    model = ContentBased().fit(petit_jeu_ventes, train_web=None)
    scores = model.score_candidates("CLI_A", ["P1", "P2", "P3"])
    assert set(scores.keys()) == {"P1", "P2", "P3"}
    assert all(isinstance(v, float) for v in scores.values())
    # P1 (categorie X, la préférée à 75% pour CLI_A) doit scorer plus haut
    # qu'un produit de categorie Y (25%) à prix comparable.
    assert scores["P1"] > scores["P3"]


def test_repli_web_utilise_si_aucun_achat(petit_jeu_ventes):
    """Un client sans aucun achat mais avec des vues web doit recevoir un
    profil basé sur ces vues (jamais un repli silencieux vers la popularité
    pure tant qu'un signal existe)."""
    web = pd.DataFrame({
        "client_key": ["CLI_C", "CLI_C"],
        "produit_key": ["P1", "P1"],
        "type_event": ["view", "view"],
    })
    model = ContentBased().fit(petit_jeu_ventes, train_web=web)
    assert "CLI_C" not in model.client_cats_achats
    assert "CLI_C" in model.client_cats_web
    assert model.client_cats_web["CLI_C"].get("X") == pytest.approx(1.0)

    scores = model.score_candidates("CLI_C", ["P1", "P3"])
    assert scores["P1"] > scores["P3"]


def test_evenements_purchase_exclus_du_profil_web():
    """`type_event='purchase'` ne doit jamais alimenter le profil contenu —
    risque de refléter directement une vente (cf. rapport 36 §7)."""
    ventes = pd.DataFrame({
        "client_key": ["CLI_D"], "produit_key": ["P1"], "categorie": ["X"], "prix_base_xof": [100.0],
    })
    web = pd.DataFrame({
        "client_key": ["CLI_E", "CLI_E"], "produit_key": ["P1", "P2"], "type_event": ["purchase", "purchase"],
    })
    model = ContentBased().fit(ventes, train_web=web)
    assert "CLI_E" not in model.client_cats_web, (
        "Les événements `purchase` ne doivent jamais construire un profil contenu."
    )
