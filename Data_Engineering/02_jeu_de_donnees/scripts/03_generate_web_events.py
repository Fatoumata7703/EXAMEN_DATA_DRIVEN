"""
Étape 3 v3 — corrige 2 bugs identifiés par l'audit du data scientist :

BUG 3 (sessions dépassant 30 min sans coupure) : l'ancienne formule tirait un
multiplicateur aléatoire INDÉPENDANT à chaque vue (ts0 + k_v * v), sans jamais borner
l'écart entre deux événements consécutifs. Fix : les timestamps sont maintenant générés
par petits pas cumulés (1 à 15 min), qui ne peuvent jamais dépasser 30 min entre deux
événements consécutifs, par construction.

BUG 4 (vues après l'achat) : l'ancien compteur de décalage (offset_min) se décrémentait
à chaque vue générée et pouvait devenir négatif pour les paniers à plusieurs produits,
plaçant certaines vues APRÈS l'heure d'achat. Fix : les timestamps des événements
pré-achat sont maintenant construits en remontant depuis l'heure d'achat par petits pas
(1 à 8 min), ce qui garantit par construction qu'ils sont tous strictement avant l'achat,
quelle que soit la taille du panier.
"""
import os
import numpy as np
import pandas as pd
from datetime import timedelta
from pathlib import Path

SEED = 42
rng = np.random.default_rng(SEED)

SOURCE_DIR = Path(os.environ.get("SOURCE_DIR", "/home/claude/livrables_finaux/jeu_de_donnees/donnees"))
ENRICH_DIR = Path(os.environ.get("OUT_DIR", "/home/claude/livrables_finaux/jeu_de_donnees/donnees"))

DEVICES = ["mobile", "desktop", "tablet"]
DEVICE_WEIGHTS = [0.72, 0.22, 0.06]
REFERRALS = ["organic_search", "social_media", "direct", "email_campaign", "paid_ads", "affiliate"]
REFERRAL_WEIGHTS = [0.30, 0.28, 0.18, 0.10, 0.10, 0.04]

N_ANONYMOUS_POOL = 2000

print("Chargement des données déjà générées (v3)...")
fact = pd.read_csv(ENRICH_DIR / "fact_transactions.csv.gz")
customers = pd.read_csv(SOURCE_DIR / "dim_customers.csv")
products = pd.read_csv(SOURCE_DIR / "dim_products.csv")
customer_ids = customers["customer_id"].to_numpy()
product_ids = products["product_id"].to_numpy()
anonymous_pool = [f"ANON{i:06d}" for i in range(N_ANONYMOUS_POOL)]

events = []
event_counter = 0
session_counter = 0


def new_event(session_id, client_key, anonymous_id, product_id, event_type, ts,
              device, referral, canal, order_id=None, quantity=None, est_bot=False):
    global event_counter
    event_counter += 1
    return {
        "event_id": f"E{event_counter:09d}",
        "session_id": session_id,
        "client_key": client_key,
        "anonymous_id": anonymous_id,
        "product_id": product_id,
        "event_type": event_type,
        "event_timestamp": ts.isoformat() + "+00:00",
        "device": device,
        "referral_source": referral,
        "canal": canal,
        "order_id": order_id,
        "quantity": quantity,
        "est_bot": est_bot,
    }


# ----------------------------------------------------------------------------
# 1. Sessions d'achat — timestamps construits EN REMONTANT depuis l'achat,
#    par petits pas bornés (1-8 min) : jamais de sous-flux, jamais > 30 min d'écart.
# ----------------------------------------------------------------------------
print("Génération des sessions d'achat (une par commande, timing corrigé)...")
orders = fact.groupby("order_id")

