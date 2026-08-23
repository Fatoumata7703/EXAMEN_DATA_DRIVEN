"""
fact_experimentation_prix — v4, corrige les 11 points de l'audit du 20 août.

Changements structurels vs v3 :
  - warm-up réellement inclusif de 90 jours (89 avant -- erreur d'arithmétique de dates)
  - prix_applique recalculé APRÈS le contrôle d'éligibilité, à partir de discount_applied
    (v3 utilisait discount_proposed pour le prix, avant même de savoir si la remise
    serait acceptée -- incohérence corrigée)
  - exclusion des décisions dont la FENÊTRE COMPLÈTE de 7 jours chevauche une promotion
    historique, pas seulement le lundi de la décision
  - produits sans vente en warm-up : statut cold_start explicite, plus de plancher
    silencieux
  - nouvel outcome margin_window_xof_7j
  - product_impressions recalculé depuis fact_exposition_reco v4 (cohérent avec la
    nouvelle table, elle-même sans fuite)
  - inférence statistique au grain PRODUIT (n=300 observations indépendantes), pas au
    grain produit-semaine (n=12996, pseudo-répliqué) : bootstrap, test de permutation,
    IC, correction de Holm -- voir fichier séparé analyse_significativite_v4.py

Lignage :
  script  : fact_experimentation_prix_v4.py
  seed    : 48
  entrees : dim_produit.csv, fact_stock.csv, fact_exposition_reco_v4.csv,
            dim_promotion.csv (Gold, v3 pipeline)
"""
import hashlib
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

SEED = 48
rng = np.random.default_rng(SEED)

STAR_DIR = Path("/home/claude/airflow_project/lake/gold/star_schema")
V4_DIR = Path("/home/claude/journal_v4")

print("Chargement des données existantes (inchangées)...")
dim_produit = pd.read_csv(STAR_DIR / "dim_produit.csv")
dim_promotion = pd.read_csv(STAR_DIR / "dim_promotion.csv")
fact_ventes = pd.read_csv(STAR_DIR / "fact_ventes.csv")
fact_stock = pd.read_csv(STAR_DIR / "fact_stock.csv")
fact_exposition_v4 = pd.read_csv(V4_DIR / "fact_exposition_reco_v4.csv", low_memory=False)

dim_produit["valid_from"] = pd.to_datetime(dim_produit["valid_from"]).dt.tz_localize("UTC")
produit_keys = dim_produit["produit_key"].to_numpy()
prix_base = dict(zip(dim_produit["produit_key"], dim_produit["prix_base_xof"]))
cout = dict(zip(dim_produit["produit_key"], dim_produit["cout_xof"]))
categorie_de = dict(zip(dim_produit["produit_key"], dim_produit["categorie"]))
launch_of = dict(zip(dim_produit["produit_key"], dim_produit["valid_from"]))

fact_ventes["date_key"] = fact_ventes["date_key"].astype(str)
fact_ventes["date"] = pd.to_datetime(fact_ventes["date_key"], format="%Y%m%d", utc=True)
fact_exposition_v4["impression_timestamp"] = pd.to_datetime(fact_exposition_v4["impression_timestamp"], utc=True)

# FIX #5 : warm-up réellement inclusif de 90 jours
WARMUP_START = pd.Timestamp("2025-02-01", tz="UTC")
WARMUP_END = pd.Timestamp("2025-05-02", tz="UTC")   # inclusif -> (mai 2 - fev 1) = 90 jours pile
EXPERIMENT_START = pd.Timestamp("2025-05-03", tz="UTC")
EXPERIMENT_END = pd.Timestamp("2026-07-31", tz="UTC")
N_JOURS_WARMUP = (WARMUP_END - WARMUP_START).days
assert N_JOURS_WARMUP == 90, f"warm-up devrait faire 90 jours, en fait {N_JOURS_WARMUP}"
print(f"Warm-up : {WARMUP_START.date()} -> {WARMUP_END.date()} ({N_JOURS_WARMUP} jours, vérifié)")

# ----------------------------------------------------------------------------
# classe_abc + demande de base, warm-up strictement antérieur à l'expérience
# ----------------------------------------------------------------------------
warmup_ventes = fact_ventes[
    (fact_ventes["date"] >= WARMUP_START) & (fact_ventes["date"] <= WARMUP_END)
    & (fact_ventes["statut_commande"] == "confirmee")
]
ca_warmup = warmup_ventes.groupby("produit_key")["montant_net_xof"].sum().sort_values(ascending=False)
ca_cumule_pct = ca_warmup.cumsum() / ca_warmup.sum() if ca_warmup.sum() > 0 else ca_warmup
classe_abc_warmup = pd.Series(
    np.where(ca_cumule_pct <= 0.80, "A", np.where(ca_cumule_pct <= 0.95, "B", "C")),
    index=ca_warmup.index,
)
for pk in produit_keys:
    if pk not in classe_abc_warmup.index:
        classe_abc_warmup.loc[pk] = "C"

