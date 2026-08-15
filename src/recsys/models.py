"""5 modèles baseline de recommandation — interface commune `fit(train)` /
`score_candidates(client_id, candidates) -> {produit: score}`.

Aucun modèle n'utilise d'information postérieure au cutoff d'entraînement.
Les événements web de type `purchase` sont exclus des profils contenu
(risque de refléter directement une vente — cf. rapport 36 §7) ; seuls
`view` et `add_to_cart` alimentent le contenu-based en repli cold-start.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class FitResult:
    name: str


class PopularityGlobal:
    name = "popularite_globale"

    def fit(self, train_ventes: pd.DataFrame, train_web: pd.DataFrame | None = None) -> "PopularityGlobal":
        self.scores = train_ventes.groupby("produit_key")["client_key"].nunique().sort_values(ascending=False)
        self.scores = (self.scores / self.scores.max()).to_dict()
        return self

    def score_candidates(self, client_id: str, candidates: list[str]) -> dict[str, float]:
        return {p: self.scores.get(p, 0.0) for p in candidates}


class PopularityRecent:
    name = "popularite_recente"

    def __init__(self, window_days: int = 60):
        self.window_days = window_days

    def fit(self, train_ventes: pd.DataFrame, train_web: pd.DataFrame | None = None) -> "PopularityRecent":
        cutoff = train_ventes["date_complete"].max()
        recent = train_ventes[train_ventes["date_complete"] > cutoff - pd.Timedelta(days=self.window_days)]
        self.scores = recent.groupby("produit_key")["client_key"].nunique().sort_values(ascending=False)
        self.scores = (self.scores / self.scores.max()).to_dict() if len(self.scores) else {}
        return self

    def score_candidates(self, client_id: str, candidates: list[str]) -> dict[str, float]:
        return {p: self.scores.get(p, 0.0) for p in candidates}


class PopularityByCategory:
    name = "popularite_categorie"

    def fit(self, train_ventes: pd.DataFrame, train_web: pd.DataFrame | None = None) -> "PopularityByCategory":
        self.pop_by_cat = {}
        for cat, g in train_ventes.groupby("categorie"):
            s = g.groupby("produit_key")["client_key"].nunique().sort_values(ascending=False)
            self.pop_by_cat[cat] = (s / s.max()).to_dict()
        self.client_top_cat = (
            train_ventes.groupby(["client_key", "categorie"]).size().rename("n")
            .reset_index().sort_values("n", ascending=False).drop_duplicates("client_key")
            .set_index("client_key")["categorie"].to_dict()
        )
        self.produit_categorie = train_ventes.drop_duplicates("produit_key").set_index("produit_key")["categorie"].to_dict()
        self.global_pop = train_ventes.groupby("produit_key")["client_key"].nunique().sort_values(ascending=False)
        self.global_pop = (self.global_pop / self.global_pop.max()).to_dict()
        return self

    def score_candidates(self, client_id: str, candidates: list[str]) -> dict[str, float]:
        cat = self.client_top_cat.get(client_id)
        if cat is None or cat not in self.pop_by_cat:
            return {p: self.global_pop.get(p, 0.0) for p in candidates}
        cat_scores = self.pop_by_cat[cat]
        out = {}
        for p in candidates:
            if self.produit_categorie.get(p) == cat:
                out[p] = cat_scores.get(p, 0.0)
            else:
                out[p] = 0.1 * self.global_pop.get(p, 0.0)  # produit hors catégorie préférée : score réduit, jamais nul
        return out


class CollaborativeFilteringItemItem:
    """Filtrage collaboratif implicite, item-item, similarité cosinus sur la
    matrice binaire client×produit du train. Score d'un candidat pour un
    client = moyenne des similarités aux produits déjà achetés par ce client."""

    name = "collaboratif_item_item"

    def fit(self, train_ventes: pd.DataFrame, train_web: pd.DataFrame | None = None) -> "CollaborativeFilteringItemItem":
        from sklearn.metrics.pairwise import cosine_similarity

        pivot = pd.crosstab(train_ventes["client_key"], train_ventes["produit_key"])
        pivot = (pivot > 0).astype(float)
        self.products = list(pivot.columns)
        self.product_index = {p: i for i, p in enumerate(self.products)}
        sim = cosine_similarity(pivot.T.to_numpy())
        np.fill_diagonal(sim, 0.0)
        self.sim = sim
        self.client_items = train_ventes.groupby("client_key")["produit_key"].apply(set).to_dict()
        return self

    def score_candidates(self, client_id: str, candidates: list[str]) -> dict[str, float] | None:
        items = self.client_items.get(client_id)
        if not items:
            return None  # pas de signal collaboratif possible : repli explicite requis
        idxs = [self.product_index[i] for i in items if i in self.product_index]
        if not idxs:
            return None
        sub = self.sim[idxs, :]
        agg = sub.mean(axis=0)
        maxv = agg.max()
        agg = agg / maxv if maxv > 0 else agg
        out = {}
        for p in candidates:
            j = self.product_index.get(p)
            out[p] = float(agg[j]) if j is not None else 0.0
        return out


class ContentBased:
    """Contenu catégorie/prix — utilisé nativement pour compléter le
    collaboratif et comme repli explicite quand celui-ci est impossible
    (cold-start). Profil basé sur les achats ; à défaut, sur les
    événements web `view`/`add_to_cart` (jamais `purchase`, cf. docstring
    module)."""

    name = "contenu_categorie_prix"

    def fit(self, train_ventes: pd.DataFrame, train_web: pd.DataFrame | None = None) -> "ContentBased":
        self.produit_cat = train_ventes.drop_duplicates("produit_key").set_index("produit_key")["categorie"].to_dict()
        self.produit_prix = train_ventes.drop_duplicates("produit_key").set_index("produit_key")["prix_base_xof"].to_dict()
        # Boucle explicite plutôt que groupby().apply(lambda ...dict) : pandas
        # "déplie" parfois un dict retourné par apply en MultiIndex au lieu de
        # le garder comme une seule valeur par groupe (piège vérifié ici —
        # provoquait un repli silencieux vers la popularité pour 100% des
        # clients). .agg() avec une fonction qui retourne un objet unique
        # (ici un dict) est le chemin fiable.
        self.client_cats_achats = {
            uid: g["categorie"].value_counts(normalize=True).to_dict()
            for uid, g in train_ventes.groupby("client_key")
        }
        self.client_prix_moyen = train_ventes.groupby("client_key")["prix_base_xof"].mean().to_dict()

        self.client_cats_web = {}
        if train_web is not None and len(train_web):
            web_signal = train_web[train_web["type_event"].isin(["view", "add_to_cart"])].merge(
                train_ventes.drop_duplicates("produit_key")[["produit_key", "categorie"]], on="produit_key", how="left"
            )
            self.client_cats_web = {
                uid: g["categorie"].value_counts(normalize=True).to_dict()
                for uid, g in web_signal.groupby("client_key")
            }

        self.global_pop = train_ventes.groupby("produit_key")["client_key"].nunique().sort_values(ascending=False)
        self.global_pop = (self.global_pop / self.global_pop.max()).to_dict()
        return self

    def score_candidates(self, client_id: str, candidates: list[str]) -> dict[str, float]:
        cat_pref = self.client_cats_achats.get(client_id) or self.client_cats_web.get(client_id)
        prix_ref = self.client_prix_moyen.get(client_id)
        if not cat_pref:
            return {p: self.global_pop.get(p, 0.0) for p in candidates}  # aucun signal contenu : repli popularité

        out = {}
        for p in candidates:
            cat_score = cat_pref.get(self.produit_cat.get(p), 0.0)
            if prix_ref and self.produit_prix.get(p):
                prix_score = 1.0 / (1.0 + abs(self.produit_prix[p] - prix_ref) / max(prix_ref, 1.0))
            else:
                prix_score = 0.5
            out[p] = 0.7 * cat_score + 0.3 * prix_score
        return out


ALL_MODELS = [PopularityGlobal, PopularityRecent, PopularityByCategory, CollaborativeFilteringItemItem, ContentBased]
