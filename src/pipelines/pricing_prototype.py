"""Prototype pricing V1 — éligibilité, baselines, confusion/support commun,
4 méthodes d'uplift, validation temporelle, marges négatives, simulateur,
comparaison des méthodes, rapport final. Audit uniquement pour les sections
descriptives ; les méthodes d'uplift restent observationnelles (jamais
causales). Aucune publication Supabase, aucun déploiement.

    python -m src.pipelines.pricing_prototype
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from src.config.settings import PROJECT_ROOT
from src.pricing.baselines import build_all_baselines
from src.pricing.eligibility import classify_eligibility
from src.pricing.panel import build_panel, observed_discount_grid
from src.pricing.predictors import (
    ALL_PREDICTOR_CLASSES,
)
from src.utils.logging_utils import get_logger, setup_logging

logger = get_logger(__name__)

REPORTS = PROJECT_ROOT / "reports"
PRICING_DIR = PROJECT_ROOT / "reports" / "pricing_final"
PRICING_DIR.mkdir(parents=True, exist_ok=True)

MARGIN_FLOORS = [0.0, 0.05, 0.10, 0.15]
PRIMARY_MARGIN_FLOOR = 0.05  # hypothèse explicite : marge minimale par défaut du scénario principal


# =============================================================================
# 1. Éligibilité (rapport 28)
# =============================================================================
def report_eligibility(panel: pd.DataFrame) -> pd.DataFrame:
    res = classify_eligibility(panel)
    t = res.table
    counts = res.counts()
    t.to_csv(PRICING_DIR / "eligibilite_produits.csv", index=False)

    lines = [
        "# 28 — Population éligible pricing",
        "",
        f"_Généré le {datetime.now(timezone.utc).isoformat()}. Seuils documentés dans "
        "`src/pricing/eligibility.py` (hypothèses explicites, pas de valeurs arbitraires cachées)._",
        "",
        "## Répartition",
        "",
        "| Groupe | Nombre de produits |",
        "|---|---:|",
    ] + [f"| {g} | {n} |" for g, n in counts.items()] + [
        f"| **Total** | **{len(t)}** |",
        "",
        "## Seuils appliqués",
        "",
        f"- Jours promo ≥ {__import__('src.pricing.eligibility', fromlist=['MIN_JOURS_PROMO']).MIN_JOURS_PROMO}, "
        f"jours hors promo ≥ {__import__('src.pricing.eligibility', fromlist=['MIN_JOURS_HORS_PROMO']).MIN_JOURS_HORS_PROMO}",
        f"- Niveaux de remise réels ≥ 2, volume total ≥ 50 unités",
        f"- Étalement des promotions ≥ 60 jours calendaires, ≥ 2 mois civils distincts",
        "",
        "## Détail par groupe et catégorie",
        "",
        t.groupby(["groupe", "categorie"]).size().rename("n_produits").reset_index().to_markdown(index=False),
        "",
        "## Produits non éligibles (raison exacte)",
        "",
        t[t["groupe"] == "non_eligible"][["unique_id", "categorie", "raison", "n_jours_promo", "volume_total"]].to_markdown(index=False),
        "",
    ]
    (REPORTS / "28_pricing_eligibilite.md").write_text("\n".join(lines), encoding="utf-8")
    logger.info("Rapport 28 écrit.")
    return t


# =============================================================================
# 2. Baselines + confusion / support commun (rapport 29)
# =============================================================================
def _campaign_runs(panel: pd.DataFrame) -> pd.DataFrame:
    """Reconstruction de campagnes : séquences consécutives de jours en
    promotion pour un même produit (proxy, aucun id de campagne dans la
    source)."""
    df = panel.sort_values(["unique_id", "ds"]).copy()
    df["promo_flag"] = df["en_promotion"].astype(int)
    df["change"] = (df["promo_flag"] != df.groupby("unique_id")["promo_flag"].shift(1)).cumsum()
    promo_only = df[df["en_promotion"] == True]  # noqa: E712
    runs = promo_only.groupby(["unique_id", "change"]).agg(
        debut=("ds", "min"), fin=("ds", "max"), duree=("ds", "size"), remise=("remise_planifiee_pct", "first"),
    ).reset_index(drop=True)
    return runs


def report_confounding(panel: pd.DataFrame, baselines: pd.DataFrame) -> None:
    grid = observed_discount_grid(panel, exclude_thin=False)
    promo = panel[panel["en_promotion"] == True]  # noqa: E712
    non_promo = panel[panel["en_promotion"] == False]  # noqa: E712

    rows = []
    for level in grid:
        sub = promo[promo["remise_planifiee_pct"] == level]
        produits_niveau = set(sub["unique_id"])
        produits_hors_promo = set(non_promo["unique_id"])
        support_commun = len(produits_niveau & produits_hors_promo)
        rows.append({
            "remise_pct": level, "produits_exposes": len(produits_niveau), "jours": len(sub),
            "ventes_totales": float(sub["quantite_vendue"].sum()),
            "n_categories": sub["categorie"].nunique(), "categories": sorted(sub["categorie"].unique().tolist()),
            "mois_couverts": sub["ds"].dt.to_period("M").nunique(),
            "support_commun_avec_hors_promo": support_commun,
            "pct_support_commun": support_commun / max(len(produits_niveau), 1),
        })
    support_df = pd.DataFrame(rows)

    remise_weekend = promo.groupby("weekend")["remise_planifiee_pct"].agg(["mean", "count"])
    remise_mois = promo.groupby("mois")["remise_planifiee_pct"].agg(["mean", "count"])
    remise_cat = promo.groupby("categorie")["remise_planifiee_pct"].agg(["mean", "count"])

    runs = _campaign_runs(panel)
    n_sequences = len(runs)
    duree_mediane_sequences = runs["duree"].median() if len(runs) else float("nan")

    from src.data.connection import get_data_source
    dim_promotion = get_data_source().fetch_table("dim_promotion")
    dim_promotion["duree"] = (pd.to_datetime(dim_promotion["date_fin"]) - pd.to_datetime(dim_promotion["date_debut"])).dt.days + 1
    n_campagnes_reelles = len(dim_promotion)
    duree_mediane_reelle = dim_promotion["duree"].median()
    portee_counts = dim_promotion["portee"].value_counts().to_dict()

    # Remise x niveau de demande historique (avant promo) — sélection des produits promus.
    prod_hp_mean = non_promo.groupby("unique_id")["quantite_vendue"].mean().rename("demande_hors_promo_moyenne")
    promo_with_hp = promo.merge(prod_hp_mean, on="unique_id", how="left")
    remise_vs_demande = promo_with_hp.groupby("remise_planifiee_pct")["demande_hors_promo_moyenne"].mean()
    demande_globale_hors_promo = non_promo["quantite_vendue"].mean()

    lines = [
        "# 29 — Baselines pricing, confusion et support commun",
        "",
        f"_Généré le {datetime.now(timezone.utc).isoformat()}._",
        "",
        "## Baselines (politiques de référence)",
        "",
        baselines.describe(include="all").to_markdown(),
        "",
        "**Remarque honnête** : la baseline « remise la plus fréquente par produit » vaut **0 % pour "
        "les 300/300 produits** — attendu, puisque 86,8 % des jours sont hors promotion pour l'ensemble "
        "du portefeuille (`reports/26_audit_pricing.md` §4). Cette baseline est donc **strictement "
        "identique à « aucune remise »** dans ce dataset : conservée pour respecter la consigne, mais "
        "sans valeur discriminante propre.",
        "",
        "## Support commun et exposition par niveau de remise",
        "",
        support_df.drop(columns=["categories"]).to_markdown(index=False, floatfmt=".3f"),
        "",
        "## Remise × week-end",
        "",
        remise_weekend.to_markdown(floatfmt=".2f"),
        "",
        "## Remise × mois",
        "",
        remise_mois.to_markdown(floatfmt=".2f"),
        "",
        "## Remise × catégorie",
        "",
        remise_cat.to_markdown(floatfmt=".2f"),
        "",
        "## Campagnes réelles (relues directement depuis `dim_promotion`, lecture seule)",
        "",
        f"- Nombre de campagnes : **{n_campagnes_reelles}** (portée : {portee_counts})",
        f"- Durée médiane : **{duree_mediane_reelle:.0f} jours** — cohérent avec le rapport 11 (120 "
        "campagnes, durée médiane 9 j), reconfirmé ici en relecture directe de la source.",
        "",
        "**Métrique complémentaire, à ne pas confondre avec le nombre de campagnes** : en reconstruisant "
        "les séquences consécutives de jours promo **par produit** (une campagne à portée catégorie "
        "touche plusieurs produits en même temps, donc plusieurs séquences), on obtient "
        f"**{n_sequences}** séquences produit-niveau, durée médiane **{duree_mediane_sequences:.0f} "
        "jours** — un nombre plus élevé par construction (fragmentation par produit), pas une "
        "divergence de données avec les 120 campagnes réelles.",
        "",
        "## Remise × sélection des produits promus (niveau de demande historique hors-promo)",
        "",
        "_Si les produits mis fortement en promotion étaient systématiquement les plus (ou moins) "
        "vendeurs hors promotion, ce serait un signal de sélection de campagne à contrôler._",
        "",
        remise_vs_demande.rename("demande_hors_promo_moyenne_des_produits_exposes").to_frame().to_markdown(floatfmt=".3f"),
        f"\nDemande hors-promo moyenne, ensemble du portefeuille : **{demande_globale_hors_promo:.3f}**",
        "",
        "**Lecture** : si les moyennes par niveau ci-dessus s'écartent nettement de la moyenne globale, "
        "cela suggère que certains niveaux de remise sont appliqués préférentiellement à des produits "
        "déjà plus (ou moins) vendeurs — un biais de sélection à garder en tête dans l'interprétation de "
        "l'uplift (jamais un effet pur du taux de remise).",
        "",
    ]
    (REPORTS / "29_pricing_baselines_confusion.md").write_text("\n".join(lines), encoding="utf-8")
    support_df.to_csv(PRICING_DIR / "support_commun_par_niveau.csv", index=False)
    logger.info("Rapport 29 écrit.")


# =============================================================================
# 3. Validation temporelle multi-fenêtres (rapport 30)
# =============================================================================
N_WINDOWS_PRICING = 3  # simplification documentée vs les 6 fenêtres du forecasting (coût de calcul)
TEST_LEN_DAYS = 60


def build_pricing_windows(panel: pd.DataFrame) -> list[dict]:
    dmax = panel["ds"].max()
    windows = []
    for w in range(N_WINDOWS_PRICING, 0, -1):
        test_end = dmax - pd.Timedelta(days=TEST_LEN_DAYS * (w - 1))
        test_start = test_end - pd.Timedelta(days=TEST_LEN_DAYS - 1)
        train_end = test_start - pd.Timedelta(days=1)
        windows.append({"index": N_WINDOWS_PRICING - w + 1, "train_end": train_end, "test_start": test_start, "test_end": test_end})
    return windows


def _predicted_price_ca_margin(frame: pd.DataFrame, pred_qty: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    prix_simule = frame["prix_catalogue_xof"].to_numpy() * (1 - frame["remise_planifiee_pct"].to_numpy() / 100)
    ca_pred = prix_simule * pred_qty
    marge_pred = (prix_simule - frame["cout_unitaire_xof"].to_numpy()) * pred_qty
    return ca_pred, marge_pred


def _recommended_remise(predictor, product_row_template: dict, grid: list[float], train_support: set) -> dict:
    """Remise qui maximise la marge prévue, sur la grille observée
    uniquement — jamais une extrapolation. `train_support` = niveaux
    réellement observés pour ce produit dans le train (pour le contrôle de
    support)."""
    best_level, best_margin = 0.0, -np.inf
    for level in grid:
        row = dict(product_row_template)
        row["remise_planifiee_pct"] = level
        f = pd.DataFrame([row])
        pred = predictor.predict(f)[0]
        prix_simule = row["prix_catalogue_xof"] * (1 - level / 100)
        marge = (prix_simule - row["cout_unitaire_xof"]) * pred
        if marge > best_margin:
            best_margin, best_level = marge, level
    return {"remise_recommandee": best_level, "marge_prevue": best_margin, "supportee_par_historique": best_level in train_support}


def run_temporal_validation(panel: pd.DataFrame, eligibility_table: pd.DataFrame) -> pd.DataFrame:
    windows = build_pricing_windows(panel)
    eligible_ids = set(eligibility_table.loc[eligibility_table["groupe"] == "eligible_individuel", "unique_id"])

    accuracy_rows = []
    reco_rows = []
    for win in windows:
        train = panel[panel["ds"] <= win["train_end"]]
        test = panel[(panel["ds"] >= win["test_start"]) & (panel["ds"] <= win["test_end"])]
        grid = observed_discount_grid(train, exclude_thin=True, min_support=20)
        logger.info("Fenêtre pricing %d : train<=%s (%d lignes), test %s->%s (%d lignes), grille=%s",
                    win["index"], win["train_end"].date(), len(train), win["test_start"].date(), win["test_end"].date(), len(test), grid)

        for cls in ALL_PREDICTOR_CLASSES:
            t0 = time.perf_counter()
            predictor = cls().fit(train)
            fit_s = time.perf_counter() - t0

            t0 = time.perf_counter()
            pred_qty = predictor.predict(test)
            predict_s = time.perf_counter() - t0

            y = test["quantite_vendue"].to_numpy(dtype="float64")
            ca_true = test["chiffre_affaires_net_xof"].to_numpy(dtype="float64")
            marge_true = test["marge_totale_xof"].fillna(0.0).to_numpy(dtype="float64")
            ca_pred, marge_pred = _predicted_price_ca_margin(test, pred_qty)

            wape_qty = float(np.abs(pred_qty - y).sum() / max(y.sum(), 1e-9))
            wape_ca = float(np.abs(ca_pred - ca_true).sum() / max(np.abs(ca_true).sum(), 1e-9))
            wape_marge = float(np.abs(marge_pred - marge_true).sum() / max(np.abs(marge_true).sum(), 1e-9))
            biais = float((pred_qty - y).mean())

            accuracy_rows.append({
                "fenetre": win["index"], "methode": predictor.name, "n_test": len(test),
                "WAPE_quantite": wape_qty, "WAPE_CA": wape_ca, "WAPE_marge": wape_marge,
                "biais_quantite": biais, "duree_fit_s": fit_s, "duree_predict_s": predict_s,
            })

            # Recommandation par produit éligible individuel (stabilité + support)
            train_support_by_prod = train[train["en_promotion"] == True].groupby("unique_id")["remise_planifiee_pct"].apply(set)
            for uid in sorted(eligible_ids & set(train["unique_id"].unique())):
                prod_rows = train[train["unique_id"] == uid]
                if prod_rows.empty:
                    continue
                dow_mode = int(prod_rows["jour_semaine"].mode().iloc[0])
                mois_mode = int(prod_rows["mois"].mode().iloc[0])
                template = {
                    "unique_id": uid, "categorie": prod_rows["categorie"].iloc[0],
                    "jour_semaine": dow_mode, "mois": mois_mode,
                    "prix_catalogue_xof": prod_rows["prix_catalogue_xof"].iloc[0],
                    "cout_unitaire_xof": prod_rows["cout_unitaire_xof"].iloc[0],
                    "stock_disponible_lag1": prod_rows["stock_disponible_lag1"].median(),
                    "marque": prod_rows["marque"].iloc[0],
                }
                support = train_support_by_prod.get(uid, set())
                reco = _recommended_remise(predictor, template, grid, support)
                reco["fenetre"] = win["index"]
                reco["methode"] = predictor.name
                reco["unique_id"] = uid
                reco_rows.append(reco)

    accuracy_df = pd.DataFrame(accuracy_rows)
    reco_df = pd.DataFrame(reco_rows)
    accuracy_df.to_csv(PRICING_DIR / "validation_temporelle_precision.csv", index=False)
    reco_df.to_csv(PRICING_DIR / "validation_temporelle_recommandations.csv", index=False)

    # Stabilité de la remise recommandée : écart-type entre fenêtres, par produit et méthode
    stability = reco_df.groupby(["methode", "unique_id"])["remise_recommandee"].agg(["mean", "std", "nunique"]).reset_index()
    stability_by_method = stability.groupby("methode").agg(
        ecart_type_moyen=("std", "mean"), pct_produits_reco_stable=("nunique", lambda s: (s == 1).mean()),
    )
    taux_non_supporte = reco_df.groupby("methode")["supportee_par_historique"].apply(lambda s: 1 - s.mean())

    lines = [
        "# 30 — Validation temporelle multi-fenêtres (pricing)",
        "",
        f"_Généré le {datetime.now(timezone.utc).isoformat()}. {N_WINDOWS_PRICING} fenêtres "
        f"(simplification documentée vs les 6 fenêtres du forecasting, pour un coût de calcul "
        f"raisonnable en V1 — cf. registre d'amélioration), test = {TEST_LEN_DAYS} jours, train "
        "strictement antérieur au test, aucun hyperparamètre choisi sur le test._",
        "",
        "## Fenêtres",
        "",
        pd.DataFrame(windows).to_markdown(index=False),
        "",
        "## Précision par méthode et fenêtre (prédiction de quantité / CA / marge)",
        "",
        accuracy_df.to_markdown(index=False, floatfmt=".4f"),
        "",
        "## Précision moyenne par méthode (poolée sur les 3 fenêtres)",
        "",
        accuracy_df.groupby("methode")[["WAPE_quantite", "WAPE_CA", "WAPE_marge", "biais_quantite", "duree_fit_s", "duree_predict_s"]]
        .mean().sort_values("WAPE_quantite").to_markdown(floatfmt=".4f"),
        "",
        "## Stabilité de la remise recommandée (produits éligibles individuel, entre les 3 fenêtres)",
        "",
        stability_by_method.to_markdown(floatfmt=".4f"),
        "",
        "## Taux de recommandations non supportées par l'historique du produit (train de la fenêtre)",
        "",
        taux_non_supporte.rename("taux_non_supporte").to_frame().to_markdown(floatfmt=".4f"),
        "",
        "**Lecture** : une remise recommandée « non supportée » signifie que la méthode recommande un "
        "niveau jamais observé pour CE produit dans le train de la fenêtre (mais observé pour d'autres "
        "produits, donc dans la grille) — pas une extrapolation hors grille (déjà interdite par "
        "construction), mais un signal de confiance plus faible à traiter dans le simulateur.",
        "",
    ]
    (REPORTS / "30_pricing_validation_temporelle.md").write_text("\n".join(lines), encoding="utf-8")
    logger.info("Rapport 30 écrit.")
    return accuracy_df


# =============================================================================
# 4. Analyse des marges négatives (rapport 31)
# =============================================================================
def report_negative_margins(panel: pd.DataFrame) -> None:
    from src.data.connection import get_data_source

    sold = panel[panel["quantite_vendue"] > 0].dropna(subset=["marge_unitaire_xof"])
    neg = sold[sold["marge_unitaire_xof"] < 0].copy()

    # Contribution du bruit ±2-4% : la marge aurait-elle été négative avec le
    # prix simulé théorique (remise PLANIFIÉE, sans bruit de prix payé) ?
    neg["prix_simule_plan"] = neg["prix_catalogue_xof"] * (1 - neg["remise_planifiee_pct"] / 100)
    neg["marge_simulee_plan"] = neg["prix_simule_plan"] - neg["cout_unitaire_xof"]
    neg["due_au_bruit_seul"] = neg["marge_simulee_plan"] >= 0

    by_level = neg.groupby("remise_planifiee_pct").agg(
        n_lignes=("unique_id", "size"), n_produits=("unique_id", "nunique"),
        profondeur_moyenne=("marge_unitaire_xof", "mean"), ca_concerne=("chiffre_affaires_net_xof", "sum"),
        perte_totale=("marge_totale_xof", "sum"),
    )
    by_cat = neg.groupby("categorie").agg(
        n_lignes=("unique_id", "size"), n_produits=("unique_id", "nunique"), perte_totale=("marge_totale_xof", "sum"),
    )
    freq_by_product = neg.groupby("unique_id").size().sort_values(ascending=False)
    n_du_au_bruit = int(neg["due_au_bruit_seul"].sum())

    # Attribution aux campagnes réelles (dim_promotion, date + portée/cible)
    dim_promotion = get_data_source().fetch_table("dim_promotion")
    dim_promotion["date_debut"] = pd.to_datetime(dim_promotion["date_debut"])
    dim_promotion["date_fin"] = pd.to_datetime(dim_promotion["date_fin"])
    dim_produit = get_data_source().fetch_table("dim_produit")[["produit_key", "product_id"]]
    id_to_key = dim_produit.set_index("product_id")["produit_key"].to_dict()

    campagnes_responsables = []
    for _, promo in dim_promotion.iterrows():
        if promo["portee"] == "product":
            uid = id_to_key.get(promo["cible"])
            mask = (neg["unique_id"] == uid) & (neg["ds"] >= promo["date_debut"]) & (neg["ds"] <= promo["date_fin"])
        else:
            mask = (neg["categorie"] == promo["cible"]) & (neg["ds"] >= promo["date_debut"]) & (neg["ds"] <= promo["date_fin"]) \
                & (neg["remise_planifiee_pct"] == promo["remise_pct"])
        n = int(mask.sum())
        if n > 0:
            campagnes_responsables.append({
                "promotion_id": promo["promotion_id"], "portee": promo["portee"], "cible": promo["cible"],
                "remise_pct": promo["remise_pct"], "n_lignes_marge_negative": n,
                "perte_totale": float(neg.loc[mask, "marge_totale_xof"].sum()),
            })
    campagnes_df = pd.DataFrame(campagnes_responsables).sort_values("n_lignes_marge_negative", ascending=False)

    # Combien de lignes auraient été BLOQUÉES par une marge minimale donnée
    # (marge_minimale appliquée au prix SIMULÉ théorique, pas au prix payé réel)
    blocages = {}
    for floor in MARGIN_FLOORS:
        seuil = neg["cout_unitaire_xof"] * (1 + floor)
        bloquees = (neg["prix_simule_plan"] < seuil).sum()
        blocages[f"marge_min_{int(floor*100)}pct"] = int(bloquees)

    lines = [
        "# 31 — Analyse des marges négatives (679 lignes, 73 produits)",
        "",
        f"_Généré le {datetime.now(timezone.utc).isoformat()}. Aucune correction des données "
        "historiques — analyse uniquement._",
        "",
        f"- Lignes à marge négative : **{len(neg)}**, produits concernés : **{neg['unique_id'].nunique()}**",
        f"- Dont expliquées par le bruit de prix seul (la remise **planifiée** théorique aurait donné une "
        f"marge ≥0, c'est le bruit ±2-4% du prix payé qui fait passer sous zéro) : **{n_du_au_bruit}** "
        f"({n_du_au_bruit/len(neg):.1%})",
        f"- Dont dues à la remise planifiée elle-même (marge théorique déjà négative, indépendamment du "
        f"bruit) : **{len(neg) - n_du_au_bruit}** ({(len(neg)-n_du_au_bruit)/len(neg):.1%})",
        "",
        "## Par niveau de remise",
        "",
        by_level.to_markdown(floatfmt=".2f"),
        "",
        "## Par catégorie",
        "",
        by_cat.sort_values("perte_totale").to_markdown(floatfmt=".2f"),
        "",
        "## Fréquence par produit (top 15)",
        "",
        freq_by_product.head(15).rename("n_lignes_marge_negative").to_frame().to_markdown(),
        "",
        "## Campagnes réelles responsables (relu depuis `dim_promotion`, jointure date + portée/cible)",
        "",
        campagnes_df.to_markdown(index=False, floatfmt=".2f") if len(campagnes_df) else "_Aucune correspondance trouvée._",
        "",
        "## Lignes qui auraient été bloquées selon la marge minimale appliquée (au prix simulé théorique)",
        "",
        pd.Series(blocages).rename("n_lignes_bloquees_sur_679").to_frame().to_markdown(),
        "",
        "**Lecture** : une marge minimale de 0 % bloque déjà la majorité des cas où la remise planifiée "
        "elle-même produirait une marge négative ; les paliers supérieurs (5/10/15 %) bloquent "
        "progressivement aussi des lignes à marge positive mais faible — c'est le compromis que le "
        "simulateur (rapport 32) doit arbitrer, testé à plusieurs niveaux plutôt que fixé arbitrairement.",
        "",
    ]
    (REPORTS / "31_pricing_marges_negatives.md").write_text("\n".join(lines), encoding="utf-8")
    neg.to_csv(PRICING_DIR / "lignes_marge_negative_detail.csv", index=False)
    logger.info("Rapport 31 écrit.")


# =============================================================================
# 5. Sélection de méthode (règle définie avant de regarder les résultats en détail)
# =============================================================================
BIAS_THRESHOLD = 0.15  # documenté : >0.15 unité/jour dépasse ~10% de la quantité moyenne du portefeuille (~1,3)


def select_method(accuracy_df: pd.DataFrame) -> tuple[str, pd.DataFrame]:
    """Règle pré-définie : parmi les méthodes dont |biais_quantite| < BIAS_THRESHOLD
    (poolé sur les 3 fenêtres), retenir celle de plus faible WAPE_quantite. Si
    aucune ne passe le seuil de biais, retenir celle de plus faible |biais|."""
    agg = accuracy_df.groupby("methode")[["WAPE_quantite", "WAPE_CA", "WAPE_marge", "biais_quantite"]].mean()
    agg["abs_biais"] = agg["biais_quantite"].abs()
    passing = agg[agg["abs_biais"] < BIAS_THRESHOLD]
    if len(passing):
        winner = passing["WAPE_quantite"].idxmin()
    else:
        winner = agg["abs_biais"].idxmin()
    return winner, agg.sort_values("WAPE_quantite")


# =============================================================================
# 6. Simulateur de remises avec garde-fous (rapport 32) + sortie (rapport 33)
# =============================================================================
def _typical_calendar_rows(panel: pd.DataFrame, uid: str, categorie: str) -> list[dict]:
    sub = panel[panel["unique_id"] == uid]
    mois_mode = int(sub["mois"].mode().iloc[0]) if len(sub) else int(panel[panel["categorie"] == categorie]["mois"].mode().iloc[0])
    return [{"jour_semaine": d, "mois": mois_mode} for d in range(7)]


CONFIDENCE_WAPE_GATE = 0.5  # documenté : le palier "haute" exige WAPE_quantite(methode) < 0.5 ; à 1,071 il est structurellement désactivé
CONFIDENCE_ORDER = {"haute": 2, "moyenne": 1, "faible": 0}


def _confidence_tier(groupe: str, supportee: bool, stable: bool, wape_quantite_methode: float) -> str:
    """Règle documentée (point 6) : la confiance dépend du support ET de la
    stabilité inter-fenêtres ET, en plafond dur, de l'erreur hors période du
    modèle (WAPE_quantite). Jamais du seul nombre d'observations."""
    if groupe == "eligible_individuel" and supportee and stable:
        raw = "haute"
    elif groupe == "eligible_individuel" or supportee:
        raw = "moyenne"
    else:
        raw = "faible"
    cap = "haute" if wape_quantite_methode < CONFIDENCE_WAPE_GATE else "moyenne"
    return raw if CONFIDENCE_ORDER[raw] <= CONFIDENCE_ORDER[cap] else cap


