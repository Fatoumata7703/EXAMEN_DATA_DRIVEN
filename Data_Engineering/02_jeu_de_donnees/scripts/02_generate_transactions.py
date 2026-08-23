"""
Étape 2 v3 — corrige 2 bugs identifiés par l'audit du data scientist :

BUG 1 (promotions mal ciblées) : la version précédente réattribuait promotion_id après
coup en matchant seulement sur discount_pct + dates, jamais sur le produit/catégorie
réel. Fix : promo_lookup stocke maintenant (discount_pct, promotion_id) ensemble dès la
construction, donc chaque ligne reçoit directement la BONNE promotion, plus de
réattribution ambiguë après coup.

BUG 2 (stock non réconciliable) : n'était pas un bug de formule mais un oubli — cette
étape régénère stock_daily avec, en plus, quantite_reapprovisionnee (demandée par le DS)
pour permettre une réconciliation exacte :
    stock_fin(t) = stock_fin(t-1) - quantite_vendue_tous_statuts(t) + quantite_reapprovisionnee(t)

Convention retenue (à documenter) : une commande annulée ou retournée DÉCRÉMENTE quand
même le stock au moment de l'achat (le stock est engagé/expédié avant qu'une annulation
soit connue) — c'est pour ça que la réconciliation doit se faire "tous statuts confondus",
pas seulement sur les commandes confirmées. Aucune réintégration en stock au moment
d'une annulation/retour n'est modélisée dans cette version (limite connue, documentée).
"""
import os
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path

SEED = 42
rng = np.random.default_rng(SEED)

SOURCE_DIR = Path(os.environ.get("SOURCE_DIR", "/home/claude/livrables_finaux/jeu_de_donnees/donnees"))
OUT_DIR = Path(os.environ.get("OUT_DIR", "/home/claude/livrables_finaux/jeu_de_donnees/donnees"))
OUT_DIR.mkdir(exist_ok=True)

START_DATE = datetime(2025, 2, 1)
END_DATE = datetime(2026, 7, 31)
DATES = pd.date_range(START_DATE, END_DATE, freq="D")

CATEGORIES_SEASONALITY = {
    "Electronique & High-Tech":  [0.9,0.9,0.9,0.9,0.9,1.0,1.0,1.0,1.0,1.1,1.6,1.9],
    "Telephonie & Accessoires":  [1.0,0.9,0.9,1.0,1.0,1.0,1.0,1.0,1.1,1.1,1.4,1.7],
    "Mode & Vetements":          [1.1,1.0,1.0,1.0,1.1,1.0,0.9,0.9,1.0,1.1,1.3,1.5],
    "Beaute & Soins":            [1.0,1.1,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.2,1.4],
    "Maison & Cuisine":          [0.9,0.9,0.9,1.0,1.0,1.0,1.0,1.0,1.0,1.1,1.3,1.5],
    "Alimentation & Epicerie":   [1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.1,1.3,1.6],
    "Sport & Loisirs":           [1.2,1.1,1.1,1.0,1.0,0.9,0.9,0.9,1.0,1.0,1.1,1.2],
    "Bebe & Enfant":             [1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.1,1.2,1.0,1.2,1.3],
}

REORDER_POINT = 20
RESTOCK_QTY_RANGE = (100, 300)
K_BASKETS = 100

print("Chargement des dimensions déjà validées (inchangées)...")
products = pd.read_csv(SOURCE_DIR / "dim_products.csv")
customers = pd.read_csv(SOURCE_DIR / "dim_customers.csv")
promotions = pd.read_csv(SOURCE_DIR / "promotions.csv")
customer_ids = customers["customer_id"].to_numpy()

products["category_clean"] = products["category"].str.strip().str.lower().map(
    {k.lower(): k for k in CATEGORIES_SEASONALITY}
)
products["launch_date_dt"] = pd.to_datetime(products["launch_date"])

# ----------------------------------------------------------------------------
# FIX BUG 1 : promo_lookup stocke (discount_pct, promotion_id) ENSEMBLE,
# indexés par produit réel — plus jamais besoin de deviner après coup.
# ----------------------------------------------------------------------------
print("Construction de la table des promotions actives par jour (avec promotion_id)...")
promo_lookup = {}
for _, p in promotions.iterrows():
    s = datetime.fromisoformat(p["start_date"])
    e = datetime.fromisoformat(p["end_date"])
    for d in pd.date_range(max(s, START_DATE), min(e, END_DATE), freq="D"):
        targets = (products.loc[products["category_clean"] == p["target"], "product_id"].tolist()
                   if p["scope"] == "category" else [p["target"]])
        for pid in targets:
            promo_lookup.setdefault((pid, d.date()), (p["discount_pct"], p["promotion_id"]))

