"""Interface commune aux 4 méthodes d'uplift : `fit(train_panel)` puis
`predict(frame)` -> quantité prévue. Permet une validation temporelle et un
simulateur strictement identiques d'une méthode à l'autre — même contrat,
mêmes données d'entrée, seule la méthode change.

Toutes les méthodes sont entraînées UNIQUEMENT sur `train` (jamais sur des
données postérieures à la fenêtre d'entraînement) — condition de validité de
la validation temporelle du point 7.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

CAT_GLOBAL_FALLBACK_KEY = "__GLOBAL__"


def _dow_baseline(train: pd.DataFrame) -> tuple[dict, dict, float]:
    """Baseline hors-promo par (produit, jour de semaine), avec repli
    catégorie puis global si le produit n'a pas assez d'historique hors-promo
    pour ce jour de semaine précis."""
    hp = train[train["en_promotion"] == False]  # noqa: E712
    by_prod_dow = hp.groupby(["unique_id", "jour_semaine"])["quantite_vendue"].mean().to_dict()
    by_cat_dow = hp.groupby(["categorie", "jour_semaine"])["quantite_vendue"].mean().to_dict()
    global_mean = float(hp["quantite_vendue"].mean()) if len(hp) else float(train["quantite_vendue"].mean())
    return by_prod_dow, by_cat_dow, global_mean


def _lookup_baseline(uid: str, categorie: str, dow: int, by_prod_dow: dict, by_cat_dow: dict, global_mean: float) -> float:
    if (uid, dow) in by_prod_dow:
        return by_prod_dow[(uid, dow)]
    if (categorie, dow) in by_cat_dow:
        return by_cat_dow[(categorie, dow)]
    return global_mean


@dataclass
class DescriptivePredictor:
    by_prod_dow: dict = field(default_factory=dict)
    by_cat_dow: dict = field(default_factory=dict)
    global_mean: float = 0.0
    uplift_by_prod_level: dict = field(default_factory=dict)   # (uid, remise) -> residuel moyen
    uplift_by_cat_level: dict = field(default_factory=dict)    # (categorie, remise) -> residuel moyen

    name: str = "descriptif_intra_produit"

    def fit(self, train: pd.DataFrame) -> "DescriptivePredictor":
        self.by_prod_dow, self.by_cat_dow, self.global_mean = _dow_baseline(train)
        hp = train[train["en_promotion"] == False]  # noqa: E712
        dow_mean_prod = hp.groupby(["unique_id", "jour_semaine"])["quantite_vendue"].mean()
        promo = train[train["en_promotion"] == True].copy()  # noqa: E712
        promo["y_att"] = promo.apply(lambda r: self.by_prod_dow.get((r["unique_id"], r["jour_semaine"]), self.global_mean), axis=1)
        promo["resid"] = promo["quantite_vendue"] - promo["y_att"]
        self.uplift_by_prod_level = promo.groupby(["unique_id", "remise_planifiee_pct"])["resid"].mean().to_dict()
        self.uplift_by_cat_level = promo.groupby(["categorie", "remise_planifiee_pct"])["resid"].mean().to_dict()
        return self

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        out = np.zeros(len(frame))
        for i, r in enumerate(frame.itertuples()):
            base = _lookup_baseline(r.unique_id, r.categorie, r.jour_semaine, self.by_prod_dow, self.by_cat_dow, self.global_mean)
            if r.remise_planifiee_pct <= 0:
                out[i] = base
                continue
            key = (r.unique_id, r.remise_planifiee_pct)
            resid = self.uplift_by_prod_level.get(key)
            if resid is None:
                resid = self.uplift_by_cat_level.get((r.categorie, r.remise_planifiee_pct), 0.0)
            out[i] = max(base + resid, 0.0)
        return out


@dataclass
class PanelFEPredictor:
    coef: dict = field(default_factory=dict)
    prod_means_x: dict = field(default_factory=dict)   # uid -> {var: mean}
    prod_means_y: dict = field(default_factory=dict)   # uid -> mean(log1p_y)
    global_means_x: dict = field(default_factory=dict)
    global_mean_y: float = 0.0
    dow_dummy_cols: list = field(default_factory=list)
    catmois_dummy_cols: list = field(default_factory=list)

    name: str = "panel_effets_fixes"

    def fit(self, train: pd.DataFrame, min_obs_per_product: int = 10) -> "PanelFEPredictor":
        import statsmodels.api as sm

        df = train.copy()
        counts = df.groupby("unique_id").size()
        keep = counts[counts >= min_obs_per_product].index
        df = df[df["unique_id"].isin(keep)].copy()

        dow_dummies = pd.get_dummies(df["jour_semaine"], prefix="dow", drop_first=True).astype(float)
        catmois_key = df["categorie"].astype(str) + "_" + df["mois"].astype(str)
        catmois_dummies = pd.get_dummies(catmois_key, prefix="catmois", drop_first=True).astype(float)
        self.dow_dummy_cols = list(dow_dummies.columns)
        self.catmois_dummy_cols = list(catmois_dummies.columns)
        stock = df["stock_disponible_lag1"].fillna(df["stock_disponible_lag1"].median())

        X = pd.concat([
            df[["remise_planifiee_pct"]].rename(columns={"remise_planifiee_pct": "remise"}),
            dow_dummies, catmois_dummies, stock.rename("stock_lag1").astype(float),
        ], axis=1)
        y = df["log1p_y"]
        group = df["unique_id"]

        group_means_x = X.groupby(group).mean()
        group_means_y = y.groupby(group).mean()
        self.prod_means_x = group_means_x.to_dict(orient="index")
        self.prod_means_y = group_means_y.to_dict()
        self.global_means_x = X.mean().to_dict()
        self.global_mean_y = float(y.mean())

        # Démoyennage par jointure explicite (map/loc) plutôt que .groupby().transform() :
        # évite le chemin interne reindex/take_nd de pandas, plus gourmand en pics mémoire
        # sur ce dataset (~118k lignes) — cause de deux échecs transitoires d'allocation.
        aligned_means_x = group_means_x.loc[group.to_numpy()].set_axis(X.index)
        aligned_means_y = group_means_y.loc[group.to_numpy()].set_axis(y.index)
        X_within = X - aligned_means_x
        y_within = y - aligned_means_y
        X_within = sm.add_constant(X_within, has_constant="add")
        fit = sm.OLS(y_within, X_within).fit(cov_type="cluster", cov_kwds={"groups": group})
        self.coef = fit.params.to_dict()
        self._catmois_key_template = catmois_key.name
        return self

    def _row_features(self, r) -> dict:
        catmois = f"{r.categorie}_{r.mois}"
        feats = {"remise": r.remise_planifiee_pct}
        for c in self.dow_dummy_cols:
            feats[c] = 1.0 if c == f"dow_{r.jour_semaine}" else 0.0
        for c in self.catmois_dummy_cols:
            feats[c] = 1.0 if c == f"catmois_{catmois}" else 0.0
        feats["stock_lag1"] = r.stock_disponible_lag1 if not pd.isna(r.stock_disponible_lag1) else self.global_means_x.get("stock_lag1", 0.0)
        return feats

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        out = np.zeros(len(frame))
        for i, r in enumerate(frame.itertuples()):
            feats = self._row_features(r)
            means_x = self.prod_means_x.get(r.unique_id, self.global_means_x)
            mean_y = self.prod_means_y.get(r.unique_id, self.global_mean_y)
            delta = self.coef.get("const", 0.0)
            for k, v in feats.items():
                delta += self.coef.get(k, 0.0) * (v - means_x.get(k, self.global_means_x.get(k, 0.0)))
            log1p_pred = mean_y + delta
            out[i] = max(np.expm1(log1p_pred), 0.0)
        return out


@dataclass
class HierarchicalPredictor:
    by_prod_dow: dict = field(default_factory=dict)
    by_cat_dow: dict = field(default_factory=dict)
    global_mean: float = 0.0
    rate_by_prod: dict = field(default_factory=dict)   # log-uplift par point de remise, par produit (shrinké)
    rate_by_cat: dict = field(default_factory=dict)

    name: str = "hierarchique_pooling_categorie"

    def fit(self, train: pd.DataFrame, shrinkage_k: float = 30.0) -> "HierarchicalPredictor":
        from src.pricing.uplift_methods import method_hierarchical_pooling

        self.by_prod_dow, self.by_cat_dow, self.global_mean = _dow_baseline(train)
        h = method_hierarchical_pooling(train, shrinkage_k=shrinkage_k)
        avg_level_prod = train[train["en_promotion"] == True].groupby("unique_id")["remise_planifiee_pct"].mean()
        avg_level_cat = train[train["en_promotion"] == True].groupby("categorie")["remise_planifiee_pct"].mean()
        h = h.set_index("unique_id")
        for uid, row in h.iterrows():
            avg_level = avg_level_prod.get(uid, avg_level_cat.get(row["categorie"], 15.0))
            avg_level = avg_level if avg_level and avg_level > 0 else 15.0
            self.rate_by_prod[uid] = row["effet_shrinkage"] / avg_level
        for cat, eff in h.groupby("categorie")["effet_categorie"].first().items():
            avg_level = avg_level_cat.get(cat, 15.0)
            avg_level = avg_level if avg_level and avg_level > 0 else 15.0
            self.rate_by_cat[cat] = eff / avg_level
        return self

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        out = np.zeros(len(frame))
        for i, r in enumerate(frame.itertuples()):
            base = _lookup_baseline(r.unique_id, r.categorie, r.jour_semaine, self.by_prod_dow, self.by_cat_dow, self.global_mean)
            rate = self.rate_by_prod.get(r.unique_id, self.rate_by_cat.get(r.categorie, 0.0))
            log1p_pred = np.log1p(base) + rate * r.remise_planifiee_pct
            out[i] = max(np.expm1(log1p_pred), 0.0)
        return out


@dataclass
class MLChallengerPredictor:
    model: object = None
    feat_cols: list = field(default_factory=list)
    cat_cols: list = field(default_factory=list)

    name: str = "challenger_ml_lightgbm"

    def fit(self, train: pd.DataFrame) -> "MLChallengerPredictor":
        from src.pricing.uplift_methods import method_ml_challenger_fit

        self.model, self.feat_cols, self.cat_cols = method_ml_challenger_fit(train)
        return self

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        from src.pricing.uplift_methods import method_ml_challenger_predict

        return method_ml_challenger_predict(self.model, self.feat_cols, self.cat_cols, frame)


ALL_PREDICTOR_CLASSES = [DescriptivePredictor, PanelFEPredictor, HierarchicalPredictor, MLChallengerPredictor]