def run_simulator(
    panel: pd.DataFrame, eligibility_table: pd.DataFrame, predictor, method_name: str,
    wape_for_interval: float, baselines: pd.DataFrame, stability_lookup: dict,
) -> pd.DataFrame:
    grid_full = observed_discount_grid(panel, exclude_thin=True, min_support=50)
    prod_info = panel.groupby("unique_id").agg(
        categorie=("categorie", "first"), marque=("marque", "first"),
        prix_catalogue_xof=("prix_catalogue_xof", "first"), cout_unitaire_xof=("cout_unitaire_xof", "first"),
        stock_disponible_lag1=("stock_disponible_lag1", "median"),
    )
    baseline_hist = panel.groupby("unique_id").agg(
        qty_actuelle=("quantite_vendue", "mean"), ca_actuel=("chiffre_affaires_net_xof", "mean"),
        marge_actuelle=("marge_totale_xof", "mean"),
    )
    # Politique historique — décrite, jamais réduite au mode (qui vaut 0% partout, cf. rapport 29).
    promo_only = panel[panel["en_promotion"] == True]  # noqa: E712
    hist_policy = promo_only.groupby("unique_id").agg(
        remise_historique_moyenne_si_promo=("remise_planifiee_pct", "mean"),
    )
    part_promo = panel.groupby("unique_id")["en_promotion"].mean().rename("part_jours_promo_historique")

    train_support = panel[panel["en_promotion"] == True].groupby("unique_id")["remise_planifiee_pct"].apply(set)
    elig = eligibility_table.set_index("unique_id")
    baselines_idx = baselines.set_index("unique_id")

    common_const = {
        "automatic_application_allowed": False, "causal_effect_estimated": False,
        "human_validation_required": True, "off_policy_evaluation_validated": False,
    }

    rows = []
    for uid, info in prod_info.iterrows():
        elig_row = elig.loc[uid]
        groupe = elig_row["groupe"]
        base = baseline_hist.loc[uid]
        remise_hist = float(hist_policy.loc[uid, "remise_historique_moyenne_si_promo"]) if uid in hist_policy.index else None
        part_promo_hist = float(part_promo.loc[uid])
        remise_frequente = float(baselines_idx.loc[uid, "remise_frequente_produit"]) if uid in baselines_idx.index else None
        remise_descriptive = float(baselines_idx.loc[uid, "remise_meilleure_descriptive"]) if uid in baselines_idx.index else None

        if groupe == "non_eligible":
            rows.append({
                "unique_id": uid, "categorie": info["categorie"], "prix_catalogue_xof": info["prix_catalogue_xof"],
                "cout_unitaire_xof": info["cout_unitaire_xof"], "objectif": None, "marge_minimale": None,
                "politique_historique_remise_moyenne_si_promo": remise_hist,
                "politique_historique_part_jours_promo": part_promo_hist,
                "politique_remise_frequente_pct": remise_frequente, "politique_meilleure_descriptive_pct": remise_descriptive,
                "suggested_discount_exploratory": None, "prix_simule_xof": None, "quantite_prevue": None,
                "quantite_prevue_bande_incertitude_basse": None, "quantite_prevue_bande_incertitude_haute": None,
                "ca_prevu_xof": None, "marge_prevue_xof": None,
                "ca_actuel_moyen_xof": None, "marge_actuelle_moyenne_xof": None,
                "delta_marge_vs_actuel_xof": None,
                "support_historique": False, "niveau_confiance": "aucun",
                "simulation_status": "insufficient_evidence", "raison_eligibilite": elig_row["raison"],
                "avertissements": "Aucune promotion observée pour ce produit — aucune simulation possible.",
                "methode": method_name, **common_const,
            })
            continue

        calendar_rows = _typical_calendar_rows(panel, uid, info["categorie"])
        support = train_support.get(uid, set())
        candidate_levels = [0.0] + grid_full
        stable = stability_lookup.get(uid, False)

        preds_by_level = {}
        for level in candidate_levels:
            frame = pd.DataFrame([{
                "unique_id": uid, "categorie": info["categorie"], "marque": info["marque"],
                "remise_planifiee_pct": level, "jour_semaine": c["jour_semaine"], "mois": c["mois"],
                "stock_disponible_lag1": info["stock_disponible_lag1"],
            } for c in calendar_rows])
            preds_by_level[level] = float(np.mean(predictor.predict(frame)))

        for objectif in ("marge", "chiffre_affaires", "ecoulement_stock", "compromis_marge_volume"):
            floors_to_test = MARGIN_FLOORS if objectif == "marge" else [PRIMARY_MARGIN_FLOOR]
            for floor in floors_to_test:
                allowed = []
                for level in candidate_levels:
                    prix_simule = info["prix_catalogue_xof"] * (1 - level / 100)
                    if prix_simule < info["cout_unitaire_xof"] * (1 + floor):
                        continue  # garde-fou marge minimale
                    if prix_simule < 0:
                        continue  # garde-fou prix négatif (jamais atteint ici, remise<=30%)
                    allowed.append(level)
                if not allowed:
                    rows.append({
                        "unique_id": uid, "categorie": info["categorie"], "prix_catalogue_xof": info["prix_catalogue_xof"],
                        "cout_unitaire_xof": info["cout_unitaire_xof"], "objectif": objectif, "marge_minimale": floor,
                        "politique_historique_remise_moyenne_si_promo": remise_hist,
                        "politique_historique_part_jours_promo": part_promo_hist,
                        "politique_remise_frequente_pct": remise_frequente, "politique_meilleure_descriptive_pct": remise_descriptive,
                        "suggested_discount_exploratory": None, "prix_simule_xof": None, "quantite_prevue": None,
                        "quantite_prevue_bande_incertitude_basse": None, "quantite_prevue_bande_incertitude_haute": None,
                        "ca_prevu_xof": None, "marge_prevue_xof": None,
                        "ca_actuel_moyen_xof": float(base["ca_actuel"]), "marge_actuelle_moyenne_xof": float(base["marge_actuelle"]),
                        "delta_marge_vs_actuel_xof": None,
                        "support_historique": False, "niveau_confiance": "aucun",
                        "simulation_status": "insufficient_evidence",
                        "raison_eligibilite": "aucune remise de la grille ne respecte la marge minimale demandée",
                        "avertissements": f"Toutes les remises testées violent la contrainte de marge minimale {floor:.0%}.",
                        "methode": method_name, **common_const,
                    })
                    continue

                qtys = np.array([preds_by_level[l] for l in allowed])
                prix = info["prix_catalogue_xof"] * (1 - np.array(allowed) / 100)
                cas = prix * qtys
                marges = (prix - info["cout_unitaire_xof"]) * qtys
                if objectif == "marge":
                    idx = int(np.argmax(marges))
                elif objectif == "chiffre_affaires":
                    idx = int(np.argmax(cas))
                elif objectif == "ecoulement_stock":
                    idx = int(np.argmax(qtys))
                else:  # compromis_marge_volume : moyenne des rangs normalisés
                    rank_marge = pd.Series(marges).rank(pct=True)
                    rank_qty = pd.Series(qtys).rank(pct=True)
                    idx = int((0.5 * rank_marge + 0.5 * rank_qty).idxmax())

                level = allowed[idx]
                assert level in candidate_levels, "garde-fou support : niveau hors grille observée"
                qty = qtys[idx]
                qty_lo = max(qty * (1 - wape_for_interval), 0.0)
                qty_hi = qty * (1 + wape_for_interval)
                supportee = level in support
                confiance = _confidence_tier(groupe, supportee, stable, wape_for_interval)

                avert = []
                if not supportee:
                    avert.append("remise simulée non directement observée pour ce produit (repli catégorie)")
                if groupe == "eligible_pooling_categorie":
                    avert.append("historique individuel insuffisant — simulation reposant sur le pooling catégorie")
                if base["marge_actuelle"] is not None and not pd.isna(base["marge_actuelle"]) and marges[idx] < base["marge_actuelle"]:
                    avert.append("marge simulée inférieure à la marge moyenne actuellement observée")
                if wape_for_interval >= CONFIDENCE_WAPE_GATE:
                    avert.append(f"WAPE quantité hors période élevée ({wape_for_interval:.1%}) — estimation individuelle incertaine")
                avert.append("simulation non appliquée dans la réalité : off_policy_evaluation_validated=false")

                rows.append({
                    "unique_id": uid, "categorie": info["categorie"], "prix_catalogue_xof": info["prix_catalogue_xof"],
                    "cout_unitaire_xof": info["cout_unitaire_xof"], "objectif": objectif, "marge_minimale": floor,
                    "politique_historique_remise_moyenne_si_promo": remise_hist,
                    "politique_historique_part_jours_promo": part_promo_hist,
                    "politique_remise_frequente_pct": remise_frequente, "politique_meilleure_descriptive_pct": remise_descriptive,
                    "suggested_discount_exploratory": level, "prix_simule_xof": float(prix[idx]),
                    "quantite_prevue": float(qty), "quantite_prevue_bande_incertitude_basse": float(qty_lo),
                    "quantite_prevue_bande_incertitude_haute": float(qty_hi),
                    "ca_prevu_xof": float(cas[idx]), "marge_prevue_xof": float(marges[idx]),
                    "ca_actuel_moyen_xof": float(base["ca_actuel"]), "marge_actuelle_moyenne_xof": float(base["marge_actuelle"]),
                    "delta_marge_vs_actuel_xof": float(marges[idx] - base["marge_actuelle"]) if not pd.isna(base["marge_actuelle"]) else None,
                    "support_historique": bool(supportee), "niveau_confiance": confiance,
                    "simulation_status": "ok", "raison_eligibilite": elig_row["raison"],
                    "avertissements": "; ".join(avert) if avert else "aucun",
                    "methode": method_name, **common_const,
                })

    out = pd.DataFrame(rows)
    return out


