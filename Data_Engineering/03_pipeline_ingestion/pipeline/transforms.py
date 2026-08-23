"""
Logique métier du pipeline d'ingestion : Raw -> Bronze -> Silver -> Gold.

Ce module ne dépend PAS d'Airflow : chaque fonction prend des entrées explicites et
retourne des chemins/dicts simples. Le DAG Airflow (dags/ecommerce_lake_ingestion_dag.py)
n'est qu'une fine couche d'orchestration au-dessus de ces fonctions — ce qui permet de
les tester en local (voir run_local_test.py) sans avoir Airflow installé.

Le contrôle qualité (`run_dq_checkpoint`) est ICI un garde-fou minimal codé à la main.
Il sera remplacé à l'étape suivante par une vraie suite great_expectations, sans changer
la structure du pipeline : c'est tout l'intérêt de l'avoir isolé dans sa propre fonction,
appelée comme un gate à l'intérieur de `load_silver`.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd

# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------
SOURCE_DIR = Path("/home/claude/airflow_project/source_exports")
LAKE_ROOT = Path("/home/claude/airflow_project/lake")

SOURCE_FILES = {
    "dim_products": "dim_products.csv",
    "dim_customers": "dim_customers.csv",
    "promotions": "promotions.csv",
    "fact_transactions": "fact_transactions.csv.gz",
    "stock_daily": "stock_daily.csv.gz",
    "web_events": "web_events.csv.gz",
}

RAW_TABLES = list(SOURCE_FILES.keys())

# seuil au-delà duquel le pipeline s'arrête plutôt que de laisser passer des
# données trop dégradées vers Silver — à ajuster table par table si besoin
DEFAULT_ERROR_THRESHOLD = 0.10


# ----------------------------------------------------------------------------
# RAW
# ----------------------------------------------------------------------------
def extract_to_raw(table: str, ds: str) -> dict:
    """Copie brute et immuable de la source vers la zone Raw, partitionnée par date d'ingestion."""
    src = SOURCE_DIR / SOURCE_FILES[table]
    dest_dir = LAKE_ROOT / "raw" / table / f"ds={ds}"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / SOURCE_FILES[table]
    shutil.copy(src, dest)
    return {"table": table, "path": str(dest), "ds": ds}


# ----------------------------------------------------------------------------
# BRONZE
# ----------------------------------------------------------------------------
def _read_any(path: Path) -> pd.DataFrame:
    if str(path).endswith(".gz"):
        return pd.read_csv(path, compression="gzip", low_memory=False)
    return pd.read_csv(path, low_memory=False)


DATE_COLUMNS = {
    "order_date", "event_timestamp", "date", "signup_date",
    "launch_date", "start_date", "end_date",
}


def load_bronze(ctx: dict) -> dict:
    """Standardisation : colonnes en minuscules, types corrects, dédoublonnage strict.
    Aucune règle métier ici — uniquement de la propreté technique."""
    table, ds = ctx["table"], ctx["ds"]
    df = _read_any(Path(ctx["path"]))
    df.columns = [c.strip().lower() for c in df.columns]
    df = df.drop_duplicates()
    for col in df.columns:
        if col in DATE_COLUMNS:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    dest_dir = LAKE_ROOT / "bronze" / table / f"ds={ds}"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{table}.csv"
    df.to_csv(dest, index=False)
    return {"table": table, "path": str(dest), "ds": ds, "n_rows": len(df)}