# FIX #6 : cold_start explicite, pas de plancher silencieux
qty_warmup = warmup_ventes.groupby("produit_key")["quantite"].sum()
cold_start_produit = {pk: (qty_warmup.get(pk, 0) == 0) for pk in produit_keys}
baseline_daily_demand = {
    pk: (qty_warmup.get(pk, 0) / N_JOURS_WARMUP) if not cold_start_produit[pk] else 0.05
    # le plancher 0.05 ne s'applique QUE si cold_start=True, et c'est visible dans la colonne dédiée
    for pk in produit_keys
}
print(f"Produits cold_start (aucune vente en warm-up) : {sum(cold_start_produit.values())} / {len(produit_keys)}")

# ----------------------------------------------------------------------------
# Randomisation par blocs, ordre des groupes re-mélangé par strate (fix v3 conservé)
# ----------------------------------------------------------------------------
print("\nAssignation persistante par blocs équilibrés...")
TREATMENT_LEVELS = ["controle_0pct", "traitement_5pct", "traitement_10pct", "traitement_15pct"]
DISCOUNT_OF = {"controle_0pct": 0, "traitement_5pct": 5, "traitement_10pct": 10, "traitement_15pct": 15}

treatment_group_of = {}
produits_df = dim_produit.copy()
produits_df["classe_abc"] = produits_df["produit_key"].map(classe_abc_warmup)
for (cat, abc), grp in produits_df.groupby(["categorie", "classe_abc"]):
    ids = grp["produit_key"].tolist()
    perm = rng.permutation(ids)
    levels_shuffled = rng.permutation(TREATMENT_LEVELS)
    for i, pk in enumerate(perm):
        treatment_group_of[pk] = levels_shuffled[i % 4]

balance = pd.Series(treatment_group_of).value_counts(normalize=True)
print("Équilibre global :", balance.round(3).to_dict())

# ----------------------------------------------------------------------------
# FIX #2 : exclusion si la FENÊTRE COMPLÈTE de 7 jours chevauche une promo,
# pas seulement le jour de la décision
# ----------------------------------------------------------------------------
dim_promotion["date_debut"] = pd.to_datetime(dim_promotion["date_debut"]).dt.tz_localize("UTC")
dim_promotion["date_fin"] = pd.to_datetime(dim_promotion["date_fin"]).dt.tz_localize("UTC")
promo_par_produit = dim_produit[["produit_key", "product_id", "categorie"]].merge(dim_promotion, how="cross")
mask_valide = (
    ((promo_par_produit["portee"] == "product") & (promo_par_produit["product_id"] == promo_par_produit["cible"]))
    | ((promo_par_produit["portee"] == "category") & (promo_par_produit["categorie"] == promo_par_produit["cible"]))
)
promo_par_produit = promo_par_produit[mask_valide]
promos_by_product = promo_par_produit.groupby("produit_key")[["date_debut", "date_fin"]].apply(
    lambda d: list(zip(d["date_debut"], d["date_fin"]))
).to_dict()


def chevauche_promo(pk, fenetre_debut, fenetre_fin):
    for (pd_debut, pd_fin) in promos_by_product.get(pk, []):
        if pd_debut <= fenetre_fin and pd_fin >= fenetre_debut:
            return True
    return False

# ----------------------------------------------------------------------------
# product_impressions : recalculé depuis fact_exposition_reco v4 (recherche binaire)
# ----------------------------------------------------------------------------
impressions_par_produit_triees = {
    pk: np.sort(grp["impression_timestamp"].astype("datetime64[ns, UTC]").values.astype("int64"))
    # FIX bug P-12 (audit DS) : .values seul sur une série tz-aware récente donne des
    # timestamps en MICROSECONDES, alors que Timestamp.value (utilisé plus bas pour
    # decision_ts) est toujours en NANOSECONDES -- écart de facteur 1000 qui plaçait
    # systématiquement la recherche binaire en fin de tableau, donnant le total complet
    # au lieu du cumul avant décision. Cast explicite en datetime64[ns, UTC] avant
    # extraction pour garantir la même unité des deux côtés de la comparaison.
    for pk, grp in fact_exposition_v4.groupby("produit_key")
}

stock_lookup = fact_stock.set_index(["produit_key", "date_key"])["niveau_stock"].to_dict()