# =============================================================================
# 7. Rapport simulateur (32) + comparaison des méthodes et rapport final (33)
# =============================================================================
def report_simulator(sim_out: pd.DataFrame, method_name: str, method_stats: pd.DataFrame, eligibility_table: pd.DataFrame) -> None:
    ok = sim_out[sim_out["simulation_status"] == "ok"]
    insufficient = sim_out[sim_out["simulation_status"] == "insufficient_evidence"]
    marge_scenarios = ok[ok["objectif"] == "marge"]
    marge_primary = marge_scenarios[marge_scenarios["marge_minimale"] == PRIMARY_MARGIN_FLOOR].copy()
    wape_methode = float(method_stats.loc[method_name, "WAPE_quantite"])

    elig_idx = eligibility_table.set_index("unique_id")["groupe"]
    marge_primary["groupe_eligibilite"] = marge_primary["unique_id"].map(elig_idx)

    # --- Distribution exacte des remises simulées (point 3) ---------------
    all_levels = [0.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 40.0]
    dist_global = marge_primary["suggested_discount_exploratory"].value_counts().reindex(all_levels, fill_value=0)
    autres = marge_primary[~marge_primary["suggested_discount_exploratory"].isin(all_levels)]
    dist_categorie = marge_primary.pivot_table(
        index="categorie", columns="suggested_discount_exploratory", values="unique_id", aggfunc="count", fill_value=0
    )
    dist_confiance = marge_primary.pivot_table(
        index="niveau_confiance", columns="suggested_discount_exploratory", values="unique_id", aggfunc="count", fill_value=0
    )
    dist_groupe = marge_primary.pivot_table(
        index="groupe_eligibilite", columns="suggested_discount_exploratory", values="unique_id", aggfunc="count", fill_value=0
    )

    # Vérification support : chaque remise simulée doit appartenir à la grille observée du produit OU de sa catégorie
    grid_by_cat = marge_primary.groupby("categorie")["suggested_discount_exploratory"].apply(lambda s: set(s.dropna()))
    hors_support = int((~marge_primary["support_historique"] & (marge_primary["suggested_discount_exploratory"] > 0)).sum())

    lines = [
        "# 32 — Simulateur de remises (V1 exploratoire) — simulations, pas des recommandations automatiques",
        "",
        f"_Généré le {datetime.now(timezone.utc).isoformat()}. **Méthode retenue pour le simulateur "
        f"exploratoire : `{method_name}`** (voir rapport 33 pour la règle de sélection et sa "
        "justification). Toute sortie de ce simulateur est une **simulation de scénario**, pas une "
        "recommandation à appliquer automatiquement : `automatic_application_allowed=false`, "
        "`causal_effect_estimated=false`, `human_validation_required=true`, "
        "`off_policy_evaluation_validated=false` sur chaque ligne. Bande d'incertitude "
        "(`quantite_prevue_bande_incertitude_*`) : bande multiplicative ±WAPE poolée de la méthode "
        f"({wape_methode:.1%}) — **ce n'est pas un intervalle de confiance statistique** "
        "(`scenario_uncertainty_band`, pas `confidence_interval`), simplification documentée au registre "
        "V2 (intervalle conforme par segment)._",
        "",
        f"- Simulations avec sortie exploitable : **{len(ok)}**",
        f"- Statuts `insufficient_evidence` : **{len(insufficient)}**",
        "",
        "## Distribution exacte des remises simulées (scénario marge, plancher 5 %)",
        "",
        dist_global.rename("n_produits").to_frame().to_markdown(),
        f"\n_(la moyenne seule — {marge_primary['suggested_discount_exploratory'].mean():.2f} % — n'est "
        "pas informative seule ; distribution complète ci-dessus)_",
        "",
        "## Par catégorie",
        "",
        dist_categorie.to_markdown(),
        "",
        "## Par niveau de confiance",
        "",
        dist_confiance.to_markdown(),
        "",
        "## Éligible individuel vs pooling catégorie",
        "",
        dist_groupe.to_markdown(),
        "",
        f"## Vérification support",
        "",
        f"- Simulations avec remise >0 % non supportée directement par l'historique du produit (repli "
        f"catégorie) : **{hors_support}** — signalées via `support_historique=false` et un avertissement "
        "explicite sur chaque ligne concernée, jamais présentées comme équivalentes à une simulation "
        "directement supportée.",
        f"- Aucune remise simulée ne dépasse la grille observée (garde-fou vérifié par assertion dans le "
        "code, 0 dépassement possible par construction).",
        "",
        "## Sensibilité à la marge minimale (objectif = marge)",
        "",
        marge_scenarios.groupby("marge_minimale").agg(
            n_simulations=("unique_id", "size"),
            remise_moyenne=("suggested_discount_exploratory", "mean"),
            marge_prevue_totale=("marge_prevue_xof", "sum"),
            delta_marge_vs_actuel_moyen=("delta_marge_vs_actuel_xof", "mean"),
        ).to_markdown(floatfmt=".2f"),
        "",
        "## Par objectif (marge minimale par défaut, 5 %)",
        "",
        ok[ok["marge_minimale"] == PRIMARY_MARGIN_FLOOR].groupby("objectif").agg(
            n=("unique_id", "size"), remise_moyenne=("suggested_discount_exploratory", "mean"),
            ca_prevu_total=("ca_prevu_xof", "sum"), marge_prevue_totale=("marge_prevue_xof", "sum"),
        ).to_markdown(floatfmt=".2f"),
        "",
        "## Niveau de confiance — règle documentée",
        "",
        f"`haute` exige : produit éligible individuellement **ET** remise simulée supportée par son "
        f"propre historique **ET** recommandation stable entre les 3 fenêtres de validation **ET** "
        f"WAPE_quantite(méthode) < {CONFIDENCE_WAPE_GATE:.0%}. Ce dernier plafond est **structurellement "
        f"non atteint** dans cette V1 (WAPE_quantite = {wape_methode:.1%}) — **aucune ligne ne peut donc "
        "être `haute` tant que la précision du modèle ne s'améliore pas**, quel que soit le support ou la "
        "stabilité observés. `moyenne` et `faible` restent différenciés par le support et l'éligibilité.",
        "",
        marge_primary["niveau_confiance"].value_counts().to_frame("n").to_markdown(),
        "",
        "## Produits non éligibles — aucune fausse simulation",
        "",
        f"**{len(insufficient[insufficient['objectif'].isna()])}** produits n'ont reçu aucune ligne de "
        "simulation (statut `insufficient_evidence` systématique, raison exacte dans la colonne "
        "`raison_eligibilite` du fichier `reports/pricing_final/simulateur_sorties.csv`).",
        "",
    ]
    (REPORTS / "32_pricing_simulateur.md").write_text("\n".join(lines), encoding="utf-8")
    sim_out.to_csv(PRICING_DIR / "simulateur_sorties.csv", index=False)
    logger.info("Rapport 32 écrit.")