# ----------------------------------------------------------------------------
# QUALITY GATE (placeholder — sera remplacé par great_expectations)
# ----------------------------------------------------------------------------
def run_dq_checkpoint(df: pd.DataFrame, table: str) -> dict:
    """Garde-fou minimal codé à la main, en attendant la vraie suite great_expectations.
    Retourne un masque des lignes en anomalie + des notes lisibles pour les logs."""
    issues = pd.Series(False, index=df.index)
    notes = []

    dup = df.duplicated()
    if dup.any():
        issues |= dup
        notes.append(f"{dup.sum()} doublons exacts")

    if table == "fact_transactions":
        neg_qty = df["quantity"] < 1
        issues |= neg_qty
        notes.append(f"{neg_qty.sum()} quantités invalides (< 1)")

        known_products = pd.read_csv(SOURCE_DIR / "dim_products.csv")["product_id"]
        orphan = ~df["product_id"].isin(known_products)
        issues |= orphan
        notes.append(f"{orphan.sum()} product_id orphelins")

        bad_status = ~df["order_status"].isin(["confirmee", "annulee", "retournee"])
        issues |= bad_status
        notes.append(f"{bad_status.sum()} order_status invalides")

    if table == "stock_daily":
        neg_stock = df["stock_level"] < 0
        neg_sold = df["quantite_vendue"] < 0
        neg_restock = df["quantite_reapprovisionnee"] < 0
        issues |= neg_stock | neg_sold | neg_restock
        notes.append(f"{neg_stock.sum()} stock_level négatifs, {neg_sold.sum()} quantite_vendue négatifs, "
                     f"{neg_restock.sum()} quantite_reapprovisionnee négatifs")

    if table == "web_events":
        known_products = pd.read_csv(SOURCE_DIR / "dim_products.csv")["product_id"]
        orphan = ~df["product_id"].isin(known_products)
        issues |= orphan
        notes.append(f"{orphan.sum()} product_id orphelins")

        bad_event_type = ~df["event_type"].isin(["view", "add_to_cart", "purchase"])
        issues |= bad_event_type
        notes.append(f"{bad_event_type.sum()} event_type invalides")

    if table == "dim_customers":
        missing = df["age_bracket"].isna() | df["region"].isna()
        notes.append(f"{missing.sum()} lignes avec région/tranche d'âge manquante (non rejetées, juste signalées)")

    if table == "dim_products":
        bad_case = df["category"].str.isupper()
        notes.append(f"{bad_case.sum()} catégories en casse incohérente (non rejetées, juste signalées)")

    return {"issues_mask": issues, "notes": notes, "error_rate": float(issues.mean()) if len(df) else 0.0}


# ----------------------------------------------------------------------------
# SILVER
# ----------------------------------------------------------------------------
def load_silver(ctx: dict, error_threshold: float = DEFAULT_ERROR_THRESHOLD) -> dict:
    """Applique le gate qualité : les lignes propres vont en Silver, les lignes en
    anomalie sont isolées dans silver_rejects/ pour investigation, sans bloquer le
    pipeline — sauf si le taux d'erreur dépasse error_threshold."""
    table, ds = ctx["table"], ctx["ds"]
    df = pd.read_csv(ctx["path"], low_memory=False)

    report = run_dq_checkpoint(df, table)
    if report["error_rate"] > error_threshold:
        raise ValueError(
            f"[{table}] taux d'erreur {report['error_rate']:.1%} > seuil {error_threshold:.0%} "
            f"— pipeline arrêté, à investiguer avant de continuer. Détail : {report['notes']}"
        )

    clean = df[~report["issues_mask"]]
    rejects = df[report["issues_mask"]]

    silver_dir = LAKE_ROOT / "silver" / table / f"ds={ds}"
    silver_dir.mkdir(parents=True, exist_ok=True)
    dest = silver_dir / f"{table}.csv"
    clean.to_csv(dest, index=False)

    if len(rejects):
        rej_dir = LAKE_ROOT / "silver_rejects" / table / f"ds={ds}"
        rej_dir.mkdir(parents=True, exist_ok=True)
        rejects.to_csv(rej_dir / f"{table}_rejects.csv", index=False)

    print(f"[{table}] silver : {len(clean)} lignes valides, {len(rejects)} rejetées. Notes : {report['notes']}")
    return {"table": table, "path": str(dest), "ds": ds, "n_rows": len(clean), "n_rejected": len(rejects)}


# ----------------------------------------------------------------------------
# GOLD
# ----------------------------------------------------------------------------
def build_gold_tables(silver_ctxs: list[dict]) -> dict:
    """Point d'entrée gold : matérialise d'abord le schéma en étoile, puis calcule
    des tables agrégées de confort (marts) à partir des tables Silver."""
    star_paths = build_star_schema(silver_ctxs)

    paths = {c["table"]: c["path"] for c in silver_ctxs}
    gold_dir = LAKE_ROOT / "gold"
    gold_dir.mkdir(parents=True, exist_ok=True)

    fact = pd.read_csv(paths["fact_transactions"])
    fact["order_date"] = pd.to_datetime(fact["order_date"])
    fact["revenue_xof"] = fact["quantity"] * fact["unit_price_xof"]

    daily = (
        fact.groupby(["product_id", fact["order_date"].dt.date])
        .agg(quantity=("quantity", "sum"), revenue_xof=("revenue_xof", "sum"))
        .reset_index()
        .rename(columns={"order_date": "date"})
    )
    daily.to_csv(gold_dir / "daily_sales_by_product.csv", index=False)

    perf = (
        fact.groupby("product_id")
        .agg(
            total_qty=("quantity", "sum"),
            total_revenue_xof=("revenue_xof", "sum"),
            avg_price_xof=("unit_price_xof", "mean"),
            n_orders=("order_id", "count"),
        )
        .reset_index()
    )
    perf.to_csv(gold_dir / "product_performance.csv", index=False)

    print(f"[gold] daily_sales_by_product : {len(daily)} lignes | product_performance : {len(perf)} produits")
    return {
        **star_paths,
        "daily_sales_by_product": str(gold_dir / "daily_sales_by_product.csv"),
        "product_performance": str(gold_dir / "product_performance.csv"),
    }


