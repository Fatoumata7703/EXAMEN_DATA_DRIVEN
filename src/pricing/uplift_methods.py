"""Quatre méthodes d'estimation de l'uplift remise → quantité, jamais
présentées comme un effet causal (cf. garde-fous rapport 27 §9).

1. Descriptive intra-produit, à calendrier comparable (contrôle jour de
   semaine).
2. Panel à effets fixes produit (estimateur "within", équivalent à des
   indicatrices produit sans construire la matrice complète — plus rapide,
   même résultat), + jour de semaine + catégorie×mois + stock décalé,
   erreurs regroupées ("clusterisées") par produit.
3. Hiérarchique / pooling catégorie : effet produit reculé (« shrinkage »)
   vers l'effet catégorie selon le volume d'observations disponible.
4. Challenger ML (LightGBM) — remise en variable de scénario, validation
   temporelle, jamais interprété comme un effet causal.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


# =============================================================================
# 1. Descriptive intra-produit, à calendrier comparable (contrôle jour de semaine)
# =============================================================================
def method_descriptive_intra_produit(panel: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for uid, g in panel.groupby("unique_id"):
        hors_promo = g[g["en_promotion"] == False]  # noqa: E712
        if hors_promo.empty:
            continue
        dow_mean = hors_promo.groupby("jour_semaine")["quantite_vendue"].mean()
        g = g.copy()
        g["y_attendu_calendrier"] = g["jour_semaine"].map(dow_mean)
        g["y_residuel"] = g["quantite_vendue"] - g["y_attendu_calendrier"]
        for level, gl in g[g["en_promotion"] == True].groupby("remise_planifiee_pct"):  # noqa: E712
            if len(gl) < 5:
                continue
            rows.append({
                "unique_id": uid, "remise_pct": float(level), "n_jours": len(gl),
                "uplift_residuel_moyen": float(gl["y_residuel"].mean()),
                "y_moyen_promo": float(gl["quantite_vendue"].mean()),
                "y_moyen_hors_promo_calendrier_ajuste": float(gl["y_attendu_calendrier"].mean()),
            })
    return pd.DataFrame(rows)


# =============================================================================
# 2. Panel à effets fixes produit (estimateur within) + clusters produit
# =============================================================================
def method_panel_fe(panel: pd.DataFrame, min_obs_per_product: int = 10) -> dict:
    import statsmodels.api as sm

    df = panel.copy()
    counts = df.groupby("unique_id").size()
    keep = counts[counts >= min_obs_per_product].index
    df = df[df["unique_id"].isin(keep)].copy()

    dow_dummies = pd.get_dummies(df["jour_semaine"], prefix="dow", drop_first=True)
    cat_mois_dummies = pd.get_dummies(df["categorie"].astype(str) + "_" + df["mois"].astype(str), prefix="catmois", drop_first=True)
    stock = df["stock_disponible_lag1"].fillna(df["stock_disponible_lag1"].median())

    X = pd.concat([
        df[["remise_planifiee_pct"]].rename(columns={"remise_planifiee_pct": "remise"}),
        dow_dummies.astype(float), cat_mois_dummies.astype(float),
        stock.rename("stock_lag1").astype(float),
    ], axis=1)
    y = df["log1p_y"]

    # Estimateur "within" : démoyennage par produit (équivalent aux indicatrices
    # produit, sans construire ~300 colonnes supplémentaires). Jointure explicite
    # (map/loc) plutôt que .groupby().transform() : évite le chemin interne
    # reindex/take_nd de pandas, plus gourmand en pics mémoire sur ce dataset.
    group = df["unique_id"]
    group_means_x = X.groupby(group).mean()
    group_means_y = y.groupby(group).mean()
    aligned_means_x = group_means_x.loc[group.to_numpy()].set_axis(X.index)
    aligned_means_y = group_means_y.loc[group.to_numpy()].set_axis(y.index)
    X_within = X - aligned_means_x
    y_within = y - aligned_means_y

    X_within = sm.add_constant(X_within, has_constant="add")
    model = sm.OLS(y_within, X_within)
    fit = model.fit(cov_type="cluster", cov_kwds={"groups": group})

    coef = fit.params.get("remise", float("nan"))
    se = fit.bse.get("remise", float("nan"))
    pval = fit.pvalues.get("remise", float("nan"))
    return {
        "coef_remise_log1p_par_point_pct": float(coef),
        "se_clusterisee_produit": float(se),
        "p_value": float(pval),
        "ic95_bas": float(coef - 1.96 * se),
        "ic95_haut": float(coef + 1.96 * se),
        "n_observations": int(len(df)),
        "n_produits": int(df["unique_id"].nunique()),
        "r2_within": float(fit.rsquared),
        "interpretation": (
            f"+1 point de remise est associé à une variation de {coef:+.5f} en log1p(quantité) "
            f"(soit environ {100*(np.exp(coef)-1):+.3f} % par point de remise, à calendrier et produit "
            "comparables) — ASSOCIATION, pas un effet causal prouvé."
        ),
    }


# =============================================================================
# 3. Hiérarchique / pooling catégorie (shrinkage vers l'effet catégorie)
# =============================================================================
def method_hierarchical_pooling(panel: pd.DataFrame, shrinkage_k: float = 30.0) -> pd.DataFrame:
    """Effet = log(y_moyen_promo) - log(y_moyen_hors_promo), par produit et par
    catégorie ; l'effet produit est reculé vers l'effet catégorie avec un
    poids n_i/(n_i+k) — k=30 documenté comme hypothèse explicite (mi-poids à
    30 jours de promotion observés)."""
    def _log_uplift(g: pd.DataFrame) -> float:
        promo_mean = g.loc[g["en_promotion"] == True, "quantite_vendue"].mean()  # noqa: E712
        hp_mean = g.loc[g["en_promotion"] == False, "quantite_vendue"].mean()  # noqa: E712
        if pd.isna(promo_mean) or pd.isna(hp_mean) or hp_mean <= 0 or promo_mean <= 0:
            return float("nan")
        return float(np.log(promo_mean) - np.log(hp_mean))

    prod_stats = panel.groupby("unique_id").apply(
        lambda g: pd.Series({"effet_produit": _log_uplift(g), "n_jours_promo": int((g["en_promotion"] == True).sum()),
                              "categorie": g["categorie"].iloc[0]}),
        include_groups=False,
    )
    cat_effect = panel.groupby("categorie").apply(_log_uplift, include_groups=False).rename("effet_categorie")
    prod_stats = prod_stats.join(cat_effect, on="categorie")

    prod_stats["effet_produit"] = prod_stats["effet_produit"].astype(float)
    prod_stats["n_jours_promo"] = prod_stats["n_jours_promo"].astype(float)
    prod_stats["poids_individuel"] = prod_stats["n_jours_promo"] / (prod_stats["n_jours_promo"] + shrinkage_k)
    prod_stats["effet_produit_rempli"] = prod_stats["effet_produit"].fillna(prod_stats["effet_categorie"])
    prod_stats["effet_shrinkage"] = (
        prod_stats["poids_individuel"] * prod_stats["effet_produit_rempli"]
        + (1 - prod_stats["poids_individuel"]) * prod_stats["effet_categorie"]
    )
    return prod_stats.reset_index().rename(columns={"index": "unique_id"})


# =============================================================================
# 4. Challenger ML (LightGBM) — scénario, jamais causal
# =============================================================================
def method_ml_challenger_fit(train: pd.DataFrame):
    import lightgbm as lgb

    feat_cols = ["remise_planifiee_pct", "jour_semaine", "mois", "categorie", "marque", "stock_disponible_lag1", "unique_id"]
    cat_cols = ["categorie", "marque", "unique_id"]
    X = train[feat_cols].copy()
    for c in cat_cols:
        X[c] = X[c].astype("category")
    y = train["quantite_vendue"].astype(float)
    model = lgb.LGBMRegressor(
        objective="tweedie", tweedie_variance_power=1.2, learning_rate=0.05, num_leaves=31,
        min_data_in_leaf=30, n_estimators=300, verbosity=-1, random_state=42,
    )
    model.fit(X, y, categorical_feature=cat_cols)
    return model, feat_cols, cat_cols


def method_ml_challenger_predict(model, feat_cols, cat_cols, frame: pd.DataFrame) -> np.ndarray:
    X = frame[feat_cols].copy()
    for c in cat_cols:
        X[c] = X[c].astype("category")
    return np.clip(model.predict(X), 0, None)