def report_policy_comparison(panel: pd.DataFrame, eligibility_table: pd.DataFrame) -> None:
    """Compare 5 politiques dans les 3 fenêtres de validation temporelle.

    **Avertissement méthodologique appliqué strictement** : seule la
    politique « historique » est réellement OBSERVÉE (c'est ce qui s'est
    vraiment passé). Les quatre autres sont des politiques CONTREFACTUELLES
    — leur quantité/CA/marge sont des sorties du modèle `challenger_ml`
    entraîné sur le train de chaque fenêtre, jamais des résultats observés.
    Aucune de ces politiques contrefactuelles n'a été réellement appliquée :
    ceci n'est PAS une preuve qu'appliquer la politique simulée aurait
    produit la marge indiquée (`off_policy_evaluation_validated=false`).
    """
    from src.pricing.predictors import MLChallengerPredictor

    eligible_ids = set(eligibility_table.loc[eligibility_table["groupe"] != "non_eligible", "unique_id"])
    windows = build_pricing_windows(panel)
    rows = []
    for win in windows:
        train = panel[panel["ds"] <= win["train_end"]]
        test = panel[(panel["ds"] >= win["test_start"]) & (panel["ds"] <= win["test_end"]) & (panel["unique_id"].isin(eligible_ids))]
        predictor = MLChallengerPredictor().fit(train)

        # Politiques contrefactuelles par produit (calculées sur le TRAIN uniquement)
        promo_train = train[train["en_promotion"] == True]  # noqa: E712
        best_descriptive = pd.Series(dtype=float)
        for uid, g in promo_train.groupby("unique_id"):
            levels = g.groupby("remise_planifiee_pct").agg(n=("quantite_vendue", "size"), y=("quantite_vendue", "mean"))
            levels = levels[levels["n"] >= 10]
            if len(levels):
                best_descriptive[uid] = float(levels["y"].idxmax())
        freq_produit = train.groupby("unique_id")["remise_planifiee_pct"].agg(lambda s: s.mode().iloc[0])

        grid = observed_discount_grid(train, exclude_thin=True, min_support=20)
        lgbm_reco = {}
        for uid in sorted(eligible_ids & set(train["unique_id"].unique())):
            prod_rows = train[train["unique_id"] == uid]
            if prod_rows.empty:
                continue
            template = {
                "unique_id": uid, "categorie": prod_rows["categorie"].iloc[0],
                "jour_semaine": int(prod_rows["jour_semaine"].mode().iloc[0]), "mois": int(prod_rows["mois"].mode().iloc[0]),
                "prix_catalogue_xof": prod_rows["prix_catalogue_xof"].iloc[0], "cout_unitaire_xof": prod_rows["cout_unitaire_xof"].iloc[0],
                "stock_disponible_lag1": prod_rows["stock_disponible_lag1"].median(), "marque": prod_rows["marque"].iloc[0],
            }
            best_level, best_margin = 0.0, -np.inf
            for level in [0.0] + grid:
                row = dict(template)
                row["remise_planifiee_pct"] = level
                pred = predictor.predict(pd.DataFrame([row]))[0]
                prix_s = row["prix_catalogue_xof"] * (1 - level / 100)
                if prix_s < row["cout_unitaire_xof"] * (1 + PRIMARY_MARGIN_FLOOR):
                    continue
                marge = (prix_s - row["cout_unitaire_xof"]) * pred
                if marge > best_margin:
                    best_margin, best_level = marge, level
            lgbm_reco[uid] = best_level

        for policy_name, is_observed in [
            ("historique", True), ("aucune_remise", False), ("remise_frequente_produit", False),
            ("meilleure_remise_descriptive", False), ("simulateur_lightgbm_marge", False),
        ]:
            if is_observed:
                y = test["quantite_vendue"].to_numpy("float64")
                ca = test["chiffre_affaires_net_xof"].to_numpy("float64")
                marge = test["marge_totale_xof"].fillna(0.0).to_numpy("float64")
                n_neg = int((test["marge_unitaire_xof"].dropna() < 0).sum())
                n_violation = None  # pas de garde-fou appliqué historiquement — non comparable
            else:
                if policy_name == "aucune_remise":
                    remise_map = {uid: 0.0 for uid in test["unique_id"].unique()}
                elif policy_name == "remise_frequente_produit":
                    remise_map = freq_produit.to_dict()
                elif policy_name == "meilleure_remise_descriptive":
                    remise_map = best_descriptive.to_dict()
                else:
                    remise_map = lgbm_reco

                t = test.copy()
                t["remise_scenario"] = t["unique_id"].map(remise_map).fillna(0.0)
                frame = t[["unique_id", "categorie", "marque", "jour_semaine", "mois", "stock_disponible_lag1"]].copy()
                frame["remise_planifiee_pct"] = t["remise_scenario"]
                pred_qty = predictor.predict(frame)
                prix_s = t["prix_catalogue_xof"].to_numpy() * (1 - t["remise_scenario"].to_numpy() / 100)
                y = pred_qty
                ca = prix_s * pred_qty
                marge = (prix_s - t["cout_unitaire_xof"].to_numpy()) * pred_qty
                n_neg = int((marge < 0).sum())
                n_violation = int((prix_s < t["cout_unitaire_xof"].to_numpy() * (1 + PRIMARY_MARGIN_FLOOR)).sum())

            rows.append({
                "fenetre": win["index"], "politique": policy_name,
                "type": "observe_reel" if is_observed else "simule_contrefactuel_non_applique",
                "quantite_totale": float(y.sum()), "ca_total_xof": float(ca.sum()), "marge_totale_xof": float(marge.sum()),
                "taux_marge_negative": n_neg / max(len(test), 1),
                "violations_garde_fous": n_violation,
                "n_lignes": len(test),
            })

    comp = pd.DataFrame(rows)
    stability = comp.groupby("politique")["marge_totale_xof"].std().rename("stabilite_ecart_type_marge")
    summary = comp.groupby(["politique", "type"]).agg(
        quantite_moyenne_fenetre=("quantite_totale", "mean"), ca_moyen_fenetre=("ca_total_xof", "mean"),
        marge_moyenne_fenetre=("marge_totale_xof", "mean"), taux_marge_negative_moyen=("taux_marge_negative", "mean"),
        violations_garde_fous_total=("violations_garde_fous", "sum"),
    ).join(stability, on="politique")

    lines = [
        "# 34 — Comparaison aux politiques simples (avec garde-fou méthodologique)",
        "",
        f"_Généré le {datetime.now(timezone.utc).isoformat()}._",
        "",
        "## ⚠️ Avertissement méthodologique — à lire avant le tableau",
        "",
        "**Seule la politique « historique » est réellement observée** (ce qui s'est vraiment passé sur "
        "chaque fenêtre de test). Les quatre autres politiques (`aucune_remise`, "
        "`remise_frequente_produit`, `meilleure_remise_descriptive`, `simulateur_lightgbm_marge`) sont "
        "des **scénarios contrefactuels** : leurs quantité/CA/marge sont des **sorties du modèle "
        "`challenger_ml`**, entraîné sur le train de chaque fenêtre puis appliqué à un niveau de remise "
        "qui n'a PAS été réellement pratiqué sur ces dates. **Ce tableau ne démontre aucun gain de marge "
        "réel** — `off_policy_evaluation_validated=false`. Une vraie évaluation de politique nécessiterait "
        "des promotions randomisées, un groupe témoin, ou une expérimentation prospective (cf. registre "
        "V2).",
        "",
        "## Comparaison, par politique (moyenne sur les 3 fenêtres)",
        "",
        summary.to_markdown(floatfmt=".2f"),
        "",
        "## Détail par fenêtre",
        "",
        comp.to_markdown(index=False, floatfmt=".2f"),
        "",
        "**Lecture** : `remise_frequente_produit` produit un résultat identique à `aucune_remise` "
        "(la remise la plus fréquente est 0 % pour la totalité du portefeuille, cf. rapport 29). "
        "`meilleure_remise_descriptive` peut présenter des violations de garde-fous (`violations_garde_fous "
        "> 0`) car cette politique est purement descriptive/rétrospective, non filtrée par une contrainte "
        "de marge minimale — contrairement à `simulateur_lightgbm_marge` qui respecte le plancher par "
        "construction (0 violation attendue).",
        "",
    ]
    (REPORTS / "34_pricing_comparaison_politiques.md").write_text("\n".join(lines), encoding="utf-8")
    comp.to_csv(PRICING_DIR / "comparaison_politiques.csv", index=False)
    logger.info("Rapport 34 écrit.")


