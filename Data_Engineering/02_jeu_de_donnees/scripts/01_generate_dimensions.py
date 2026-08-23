"""
01_generate_dimensions.py — Génère dim_products, dim_customers, promotions.

Ces 3 tables n'ont PAS changé depuis la toute première génération (seed=42,
reproductible) : elles ne dépendent d'aucun panier ni d'aucune session, donc
aucune des corrections d'audit ultérieures ne les concerne.

Fait partie d'une séquence en 3 étapes :
  01_generate_dimensions.py       (ce fichier)   -> dim_products, dim_customers, promotions
  02_generate_transactions.py                    -> fact_transactions, stock_daily (paniers réels)
  03_generate_web_events.py                      -> web_events (sessions, funnel, anonymes, bots)
Exécuter dans cet ordre : 01 -> 02 -> 03 (02 et 03 dépendent des fichiers produits par 01).
"""

"""
Générateur de jeu de données synthétique
Plateforme Data-Driven Pricing & Recommandation - E-commerce local (Afrique de l'Ouest, FCFA/XOF)

Produit 6 tables cohérentes entre elles (clés partagées) :
  - dim_products      : catalogue produit
  - dim_customers     : clients
  - promotions        : campagnes de remise
  - fact_transactions : ventes (batch)
  - web_events        : logs de navigation (streaming simulé)
  - stock_daily       : niveau de stock quotidien par produit

La logique métier (saisonnalité, élasticité prix, effet weekend, ruptures de stock,
funnel de navigation) est injectée volontairement, ainsi que des imperfections de
qualité de données (nulls, doublons, valeurs aberrantes, FK orphelines) pour donner
une vraie matière au travail de data quality / pipeline.

Reproductible : SEED fixe.
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import json
import os

# ----------------------------------------------------------------------------
# CONFIG
# ----------------------------------------------------------------------------
SEED = 42
rng = np.random.default_rng(SEED)

N_PRODUCTS = 300
N_CUSTOMERS = 5000
N_PROMOTIONS = 120

START_DATE = datetime(2025, 2, 1)
END_DATE = datetime(2026, 7, 31)
DATES = pd.date_range(START_DATE, END_DATE, freq="D")
N_DAYS = len(DATES)

OUT_DIR = "/home/claude/output"
os.makedirs(OUT_DIR, exist_ok=True)

CURRENCY = "XOF"

# ----------------------------------------------------------------------------
# REFERENCE DATA
# ----------------------------------------------------------------------------
CATEGORIES = {
    "Electronique & High-Tech":  {"base_price": (25000, 450000), "margin": (0.15, 0.30), "popularity": 1.3,
                                   "seasonality": [0.9,0.9,0.9,0.9,0.9,1.0,1.0,1.0,1.0,1.1,1.6,1.9]},
    "Telephonie & Accessoires":  {"base_price": (3000, 350000),  "margin": (0.18, 0.35), "popularity": 1.5,
                                   "seasonality": [1.0,0.9,0.9,1.0,1.0,1.0,1.0,1.0,1.1,1.1,1.4,1.7]},
    "Mode & Vetements":          {"base_price": (2500, 45000),   "margin": (0.35, 0.55), "popularity": 1.2,
                                   "seasonality": [1.1,1.0,1.0,1.0,1.1,1.0,0.9,0.9,1.0,1.1,1.3,1.5]},
    "Beaute & Soins":            {"base_price": (1500, 35000),   "margin": (0.30, 0.50), "popularity": 1.1,
                                   "seasonality": [1.0,1.1,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.2,1.4]},
    "Maison & Cuisine":          {"base_price": (2000, 120000),  "margin": (0.20, 0.40), "popularity": 0.9,
                                   "seasonality": [0.9,0.9,0.9,1.0,1.0,1.0,1.0,1.0,1.0,1.1,1.3,1.5]},
    "Alimentation & Epicerie":   {"base_price": (500, 15000),    "margin": (0.10, 0.20), "popularity": 1.6,
                                   "seasonality": [1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.1,1.3,1.6]},
    "Sport & Loisirs":           {"base_price": (3000, 90000),   "margin": (0.25, 0.40), "popularity": 0.8,
                                   "seasonality": [1.2,1.1,1.1,1.0,1.0,0.9,0.9,0.9,1.0,1.0,1.1,1.2]},
    "Bebe & Enfant":             {"base_price": (1500, 60000),   "margin": (0.25, 0.40), "popularity": 0.9,
                                   "seasonality": [1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.1,1.2,1.0,1.2,1.3]},
}
CAT_NAMES = list(CATEGORIES.keys())

BRANDS = ["Sunu", "Teranga", "Baobab", "Sahel", "Dakaroise", "Lumo", "Kora", "Nimba",
          "Cauri", "Djoloff", "Atlas", "Sirius", "Nova", "Prime", "Urban", "Eco"]
NOUNS = {
    "Electronique & High-Tech": ["Ecran", "Enceinte", "Casque", "Ordinateur portable", "Tablette", "Camera", "Console", "Chargeur solaire"],
    "Telephonie & Accessoires": ["Smartphone", "Coque telephone", "Ecouteurs", "Powerbank", "Support telephone", "Cable USB-C", "Protection ecran"],
    "Mode & Vetements":         ["Boubou", "Robe", "Chemise", "Pantalon", "Sac a main", "Sandales", "Veste", "Ensemble wax"],
    "Beaute & Soins":           ["Creme hydratante", "Huile de baobab", "Savon noir", "Parfum", "Beurre de karite", "Serum visage"],
    "Maison & Cuisine":         ["Marmite", "Service a the", "Mixeur", "Ventilateur", "Set de cuisine", "Lampe solaire", "Panier tresse"],
    "Alimentation & Epicerie":  ["Riz brise 25kg", "Huile arachide 5L", "The Touba", "Sucre en poudre", "Cafe Touba", "Bissap sec", "Concentre tomate"],
    "Sport & Loisirs":          ["Ballon foot", "Tapis de yoga", "Corde a sauter", "Velo", "Sac de sport", "Maillot equipe"],
    "Bebe & Enfant":            ["Couches", "Poussette", "Lait infantile", "Jouet eveil", "Body bebe", "Biberon"],
}
REGIONS = ["Dakar", "Thies", "Saint-Louis", "Ziguinchor", "Touba", "Mbour", "Kaolack", "Rufisque", "Diourbel", "Louga"]
DEVICES = ["mobile", "desktop", "tablet"]
DEVICE_WEIGHTS = [0.72, 0.22, 0.06]
REFERRALS = ["organic_search", "social_media", "direct", "email_campaign", "paid_ads", "affiliate"]
REFERRAL_WEIGHTS = [0.30, 0.28, 0.18, 0.10, 0.10, 0.04]

print(f"Génération sur {N_DAYS} jours, {N_PRODUCTS} produits, {N_CUSTOMERS} clients...")

# ----------------------------------------------------------------------------
# 1. DIM PRODUCTS
# ----------------------------------------------------------------------------
products = []
for i in range(N_PRODUCTS):
    cat = CAT_NAMES[rng.integers(0, len(CAT_NAMES))]
    cfg = CATEGORIES[cat]
    price_lo, price_hi = cfg["base_price"]
    base_price = round(float(rng.uniform(price_lo, price_hi)), -1)
    margin_lo, margin_hi = cfg["margin"]
    margin = rng.uniform(margin_lo, margin_hi)
    cost = round(base_price * (1 - margin), 0)
    noun = NOUNS[cat][rng.integers(0, len(NOUNS[cat]))]
    brand = BRANDS[rng.integers(0, len(BRANDS))]
    launch_offset = int(rng.integers(-400, N_DAYS - 30))
    launch_date = START_DATE + timedelta(days=launch_offset)
    products.append({
        "product_id": f"P{i+1:05d}",
        "product_name": f"{brand} {noun} #{i+1}",
        "category": cat,
        "brand": brand,
        "base_price_xof": base_price,
        "cost_xof": cost,
        "popularity_score": round(float(cfg["popularity"] * rng.uniform(0.5, 1.5)), 3),
        "launch_date": max(launch_date, START_DATE - timedelta(days=365)).date().isoformat(),
        "initial_stock": int(rng.integers(50, 500)),
    })
dim_products = pd.DataFrame(products)

# inject a few duplicate category-casing inconsistencies (data quality issue)
dirty_idx = rng.choice(dim_products.index, size=15, replace=False)
dim_products.loc[dirty_idx, "category"] = dim_products.loc[dirty_idx, "category"].str.upper()

# ----------------------------------------------------------------------------
# 2. DIM CUSTOMERS
# ----------------------------------------------------------------------------
FIRST_NAMES = ["Awa", "Moussa", "Fatou", "Ibrahima", "Aissatou", "Cheikh", "Mariama", "Ousmane",
               "Khady", "Abdoulaye", "Ndeye", "Mamadou", "Coumba", "Serigne", "Aminata", "Babacar"]
LAST_NAMES = ["Diop", "Ndiaye", "Fall", "Gueye", "Sow", "Ba", "Diallo", "Sarr", "Cisse", "Diagne", "Faye", "Thiam"]

customers = []
for i in range(N_CUSTOMERS):
    signup_offset = int(rng.integers(-800, N_DAYS - 1))
    signup_date = START_DATE + timedelta(days=signup_offset)
    customers.append({
        "customer_id": f"C{i+1:06d}",
        "full_name": f"{FIRST_NAMES[rng.integers(0,len(FIRST_NAMES))]} {LAST_NAMES[rng.integers(0,len(LAST_NAMES))]}",
        "region": REGIONS[rng.integers(0, len(REGIONS))],
        "age_bracket": rng.choice(["18-24", "25-34", "35-44", "45-54", "55+"], p=[0.22,0.33,0.25,0.13,0.07]),
        "signup_date": max(signup_date, START_DATE - timedelta(days=1000)).date().isoformat(),
        "loyalty_segment": rng.choice(["nouveau", "occasionnel", "regulier", "vip"], p=[0.35,0.35,0.22,0.08]),
    })
dim_customers = pd.DataFrame(customers)

# inject missing values (data quality issue): ~3% missing age_bracket / region
for col in ["age_bracket", "region"]:
    null_idx = rng.choice(dim_customers.index, size=int(0.03 * N_CUSTOMERS), replace=False)
    dim_customers.loc[null_idx, col] = None

# ----------------------------------------------------------------------------
# 3. PROMOTIONS
# ----------------------------------------------------------------------------
promos = []
for i in range(N_PROMOTIONS):
    scope = rng.choice(["category", "product"], p=[0.6, 0.4])
    if scope == "category":
        target = CAT_NAMES[rng.integers(0, len(CAT_NAMES))]
    else:
        target = dim_products.sample(1, random_state=int(rng.integers(0, 1_000_000))).iloc[0]["product_id"]
    start_offset = int(rng.integers(0, N_DAYS - 20))
    duration = int(rng.integers(3, 15))
    start_date = START_DATE + timedelta(days=start_offset)
    end_date = start_date + timedelta(days=duration)
    promos.append({
        "promotion_id": f"PROMO{i+1:04d}",
        "scope": scope,
        "target": target,
        "discount_pct": int(rng.choice([5,10,15,20,25,30,40], p=[0.2,0.25,0.2,0.15,0.1,0.07,0.03])),
        "start_date": start_date.date().isoformat(),
        "end_date": end_date.date().isoformat(),
    })
promotions = pd.DataFrame(promos)


# ----------------------------------------------------------------------------
# Écriture des fichiers de sortie
# ----------------------------------------------------------------------------
import os
OUT_DIR = os.environ.get("OUT_DIR", "/home/claude/livrables_finaux/jeu_de_donnees/donnees")
os.makedirs(OUT_DIR, exist_ok=True)

dim_products.to_csv(f"{OUT_DIR}/dim_products.csv", index=False)
dim_customers.to_csv(f"{OUT_DIR}/dim_customers.csv", index=False)
promotions.to_csv(f"{OUT_DIR}/promotions.csv", index=False)

print(f"dim_products : {len(dim_products)} lignes")
print(f"dim_customers : {len(dim_customers)} lignes")
print(f"promotions : {len(promotions)} lignes")
print(f"Écrit dans {OUT_DIR}/")
