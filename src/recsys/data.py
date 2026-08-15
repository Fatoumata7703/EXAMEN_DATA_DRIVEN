"""Chargement des données Recommandation V1 — lecture seule, mise en cache
locale pour éviter de re-solliciter la source à chaque itération.

Contraintes structurelles vérifiées à l'audit (2026-08-14, cf.
`reports/36_recsys_eligibilite.md`), imposées partout dans ce module :

* `vente_id` est une ligne de vente, jamais une commande — aucune
  reconstruction de panier multi-produits n'est tentée.
* Ni `order_id`, ni `session_id` métier, ni `event_timestamp` n'existent
  dans le schéma — aucune règle "achetés ensemble" ni recommandation
  séquentielle n'est construite.
* `client_key` est réellement présent et rempli à 100 % dans
  `fact_evenements_web` (vérifié, pas supposé) — les événements web sont
  donc attribuables aux clients sans fabrication.
* Le stock utilisé pour l'éligibilité produit est toujours strictement
  antérieur à la date de recommandation (J-1 au plus tard), jamais
  contemporain.
"""

from __future__ import annotations

import pandas as pd

from src.config.settings import PROJECT_ROOT

CACHE_DIR = PROJECT_ROOT / "data" / "interim" / "recsys_raw"


def _cache_or_fetch(table: str) -> pd.DataFrame:
    path = CACHE_DIR / f"{table}.parquet"
    if path.exists():
        return pd.read_parquet(path)
    from src.data.connection import get_data_source

    df = get_data_source().fetch_table(table)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    return df


def load_raw() -> dict[str, pd.DataFrame]:
    tables = {}
    for t in ("fact_ventes", "fact_evenements_web", "dim_client", "dim_produit", "dim_date", "dim_promotion", "fact_stock"):
        tables[t] = _cache_or_fetch(t)
    return tables


def build_ventes(tables: dict[str, pd.DataFrame] | None = None) -> pd.DataFrame:
    tables = tables or load_raw()
    ventes = tables["fact_ventes"].copy()
    dates = tables["dim_date"][["date_key", "date_complete"]]
    produits = tables["dim_produit"][["produit_key", "product_id", "categorie", "marque", "prix_base_xof", "cout_xof"]]
    ventes = ventes.merge(dates, on="date_key", how="left")
    ventes = ventes.merge(produits, on="produit_key", how="left")
    ventes["date_complete"] = pd.to_datetime(ventes["date_complete"])
    ventes["quantite"] = ventes["quantite"].astype(int)
    ventes["montant_net_xof"] = pd.to_numeric(ventes["montant_net_xof"], errors="coerce")
    ventes["prix_base_xof"] = pd.to_numeric(ventes["prix_base_xof"], errors="coerce")
    return ventes


def build_web(tables: dict[str, pd.DataFrame] | None = None) -> pd.DataFrame:
    tables = tables or load_raw()
    web = tables["fact_evenements_web"].copy()
    dates = tables["dim_date"][["date_key", "date_complete"]]
    web = web.merge(dates, on="date_key", how="left")
    web["date_complete"] = pd.to_datetime(web["date_complete"])
    return web


def build_stock(tables: dict[str, pd.DataFrame] | None = None) -> pd.DataFrame:
    tables = tables or load_raw()
    stock = tables["fact_stock"].copy()
    dates = tables["dim_date"][["date_key", "date_complete"]]
    stock = stock.merge(dates, on="date_key", how="left")
    stock["date_complete"] = pd.to_datetime(stock["date_complete"])
    return stock


class WindowSpec:
    def __init__(self, index: int, label: str, train_end: pd.Timestamp, test_days: int = 60):
        self.index = index
        self.label = label
        self.train_end = train_end
        self.test_start = train_end + pd.Timedelta(days=1)
        self.test_end = train_end + pd.Timedelta(days=test_days)


# Fenêtres 1-3 : mêmes coupures que le pricing (comparabilité inter-phases).
# Fenêtre 0 : coupure précoce dédiée au cold-start réel — à ces trois dates
# tardives, 0 client n'a un historique train vide (vérifié empiriquement),
# donc le cold-start n'y est pas observable. À 2025-05-01, 971 clients n'ont
# encore aucun achat, dont 717 en font un dans les 60 jours suivants —
# échantillon suffisant pour évaluer ce segment séparément.
WINDOWS = [
    WindowSpec(0, "cold_start_dediee", pd.Timestamp("2025-05-01")),
    WindowSpec(1, "principale_1", pd.Timestamp("2026-02-01")),
    WindowSpec(2, "principale_2", pd.Timestamp("2026-04-02")),
    WindowSpec(3, "principale_3", pd.Timestamp("2026-06-01")),
]