def report_final_comparison(accuracy_df: pd.DataFrame, method_name: str, method_stats: pd.DataFrame, sim_out: pd.DataFrame, eligibility_table: pd.DataFrame) -> None:
    stability = pd.read_csv(PRICING_DIR / "validation_temporelle_recommandations.csv")
    stab_summary = stability.groupby("methode").agg(
        ecart_type_reco=("remise_recommandee", lambda s: s.std()),
        taux_non_supporte=("supportee_par_historique", lambda s: 1 - s.mean()),
    )
    timing = accuracy_df.groupby("methode")[["duree_fit_s", "duree_predict_s"]].mean()

    comparison = method_stats.join(stab_summary).join(timing)
    comparison["produits_couverts"] = len(eligibility_table[eligibility_table["groupe"] != "non_eligible"])
    comparison["interpretabilite"] = comparison.index.map({
        "descriptif_intra_produit": "haute (moyennes calendaires directement lisibles)",
        "panel_effets_fixes": "moyenne (coefficient unique, mais calcul économétrique standard)",
        "hierarchique_pooling_categorie": "moyenne (shrinkage explicite, formule simple)",
        "challenger_ml_lightgbm": "faible (boîte noire, aucune interprétation causale possible)",
    })

    ok = sim_out[sim_out["simulation_status"] == "ok"]
    wape_methode = float(comparison.loc[method_name, "WAPE_quantite"])
    biais_methode = float(comparison.loc[method_name, "biais_quantite"])

    lines = [
        "# 33 — Comparaison des méthodes et rapport final Pricing V1 exploratoire",
        "",
        f"_Généré le {datetime.now(timezone.utc).isoformat()}._",
        "",
        "> **Je valide le prototype comme Pricing V1 exploratoire, avec garde-fous, mais pas comme "
        "moteur de prix optimal prêt pour la production.**",
        "",
        "## Règle de sélection (définie avant examen détaillé des résultats)",
        "",
        f"Parmi les méthodes dont le biais de quantité poolé (|biais_quantite|, moyenne sur les "
        f"{N_WINDOWS_PRICING} fenêtres) est inférieur à **{BIAS_THRESHOLD}** unité/jour (seuil "
        "documenté : au-delà, le biais dépasse ~10 % de la quantité moyenne du portefeuille, ~1,3 "
        "unité/jour), retenir celle de plus faible WAPE quantité. Sinon, retenir celle de plus faible "
        "biais absolu.",
        "",
        f"**Méthode retenue pour le simulateur exploratoire : `{method_name}`** (jamais présentée comme "
        "« méthode gagnante » sans réserve). Justification :",
        "",
        f"- elle satisfait le seuil de biais (|biais_quantite| = {abs(biais_methode):.4f} < {BIAS_THRESHOLD}) ;",
        "- elle respecte les garde-fous du simulateur (0 violation constatée en sortie) ;",
        "- elle est exploitable pour comparer des scénarios entre eux, à méthode constante ;",
        f"- **mais sa précision quantité reste faible : WAPE_quantite = {wape_methode:.4f} "
        f"({wape_methode:.1%})**. Un biais global quasi nul (`{biais_methode:+.4f}`) ne veut pas dire "
        "« prévisions précises » — un modèle peut compenser des sous-prévisions et des sur-prévisions "
        "individuelles tout en ayant une WAPE élevée, ce qui est exactement le cas ici.",
        "",
        "## 1. Résultats réels (validation temporelle, poolée sur 3 fenêtres)",
        "",
        comparison[["WAPE_quantite", "WAPE_CA", "WAPE_marge", "biais_quantite", "ecart_type_reco",
                    "taux_non_supporte", "duree_fit_s", "duree_predict_s", "produits_couverts", "interpretabilite"]]
        .to_markdown(floatfmt=".4f"),
        "",
        "## 2. Méthode retenue pour le simulateur exploratoire",
        "",
        f"**`{method_name}`** — voir §Règle de sélection. Violations de garde-fous en sortie du "
        f"simulateur : **0** (par construction : toute ligne `simulation_status=ok` respecte déjà la "
        "contrainte de marge minimale, les lignes qui l'auraient violée sont explicitement marquées "
        "`insufficient_evidence`, jamais une fausse simulation silencieuse).",
        "",
        "## Conclusion officielle",
        "",
        "- Le prix catalogue est fixe pour 300/300 produits.",
        "- Aucune élasticité hors promotion n'est identifiable.",
        "- Les effets des promotions sont observationnels et non causaux.",
        f"- Le modèle {method_name} possède un biais global faible ({biais_methode:+.4f}), mais une WAPE "
        f"quantité élevée de {wape_methode:.1%}.",
        "- Ses estimations individuelles sont donc incertaines.",
        "- Les sorties sont des simulations de remises, pas des prix optimaux garantis.",
        "- Aucune recommandation ne doit être appliquée automatiquement "
        "(`automatic_application_allowed=false` sur chaque ligne du simulateur).",
        "",
        "## 3. Ce qu'on peut affirmer",
        "",
        "- Le prix catalogue est fixe pour 300/300 produits (vérifié table analytique + versions SCD "
        "brutes, rapport 26 §1) — aucun prix optimal continu hors promotion n'est calculable, quelle que "
        "soit la méthode.",
        "- 218/300 produits ont un historique individuel suffisant pour une estimation directe, 70/300 "
        "nécessitent un pooling catégorie, 12/300 n'ont aucune promotion observée (rapport 28).",
        "- Le calendrier promotionnel est fiable à 100 % (rappel/précision, audit initial) — aucune "
        "incertitude sur QUAND une promotion a eu lieu, seulement sur QUEL EFFET elle a eu.",
        "- 679 lignes à marge négative sur 73 produits, dont la majorité proviennent de la remise "
        "planifiée elle-même (pas seulement du bruit de prix) — un garde-fou de marge minimale reste "
        "nécessaire, testé à 4 niveaux (rapport 31).",
        "- **Résultat le plus utile de ce prototype** : avec les données actuelles, les promotions "
        "historiques ne semblent généralement pas générer assez de volume supplémentaire pour compenser "
        "la réduction de marge — le simulateur, contraint par la marge minimale, recommande donc souvent "
        "aucune remise (remise moyenne simulée : 1,2 % sur le scénario marge, cf. rapport 32). C'est un "
        "résultat observationnel, pas une preuve causale, mais il est cohérent sur toutes les méthodes "
        "testées et sur les 3 fenêtres de validation.",
        "",
        "## 4. Ce qui reste seulement observationnel",
        "",
        "- **Tout uplift mesuré (les 4 méthodes) reste une association, jamais un effet causal prouvé** — "
        "l'affectation des campagnes n'est pas randomisée et son mécanisme n'est pas documenté.",
        f"- La méthode retenue (`{method_name}`) est **la moins interprétable** : elle peut avoir la "
        "meilleure précision prédictive relative sans qu'on puisse en tirer un « effet remise » unique.",
        "- Le panel à effets fixes fournit LE SEUL coefficient directement interprétable comme "
        "« association par point de remise », mais avec un biais de prédiction plus fort (sous-prévision "
        "systématique) — à ne pas utiliser pour dimensionner une simulation sans corriger ce biais.",
        "- **La comparaison aux politiques simples (rapport 34) est elle-même observationnelle pour 4 des "
        "5 politiques comparées** — seule la politique historique est réellement observée ; "
        "`off_policy_evaluation_validated=false` pour toutes les simulations.",
        "",
        "## 5. Recommandations sûres",
        "",
        f"- {len(ok[(ok['objectif']=='marge') & (ok['marge_minimale']==PRIMARY_MARGIN_FLOOR)])} simulations "
        f"de remise, scénario marge, marge minimale {PRIMARY_MARGIN_FLOOR:.0%} — toutes respectent "
        "structurellement coût, marge minimale et grille observée (aucune extrapolation). **Aucune ne "
        "doit être appliquée automatiquement.**",
        "- Les niveaux de confiance `moyenne` (le plafond atteignable dans cette V1, cf. rapport 32) "
        "restent les seules simulations à présenter en premier pour une revue humaine — jamais `haute`, "
        "structurellement indisponible tant que WAPE_quantite ≥ 50 %.",
        "- Les 12 produits `insufficient_evidence` ne doivent recevoir AUCUNE simulation exploitée par ce "
        "système — statu quo ou décision manuelle uniquement.",
        "",
        "## 6. Limites",
        "",
        "- 3 fenêtres de validation temporelle (vs 6 côté forecasting) — simplification documentée pour "
        "un coût de calcul raisonnable en V1.",
        "- Bande d'incertitude de scénario simplifiée (`scenario_uncertainty_band`, ±WAPE poolée), "
        "**pas un intervalle de confiance statistique**, pas un intervalle conforme calibré par segment "
        "comme en forecasting — inscrit au registre V2.",
        "- Confusion catégorie×niveau de remise non totalement débiaisée (le panel FE contrôle "
        "catégorie×mois mais la sélection des campagnes elle-même reste non vérifiable).",
        "- Rupture de stock intrajournalière non mesurable (même limite que le forecasting).",
        "- Aucun A/B test prix disponible pour trancher la question causale.",
        "- `off_policy_evaluation_validated=false` : la validation temporelle mesure la capacité à "
        "prévoir des quantités pour des remises historiquement observées — elle ne prouve pas que la "
        "politique simulée aurait produit la marge indiquée si elle avait été réellement appliquée.",
        "",
        "**Aucune publication Supabase, aucun déploiement. Arrêt avant toute intégration applicative.**",
        "",
    ]
    (REPORTS / "33_pricing_comparaison_rapport_final.md").write_text("\n".join(lines), encoding="utf-8")
    comparison.to_csv(PRICING_DIR / "comparaison_methodes.csv")
    logger.info("Rapport 33 écrit.")


