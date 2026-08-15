"""Politiques de référence simples — jamais des optimisations, des règles
descriptives auxquelles toute méthode plus complexe doit se comparer
favorablement hors période (cf. rapport 27 §8, règle déjà actée).
"""

from __future__ import annotations

import pandas as pd


def baseline_aucune_remise(products: list[str]) -> pd.Series:
    return pd.Series(0.0, index=products, name="remise_aucune_remise")


def baseline_remise_frequente_produit(panel: pd.DataFrame) -> pd.Series:
    """Remise la plus fréquente par produit, sur TOUS les jours (0 % inclus) —
    reflète ce que le produit a réellement le plus souvent porté comme prix."""
    return panel.groupby("unique_id")["remise_planifiee_pct"].agg(lambda s: s.mode().iloc[0]).rename("remise_frequente_produit")


def baseline_remise_frequente_categorie(panel: pd.DataFrame) -> pd.Series:
    cat_mode = panel.groupby("categorie")["remise_planifiee_pct"].agg(lambda s: s.mode().iloc[0])
    cat_by_product = panel.groupby("unique_id")["categorie"].first().map(cat_mode)
    return cat_by_product.rename("remise_frequente_categorie")


def baseline_meilleure_remise_descriptive(panel: pd.DataFrame, min_support: int = 20) -> pd.DataFrame:
    """Meilleure remise HISTORIQUE au sens de la quantité moyenne observée —
    purement descriptif (constat rétrospectif), jamais qualifié d'optimal :
    aucune garantie que ce niveau reste le meilleur hors période ou pour un
    autre produit."""
    rows = []
    for uid, g in panel.groupby("unique_id"):
        levels = g.groupby("remise_planifiee_pct").agg(
            n=("quantite_vendue", "size"), y_moyen=("quantite_vendue", "mean"),
        )
        levels = levels[levels["n"] >= min_support]
        if levels.empty:
            rows.append({"unique_id": uid, "remise_meilleure_descriptive": 0.0, "y_moyen_historique": pd.NA, "support": 0})
            continue
        best = levels["y_moyen"].idxmax()
        rows.append({
            "unique_id": uid, "remise_meilleure_descriptive": float(best),
            "y_moyen_historique": float(levels.loc[best, "y_moyen"]), "support": int(levels.loc[best, "n"]),
        })
    return pd.DataFrame(rows).set_index("unique_id")


def politique_historique_observee(panel: pd.DataFrame) -> pd.DataFrame:
    """La politique réellement appliquée jour par jour — série complète, pas
    une constante par produit. Sert de statu quo dans la validation
    temporelle (point 7) et dans la comparaison du simulateur (point 11)."""
    return panel[["unique_id", "ds", "remise_planifiee_pct", "quantite_vendue",
                  "chiffre_affaires_net_xof", "marge_totale_xof"]].copy()


def build_all_baselines(panel: pd.DataFrame) -> pd.DataFrame:
    products = sorted(panel["unique_id"].unique())
    aucune = baseline_aucune_remise(products)
    freq_prod = baseline_remise_frequente_produit(panel)
    freq_cat = baseline_remise_frequente_categorie(panel)
    meilleure = baseline_meilleure_remise_descriptive(panel)
    out = pd.DataFrame({"remise_aucune_remise": aucune}).join(
        freq_prod, how="left"
    ).join(freq_cat, how="left").join(meilleure, how="left")
    return out.reset_index().rename(columns={"index": "unique_id"})
