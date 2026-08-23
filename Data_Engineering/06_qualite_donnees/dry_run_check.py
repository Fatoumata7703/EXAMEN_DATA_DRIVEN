"""
Validation pandas des règles de qualité, en amont de leur implémentation dans
great_expectations (run_data_quality.py). Permet de confirmer que les colonnes et
les seuils utilisés correspondent aux données réellement produites par le pipeline,
indépendamment de l'installation du package great_expectations.
"""
import os
from pathlib import Path

import pandas as pd

SOURCE_DIR = Path(os.environ.get(
    "SOURCE_DIR", str(Path(__file__).resolve().parent.parent / "02_jeu_de_donnees" / "donnees")
))

def load(fname, base=SOURCE_DIR):
    if str(fname).endswith(".gz"):
        return pd.read_csv(f"{base}/{fname}", compression="gzip", low_memory=False)
    return pd.read_csv(f"{base}/{fname}")

dim_products = load("dim_products.csv")
dim_customers = load("dim_customers.csv")
promotions = load("promotions.csv")
fact_transactions = load("fact_transactions.csv.gz")
stock_daily = load("stock_daily.csv.gz")
web_events = load("web_events.csv.gz")

print("=== dim_products ===")
print("product_id uniques:", dim_products["product_id"].is_unique)
print("product_id nulls:", dim_products["product_id"].isna().sum())
print("category nulls:", dim_products["category"].isna().sum())
bad_case = dim_products["category"].str.isupper().sum()
print(f"category en casse anormale (regex ^[A-Z\\s&-]+$ proxy): {bad_case}")

print("\n=== dim_customers ===")
print("customer_id uniques:", dim_customers["customer_id"].is_unique)
print("customer_id nulls:", dim_customers["customer_id"].isna().sum())
region_null_rate = dim_customers["region"].isna().mean()
age_null_rate = dim_customers["age_bracket"].isna().mean()
print(f"region nulls: {region_null_rate:.2%} (seuil mostly=0.90 -> {'OK' if 1-region_null_rate >= 0.90 else 'ECHEC'})")
print(f"age_bracket nulls: {age_null_rate:.2%} (seuil mostly=0.90 -> {'OK' if 1-age_null_rate >= 0.90 else 'ECHEC'})")

print("\n=== promotions ===")
print("promotion_id uniques:", promotions["promotion_id"].is_unique)
print("discount_pct hors [0,100]:", (~promotions["discount_pct"].between(0, 100)).sum())

print("\n=== fact_transactions ===")
print("ligne_id_origine uniques:", fact_transactions["ligne_id_origine"].is_unique)
print("order_id nulls:", fact_transactions["order_id"].isna().sum())
print("order_status hors set:", (~fact_transactions["order_status"].isin(["confirmee","annulee","retournee"])).sum())
print("quantity < 1:", (fact_transactions["quantity"] < 1).sum())
valid_products = set(dim_products["product_id"])
orphan_products = (~fact_transactions["product_id"].isin(valid_products)).sum()
print("product_id hors du référentiel dim_products:", orphan_products)
null_cols = ["ligne_id_origine", "order_id", "customer_id", "product_id", "order_date", "quantity", "unit_price_xof"]
for c in null_cols:
    n = fact_transactions[c].isna().sum()
    if n:
        print(f"  {c} nulls: {n}")

print("\n=== stock_daily ===")
print("stock_level < 0:", (stock_daily["stock_level"] < 0).sum())
print("quantite_vendue < 0:", (stock_daily["quantite_vendue"] < 0).sum())
print("quantite_reapprovisionnee < 0:", (stock_daily["quantite_reapprovisionnee"] < 0).sum())

print("\n=== web_events ===")
valid_events = {"view", "add_to_cart", "purchase"}
print("event_type hors du set autorisé:", (~web_events["event_type"].isin(valid_events)).sum())
orphan_products_web = (~web_events["product_id"].isin(valid_products)).sum()
print("product_id hors du référentiel dim_products:", orphan_products_web)
print("event_id uniques:", web_events["event_id"].is_unique)