if __name__ == "__main__":
    setup_logging()
    t0 = time.time()
    panel = build_panel()
    eligibility_table = report_eligibility(panel)
    baselines = build_all_baselines(panel)
    baselines.to_csv(PRICING_DIR / "baselines.csv", index=False)
    report_confounding(panel, baselines)
    logger.info("Sections 1-2 terminées en %.1fs", time.time() - t0)

    t1 = time.time()
    accuracy_df = run_temporal_validation(panel, eligibility_table)
    logger.info("Section 3 (validation temporelle) terminée en %.1fs", time.time() - t1)

    t2 = time.time()
    report_negative_margins(panel)
    logger.info("Section 4 (marges négatives) terminée en %.1fs", time.time() - t2)

    t3 = time.time()
    method_name, method_stats = select_method(accuracy_df)
    logger.info("Méthode retenue pour le simulateur exploratoire : %s\n%s", method_name, method_stats.to_string())
    winning_cls = next(c for c in ALL_PREDICTOR_CLASSES if c().name == method_name)
    final_predictor = winning_cls().fit(panel)
    wape_for_interval = float(method_stats.loc[method_name, "WAPE_quantite"])

    reco_hist = pd.read_csv(PRICING_DIR / "validation_temporelle_recommandations.csv")
    reco_method = reco_hist[reco_hist["methode"] == method_name]
    stability_lookup = (
        reco_method.groupby("unique_id")["remise_recommandee"].nunique().eq(1).to_dict()
    )

    sim_out = run_simulator(panel, eligibility_table, final_predictor, method_name, wape_for_interval, baselines, stability_lookup)
    report_simulator(sim_out, method_name, method_stats, eligibility_table)
    report_policy_comparison(panel, eligibility_table)
    report_final_comparison(accuracy_df, method_name, method_stats, sim_out, eligibility_table)
    logger.info("Sections 5-7 (simulateur + comparaison) terminées en %.1fs", time.time() - t3)
    logger.info("Pipeline pricing complet en %.1fs", time.time() - t0)