for order_id, lines in orders:
    session_counter += 1
    sid = f"S{session_counter:09d}"
    customer = lines.iloc[0]["customer_id"]
    order_dt = pd.Timestamp(lines.iloc[0]["order_date"]) + pd.Timedelta(
        hours=int(rng.integers(7, 23)), minutes=int(rng.integers(0, 59))
    )
    device = rng.choice(DEVICES, p=DEVICE_WEIGHTS)
    referral = rng.choice(REFERRALS, p=REFERRAL_WEIGHTS)

    # construire la liste ordonnée des événements pré-achat (view*, add_to_cart) par produit
    pre_purchase = []
    for _, line in lines.iterrows():
        n_views = int(rng.integers(1, 4))
        for _ in range(n_views):
            pre_purchase.append((line["product_id"], "view"))
        pre_purchase.append((line["product_id"], "add_to_cart"))

    # remonter depuis order_dt avec des pas bornés (1-8 min) -> jamais de sous-flux,
    # jamais d'écart consécutif > 30 min, toujours strictement avant l'achat
    ts_cursor = order_dt
    timestamps = []
    for _ in range(len(pre_purchase)):
        gap = int(rng.integers(1, 9))
        ts_cursor = ts_cursor - timedelta(minutes=gap)
        timestamps.append(ts_cursor)
    timestamps.reverse()  # ordre chronologique croissant

    for (pid, etype), ts in zip(pre_purchase, timestamps):
        events.append(new_event(sid, customer, None, pid, etype, ts, device, referral, "web"))

    for _, line in lines.iterrows():
        events.append(new_event(sid, customer, None, line["product_id"], "purchase", order_dt,
                                 device, referral, "web",
                                 order_id=order_id, quantity=int(line["quantity"])))

print(f"{len(events)} événements générés pour {session_counter} sessions d'achat.")

# ----------------------------------------------------------------------------
# 2. Sessions de navigation pure — timestamps construits EN AVANÇANT par petits
#    pas bornés (1-15 min), jamais > 30 min d'écart consécutif.
# ----------------------------------------------------------------------------
print("Génération des sessions de navigation pure (timing corrigé)...")
TARGET_BROWSE_EVENTS = 320_000
n_browse_sessions = 0
browse_event_count = 0

START_DATE = pd.Timestamp("2025-02-01")
N_DAYS = (pd.Timestamp("2026-07-31") - START_DATE).days

while browse_event_count < TARGET_BROWSE_EVENTS:
    session_counter += 1
    n_browse_sessions += 1
    sid = f"S{session_counter:09d}"

    day_offset = int(rng.integers(0, N_DAYS))
    ts0 = START_DATE + timedelta(days=day_offset, hours=int(rng.integers(7, 23)), minutes=int(rng.integers(0, 59)))
    device = rng.choice(DEVICES, p=DEVICE_WEIGHTS)
    referral = rng.choice(REFERRALS, p=REFERRAL_WEIGHTS)

    is_anonymous = rng.random() < 0.35
    client_key = None if is_anonymous else customer_ids[rng.integers(0, len(customer_ids))]
    anon_id = anonymous_pool[rng.integers(0, N_ANONYMOUS_POOL)] if is_anonymous else None

    is_bot = rng.random() < 0.01

    if is_bot:
        n_views = int(rng.integers(15, 40))
        for v in range(n_views):
            ts = ts0 + timedelta(seconds=v * int(rng.integers(1, 3)))
            pid = product_ids[rng.integers(0, len(product_ids))]
            events.append(new_event(sid, client_key, anon_id, pid, "view", ts,
                                     device, "direct", "web", est_bot=True))
        browse_event_count += n_views
        continue

    n_views = int(rng.integers(1, 4))
    reaches_cart = rng.random() < 0.25

    ts_cursor = ts0
    for v in range(n_views):
        if v > 0:
            gap = int(rng.integers(1, 16))  # 1-15 min, toujours << 30
            ts_cursor = ts_cursor + timedelta(minutes=gap)
        pid = product_ids[rng.integers(0, len(product_ids))]
        events.append(new_event(sid, client_key, anon_id, pid, "view", ts_cursor,
                                 device, referral, "web"))
    browse_event_count += n_views

    if reaches_cart:
        gap = int(rng.integers(1, 11))  # 1-10 min, toujours << 30
        ts_cursor = ts_cursor + timedelta(minutes=gap)
        pid = product_ids[rng.integers(0, len(product_ids))]
        events.append(new_event(sid, client_key, anon_id, pid, "add_to_cart", ts_cursor,
                                 device, referral, "web"))
        browse_event_count += 1

print(f"{n_browse_sessions} sessions de navigation pure générées ({browse_event_count} événements).")

web_events = pd.DataFrame(events)
web_events = web_events.rename(columns={"client_key": "customer_id"})  # customer_id au niveau source, pas la clé de substitution (prématuré à ce stade)

out_path = ENRICH_DIR / "web_events.csv.gz"
web_events.to_csv(out_path, index=False, compression="gzip")
print(f"\nTotal : {len(web_events)} événements, {session_counter} sessions.")
print(f"Sauvegardé : {out_path}")