stock_state = dict(zip(products["product_id"], products["initial_stock"]))
pid_array = products["product_id"].to_numpy()
popularity = dict(zip(products["product_id"], products["popularity_score"]))
category_of = dict(zip(products["product_id"], products["category_clean"]))
base_price_of = dict(zip(products["product_id"], products["base_price_xof"]))
launch_of = dict(zip(products["product_id"], products["launch_date_dt"]))

transactions = []
stock_rows = []
order_counter = 0
line_counter = 0

print("Simulation basket-native jour par jour (v3)...")
for d in DATES:
    dow = d.dayofweek
    weekend_mult = 1.25 if dow >= 5 else 1.0
    month_idx = d.month - 1
    d_date = d.date()

    eligible_mask = (products["launch_date_dt"] <= d) & (products["product_id"].map(stock_state).fillna(0) > 0)
    eligible = products.loc[eligible_mask, "product_id"].tolist()
    if not eligible:
        continue

    weights = np.array([
        popularity[pid] * CATEGORIES_SEASONALITY[category_of[pid]][month_idx]
        * (1.0 + (promo_lookup.get((pid, d_date), (0, None))[0] / 100.0) * 2.2)
        for pid in eligible
    ])
    weights = weights / weights.sum()

    total_weight = np.array([
        popularity[pid] * CATEGORIES_SEASONALITY[category_of[pid]][month_idx]
        for pid in eligible
    ]).sum()
    lambda_baskets = K_BASKETS * (total_weight / len(eligible)) * weekend_mult * (len(eligible) / 300)
    n_baskets = rng.poisson(max(lambda_baskets, 1))

    # quantité vendue par produit ce jour (tous statuts confondus) — pour le
    # décrément de stock ET pour permettre au DS de réconcilier exactement
    sold_today = {}

    for _ in range(n_baskets):
        if not eligible:
            break
        basket_size = int(rng.choice([1, 2, 3, 4], p=[0.55, 0.27, 0.12, 0.06]))
        basket_size = min(basket_size, len(eligible))
        chosen = rng.choice(eligible, size=basket_size, replace=False, p=weights)

        order_counter += 1
        oid = f"CMD{order_counter:08d}"
        cust = customer_ids[rng.integers(0, N_CUSTOMERS := len(customer_ids))]
        status = rng.choice(["confirmee", "annulee", "retournee"], p=[0.95, 0.03, 0.02])

        for pid in chosen:
            current_stock = stock_state[pid]
            if current_stock <= 0:
                continue
            qty = int(rng.choice([1, 2, 3, 4, 5], p=[0.55, 0.22, 0.12, 0.07, 0.04]))
            qty = min(qty, current_stock)
            if qty <= 0:
                continue

            # FIX BUG 1 : discount ET promotion_id viennent de la MÊME entrée, jamais désynchronisés
            discount, promo_id = promo_lookup.get((pid, d_date), (0, None))
            unit_price = round(base_price_of[pid] * (1 - discount / 100.0) * float(rng.uniform(0.98, 1.02)), 0)

            line_counter += 1
            transactions.append({
                "ligne_id_origine": f"L{line_counter:08d}",
                "order_id": oid,
                "order_status": status,
                "customer_id": cust,
                "product_id": pid,
                "order_date": d_date.isoformat(),
                "quantity": qty,
                "unit_price_xof": unit_price,
                "promotion_id": promo_id,
                "discount_pct_applied": discount,
            })
            stock_state[pid] = current_stock - qty
            # tous statuts confondus : le stock est décrémenté à l'achat, avant qu'une
            # éventuelle annulation/retour ne soit connue (convention documentée)
            sold_today[pid] = sold_today.get(pid, 0) + qty

    # réapprovisionnement fin de journée — quantité tracée explicitement cette fois
    for pid in pid_array:
        if launch_of[pid] > d:
            continue
        cs = stock_state[pid]
        restock_qty = 0
        if cs <= REORDER_POINT:
            restock_qty = int(rng.integers(*RESTOCK_QTY_RANGE))
            cs += restock_qty
            stock_state[pid] = cs
        stock_rows.append({
            "product_id": pid,
            "date": d_date.isoformat(),
            "stock_level": cs,
            "quantite_vendue": sold_today.get(pid, 0),
            "quantite_reapprovisionnee": restock_qty,
        })

    if d.day == 1:
        print(f"  ... {d_date} traité ({order_counter} commandes, {line_counter} lignes cumulées)")

fact = pd.DataFrame(transactions)
stock_daily = pd.DataFrame(stock_rows)

print(f"\n{len(fact)} lignes produit générées dans {fact['order_id'].nunique()} commandes.")

fact.to_csv(OUT_DIR / "fact_transactions.csv.gz", index=False, compression="gzip")
stock_daily.to_csv(OUT_DIR / "stock_daily.csv.gz", index=False, compression="gzip")
print(f"Sauvegardé : fact_transactions.csv.gz ({len(fact)} lignes)")
print(f"Sauvegardé : stock_daily.csv.gz ({len(stock_daily)} lignes, avec quantite_vendue + quantite_reapprovisionnee)")