ELASTICITE = 1.8
BRUIT_DEMANDE_SD = 0.15

print("\nGénération des décisions hebdomadaires...")
lundis = pd.date_range(EXPERIMENT_START, EXPERIMENT_END, freq="W-MON", tz="UTC")

decisions = []
decision_counter = 0
experiment_counter = 0
n_exclues_lancement = 0
n_exclues_promo_fenetre = 0

for lundi in lundis:
    experiment_counter += 1
    experiment_id = f"XPP4{experiment_counter:04d}"
    veille = lundi - timedelta(days=1)
    veille_key = int(veille.strftime("%Y%m%d"))
    fenetre_fin = lundi + timedelta(days=7)

    for pk in produit_keys:
        if lundi <= launch_of[pk]:
            n_exclues_lancement += 1
            continue

        # FIX #2 : fenêtre complète, pas juste le lundi
        if chevauche_promo(pk, lundi, fenetre_fin):
            n_exclues_promo_fenetre += 1
            continue

        groupe = treatment_group_of[pk]
        discount_proposed = DISCOUNT_OF[groupe]

        # éligibilité calculée sur le prix qui RÉSULTERAIT de discount_proposed
        prix_teste = round(prix_base[pk] * (1 - discount_proposed / 100), 0)
        marge_ratio = (prix_teste - cout[pk]) / prix_teste if prix_teste else 0
        eligible = bool(prix_teste >= cout[pk] and marge_ratio >= 0.05)
        discount_applied = discount_proposed if eligible else 0

        # FIX #3/#4 : prix_applique recalculé APRES l'éligibilité, à partir de discount_applied
        prix_applique = round(prix_base[pk] * (1 - discount_applied / 100), 0)

        decision_ts = lundi + timedelta(hours=6)
        stock_veille = stock_lookup.get((pk, veille_key))
        if stock_veille is None:
            continue  # même garde-fou que v3 (aucun stock avant lancement réel)

        ts_array = impressions_par_produit_triees.get(pk)
        impressions_avant = int(np.searchsorted(ts_array, decision_ts.value, side="left")) if ts_array is not None else 0

        multiplicateur = 1 + (discount_applied / 100) * ELASTICITE
        demande_attendue = baseline_daily_demand[pk] * 7 * multiplicateur
        bruit = float(rng.normal(1.0, BRUIT_DEMANDE_SD))
        units_sold_window = max(0, round(demande_attendue * bruit))
        revenue_window_xof = round(units_sold_window * prix_applique)
        # FIX #7 : outcome de marge, calculé exclusivement à partir de prix_applique
        margin_window_xof = round(units_sold_window * (prix_applique - cout[pk]))

        decision_counter += 1
        decisions.append({
            "decision_id": f"DEC4{decision_counter:08d}",
            "experiment_id": experiment_id,
            "produit_key": pk,
            "decision_timestamp": decision_ts.isoformat(),
            "treatment_group": groupe,
            "eligible_for_discount": eligible,
            "discount_proposed": discount_proposed,
            "discount_applied": discount_applied,
            "prix_applique_xof": prix_applique,
            "propensity_score": round(1 / len(TREATMENT_LEVELS), 3),
            "product_impressions": impressions_avant,
            "stock_at_decision": stock_veille,
            "categorie": categorie_de[pk],
            "classe_abc": classe_abc_warmup.get(pk, "C"),
            "cold_start_warmup": cold_start_produit[pk],
            "units_sold_window_7j": units_sold_window,
            "revenue_window_xof_7j": revenue_window_xof,
            "margin_window_xof_7j": margin_window_xof,
            "fenetre_observation_debut": decision_ts.isoformat(),
            "fenetre_observation_fin": (decision_ts + timedelta(days=7)).isoformat(),
            "statut_experience": "synthetic_academic_experiment",
        })

fact_experimentation_prix_v4 = pd.DataFrame(decisions)
print(f"\n{len(fact_experimentation_prix_v4)} décisions générées.")
print(f"Exclues (avant lancement) : {n_exclues_lancement}")
print(f"Exclues (chevauchement fenêtre 7j avec promo) : {n_exclues_promo_fenetre}")

out_path = V4_DIR / "fact_experimentation_prix_v4.csv"
fact_experimentation_prix_v4.to_csv(out_path, index=False)
print(f"\nSauvegardé : {out_path}")
print(f"Empreinte de sortie (SHA256) : {hashlib.sha256(open(out_path,'rb').read()).hexdigest()}")
print(f"Date d'exécution : {datetime.now().isoformat()}")
print(f"Seed : {SEED}")