# ----------------------------------------------------------------------------
# GOLD — SCHÉMA EN ÉTOILE (dimensions + tables de faits)
# ----------------------------------------------------------------------------
def _normalize_category(series: pd.Series) -> pd.Series:
    """Corrige la casse incohérente en mappant chaque catégorie vers sa forme
    canonique (la plus fréquente), plutôt que de se contenter de la signaler."""
    canon = series.str.strip()
    # forme canonique = la variante la plus fréquente pour chaque catégorie en minuscules
    mapping = (
        canon.groupby(canon.str.lower()).agg(lambda s: s.value_counts().idxmax())
    )
    return canon.str.lower().map(mapping)


def build_star_schema(silver_ctxs: list[dict]) -> dict:
    """Matérialise le schéma en étoile : dim_produit, dim_client, dim_date,
    dim_promotion, fact_ventes, fact_evenements_web — à partir des tables Silver.

    dim_produit et dim_client portent les colonnes SCD Type 2 (valid_from, valid_to,
    is_current). À ce stade on n'a qu'un seul snapshot de chaque, donc toutes les
    lignes sont is_current=True avec valid_to=NaT — la structure est prête à recevoir
    de nouvelles versions au fil des futurs runs du pipeline.
    """
    paths = {c["table"]: c["path"] for c in silver_ctxs}
    dwh_dir = LAKE_ROOT / "gold" / "star_schema"
    dwh_dir.mkdir(parents=True, exist_ok=True)

    # --- DIM_PRODUIT --------------------------------------------------------
    products = pd.read_csv(paths["dim_products"])
    products["category"] = _normalize_category(products["category"])
    products = products.reset_index(drop=True)
    dim_produit = pd.DataFrame({
        "produit_key": [f"PRD{i:06d}" for i in range(len(products))],
        "product_id": products["product_id"],
        "product_name": products["product_name"],
        "categorie": products["category"],
        "marque": products["brand"],
        "prix_base_xof": products["base_price_xof"],
        "cout_xof": products["cost_xof"],
        "valid_from": products["launch_date"],
        "valid_to": pd.NaT,
        "is_current": True,
    })
    dim_produit.to_csv(dwh_dir / "dim_produit.csv", index=False)

    # --- DIM_CLIENT ----------------------------------------------------------
    customers = pd.read_csv(paths["dim_customers"]).reset_index(drop=True)
    dim_client = pd.DataFrame({
        "client_key": [f"CLI{i:06d}" for i in range(len(customers))],
        "customer_id": customers["customer_id"],
        "region": customers["region"].fillna("Non renseigné"),
        "age_bracket": customers["age_bracket"].fillna("Non renseigné"),
        "segment_fidelite": customers["loyalty_segment"],
        "valid_from": customers["signup_date"],
        "valid_to": pd.NaT,
        "is_current": True,
    })
    dim_client.to_csv(dwh_dir / "dim_client.csv", index=False)

    # --- DIM_PROMOTION ---------------------------------------------------------
    promos = pd.read_csv(paths["promotions"]).reset_index(drop=True)
    dim_promotion = pd.DataFrame({
        "promo_key": [f"PRM{i:04d}" for i in range(len(promos))],
        "promotion_id": promos["promotion_id"],
        "portee": promos["scope"],
        "cible": promos["target"],
        "remise_pct": promos["discount_pct"],
        "date_debut": promos["start_date"],
        "date_fin": promos["end_date"],
    })
    dim_promotion.to_csv(dwh_dir / "dim_promotion.csv", index=False)

    # --- DIM_DATE --------------------------------------------------------------
    fact_tx = pd.read_csv(paths["fact_transactions"], low_memory=False)
    web = pd.read_csv(paths["web_events"], low_memory=False)
    fact_tx["order_date"] = pd.to_datetime(fact_tx["order_date"])
    web["event_date"] = pd.to_datetime(web["event_timestamp"]).dt.tz_localize(None).dt.normalize()
    all_dates = pd.concat([fact_tx["order_date"], web["event_date"]])
    date_range = pd.date_range(all_dates.min(), all_dates.max(), freq="D")
    dim_date = pd.DataFrame({
        "date_key": date_range.strftime("%Y%m%d"),
        "date_complete": date_range,
        "annee": date_range.year,
        "mois": date_range.month,
        "jour": date_range.day,
        "jour_semaine": date_range.day_name(),
        "est_weekend": date_range.dayofweek >= 5,
    })
    dim_date.to_csv(dwh_dir / "dim_date.csv", index=False)

    # --- lookups pour les jointures --------------------------------------------
    produit_lookup = dim_produit.set_index("product_id")["produit_key"]
    client_lookup = dim_client.set_index("customer_id")["client_key"]
    promo_lookup = dim_promotion.set_index("promotion_id")["promo_key"]

    # --- FACT_VENTES -------------------------------------------------------------
    fact_ventes = pd.DataFrame({
        "vente_id": fact_tx["ligne_id_origine"],  # identifiant de LIGNE, pas de panier
        "produit_key": fact_tx["product_id"].map(produit_lookup),
        "client_key": fact_tx["customer_id"].map(client_lookup),
        "date_key": fact_tx["order_date"].dt.strftime("%Y%m%d"),
        "promo_key": fact_tx["promotion_id"].map(promo_lookup),  # NaN si pas de promo, voulu
        "quantite": fact_tx["quantity"],
        "montant_net_xof": fact_tx["quantity"] * fact_tx["unit_price_xof"],
        "order_id": fact_tx["order_id"],  # identifiant de PANIER, partagé entre plusieurs lignes
        "statut_commande": fact_tx["order_status"],
    })
    n_orphan_produit = fact_ventes["produit_key"].isna().sum()
    n_orphan_client = fact_ventes["client_key"].isna().sum()
    if n_orphan_produit or n_orphan_client:
        print(f"[fact_ventes] ATTENTION : {n_orphan_produit} produit_key et {n_orphan_client} client_key non résolues")
    fact_ventes.to_csv(dwh_dir / "fact_ventes.csv", index=False)

    # --- FACT_EVENEMENTS_WEB -------------------------------------------------------
    web["event_timestamp_dt"] = pd.to_datetime(web["event_timestamp"])
    fact_web = pd.DataFrame({
        "event_id": web["event_id"],
        "session_id": web["session_id"],
        "produit_key": web["product_id"].map(produit_lookup),
        "client_key": web["customer_id"].map(client_lookup),  # NaN pour les sessions anonymes, voulu
        "anonymous_id": web["anonymous_id"],
        "date_key": web["event_timestamp_dt"].dt.strftime("%Y%m%d"),
        "event_timestamp": web["event_timestamp_dt"].dt.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "type_event": web["event_type"],
        "appareil": web["device"],
        "source_trafic": web["referral_source"],
        "canal": web["canal"],
        "order_id": web["order_id"],  # rempli uniquement sur les événements purchase
        "quantity": web["quantity"].astype("Int64"),  # nullable int : évite le bug "1.0"
        "est_bot": web["est_bot"],
    })
    n_orphan_produit_web = fact_web["produit_key"].isna().sum()
    if n_orphan_produit_web:
        print(f"[fact_evenements_web] ATTENTION : {n_orphan_produit_web} produit_key non résolues")
    fact_web.to_csv(dwh_dir / "fact_evenements_web.csv", index=False)

    print(
        f"[star_schema] dim_produit={len(dim_produit)} dim_client={len(dim_client)} "
        f"dim_date={len(dim_date)} dim_promotion={len(dim_promotion)} "
        f"fact_ventes={len(fact_ventes)} fact_evenements_web={len(fact_web)}"
    )

    # --- FACT_STOCK — reconstruite à chaque run, réconciliation exacte possible -------
    stock = pd.read_csv(paths["stock_daily"])
    stock["date"] = pd.to_datetime(stock["date"])
    fact_stock = pd.DataFrame({
        "produit_key": stock["product_id"].map(produit_lookup),
        "date_key": stock["date"].dt.strftime("%Y%m%d"),
        "niveau_stock": stock["stock_level"],
        "quantite_vendue": stock["quantite_vendue"],
        "quantite_reapprovisionnee": stock["quantite_reapprovisionnee"],
    })
    n_orphan_stock = fact_stock["produit_key"].isna().sum()
    if n_orphan_stock:
        print(f"[fact_stock] ATTENTION : {n_orphan_stock} produit_key non résolues")
    fact_stock.to_csv(dwh_dir / "fact_stock.csv", index=False)
    print(f"[fact_stock] {len(fact_stock)} lignes")

    return {
        "dim_produit": str(dwh_dir / "dim_produit.csv"),
        "dim_client": str(dwh_dir / "dim_client.csv"),
        "dim_date": str(dwh_dir / "dim_date.csv"),
        "dim_promotion": str(dwh_dir / "dim_promotion.csv"),
        "fact_ventes": str(dwh_dir / "fact_ventes.csv"),
        "fact_evenements_web": str(dwh_dir / "fact_evenements_web.csv"),
        "fact_stock": str(dwh_dir / "fact_stock.csv"),
    }
