"""Pipeline de préparation — construit la table analytique produit × jour.

    python -m src.pipelines.prepare [--refresh]

Entrée  : cache Parquet des tables sources (cf. `src.pipelines.extract`)
Sortie  : ``data/processed/table_analytique.parquet`` + rapport de construction
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.config.settings import PROJECT_ROOT, load_config
from src.data.build_dataset import (
    DatasetSpec,
    UnresolvedColumnError,
    build_analytical_table,
    parse_date_key,
)
from src.data.build_pricing_dataset import build_pricing_dataset
from src.data.extract import load_cached
from src.data.mapping import best_join_column, normalize
from src.features.stock import build_stock_features, censorship_mask
from src.features.promotions import (
    PromotionSchema,
    aggregate_promo_calendar,
    build_promo_calendar,
    resolve_scope_attributes,
    verify_promo_calendar,
)
from src.utils.logging_utils import get_logger, setup_logging

logger = get_logger(__name__)


def _mapping_from_reports() -> dict[str, dict[str, Any]]:
    """Mapping validé par l'audit (rapport JSON), sinon erreur explicite."""
    snapshot_path = PROJECT_ROOT / "reports" / "audit_snapshot.json"
    if not snapshot_path.exists():
        raise FileNotFoundError(
            "Rapport d'audit introuvable. Lancez d'abord : python -m src.pipelines.audit"
        )
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    return payload["mapping"]


SCD_START_NAMES = {
    "valid_from",
    "date_debut_validite",
    "debut_validite",
    "effective_from",
    "date_effet",
}


def detect_validity_start(products: pd.DataFrame) -> str | None:
    """Colonne de début de validité de la dimension produit.

    Sa signification métier exacte n'est pas prouvable ici (ni commentaire de
    colonne, ni migration, ni documentation). Elle est donc nommée
    ``date_debut_validite`` en aval, **jamais** ``date_lancement``.
    """
    for col in products.columns:
        if normalize(col) in SCD_START_NAMES and pd.api.types.is_datetime64_any_dtype(
            products[col]
        ):
            return col
    return None


def build_spec(
    mapping: dict[str, dict[str, Any]], cfg, products: pd.DataFrame, sales: pd.DataFrame
) -> DatasetSpec:
    """Construit la description des colonnes, config YAML prioritaire."""
    ventes = mapping.get("ventes", {})
    produit = mapping.get("produit", {})
    web = mapping.get("web", {})
    override = cfg.get("schema_mapping", {}) or {}

    def pick(logical: str, cfg_key: str, default: Any) -> Any:
        configured = (override.get(logical) or {}).get(cfg_key)
        return configured or default

    # La clé de la dimension produit est celle dont les valeurs joignent
    # réellement avec la table de faits (clé de substitution), jamais la clé
    # naturelle — que le nom pourrait pourtant désigner tout aussi bien.
    fact_product_key = pick("ventes", "product_key", ventes.get("product_key"))
    if fact_product_key not in sales.columns:
        raise UnresolvedColumnError(
            f"Clé produit '{fact_product_key}' absente de la table de ventes "
            f"(colonnes : {list(sales.columns)})."
        )
    detected, overlap = best_join_column(sales[fact_product_key], products, min_overlap=0.0)
    dim_key = pick("produit", "key", detected)
    if not dim_key:
        raise UnresolvedColumnError(
            "Aucune colonne de dim_produit ne joint avec "
            f"fact.{fact_product_key} (meilleur recouvrement {overlap:.1%})."
        )
    if not products[dim_key].is_unique:
        raise UnresolvedColumnError(
            f"La clé de jointure produit '{dim_key}' n'est pas unique dans la "
            "dimension : la jointure dupliquerait des lignes de vente."
        )
    logger.info(
        "Clé de jointure produit : fact.%s -> dim.%s (recouvrement %.1f%%)",
        fact_product_key,
        dim_key,
        100 * overlap,
    )

    validity = pick("produit", "validity_start", None) or detect_validity_start(products)
    if validity:
        logger.info(
            "Début de validité produit : `%s` (signification non prouvée -> "
            "exposée sous le nom `date_debut_validite`).",
            validity,
        )

    return DatasetSpec(
        sales_table=ventes.get("table"),
        product_key=fact_product_key,
        date_key=pick("ventes", "date_column", ventes.get("date")),
        quantity=pick("ventes", "quantity_column", ventes.get("quantity")),
        amount=pick("ventes", "amount_column", ventes.get("amount")),
        promo_key=pick("ventes", "promotion_key", ventes.get("promotion_key")),
        product_dim_key=dim_key,
        product_natural_id=None,  # résolu ensuite via les cibles de portée produit
        category=pick("produit", "category", produit.get("category")),
        brand=pick("produit", "brand", produit.get("brand")),
        label=pick("produit", "label", produit.get("label")),
        catalog_price=pick("produit", "unit_price", produit.get("unit_price")),
        validity_start=validity,
        web_product_key=web.get("product_key"),
        web_date_key=web.get("date"),
        web_event_type=pick("web", "event_type_column", web.get("event_type")),
    )


def run_prepare() -> tuple[pd.DataFrame, dict[str, Any]]:
    cfg = load_config()
    setup_logging(
        level=cfg.get("logging.level", "INFO"),
        json_output=bool(cfg.get("logging.json", False)),
        log_file=PROJECT_ROOT / cfg.get("logging.file", "reports/logs/pipeline.log"),
    )
    mapping = _mapping_from_reports()
    sales = load_cached(mapping["ventes"]["table"])
    products = load_cached(mapping["produit"]["table"])
    promotions = load_cached(mapping["promotion"]["table"])
    web = load_cached(mapping["web"]["table"]) if mapping.get("web", {}).get("table") else None

    spec = build_spec(mapping, cfg, products, sales)

    # --- Calendrier promotionnel ------------------------------------------
    promo_cfg = cfg.get("promotions", {}) or {}
    promo_map = mapping.get("promotion", {})
    scope_col = promo_cfg.get("scope_column") or _first_present(
        promotions, ["scope", "portee", "niveau"]
    )
    target_col = promo_cfg.get("target_column") or _first_present(
        promotions, ["cible", "target", "valeur"]
    )
    if not scope_col or not target_col:
        raise UnresolvedColumnError(
            "Portée et/ou cible de promotion introuvables dans "
            f"{promo_map.get('table')} (colonnes : {list(promotions.columns)}). "
            "Renseignez promotions.scope_column / promotions.target_column dans "
            "config/config.yaml."
        )

    # Chaque portée est résolue avec ses seules cibles : mélanger les cibles
    # de toutes les portées ferait passer `categorie` pour un identifiant produit.
    scope_map = promo_cfg.get("scope_to_attribute") or resolve_scope_attributes(
        promotions, products, scope_col, target_col
    )
    if not scope_map:
        raise UnresolvedColumnError(
            "Aucune portée de promotion n'a pu être rattachée à un attribut produit."
        )

    # La clé naturelle produit est celle que ciblent les promotions de portée
    # produit — et elle doit être unique dans la dimension.
    product_scopes = [s for s in scope_map if str(s).lower() in {"product", "produit", "sku"}]
    natural_id = promo_cfg.get("product_natural_id") or (
        scope_map[product_scopes[0]] if product_scopes else None
    )
    if natural_id and not products[natural_id].is_unique:
        raise UnresolvedColumnError(
            f"La colonne '{natural_id}' retenue comme identifiant produit naturel "
            "n'est pas unique dans la dimension : elle ne peut pas identifier un produit."
        )
    spec.product_natural_id = natural_id
    logger.info("Identifiant produit naturel retenu : %s", natural_id)

    schema = PromotionSchema(
        key=promo_map.get("promotion_key"),
        scope=scope_col,
        target=target_col,
        start=promo_map.get("start_date"),
        end=promo_map.get("end_date"),
        discount=promo_map.get("discount_rate"),
        scope_to_product_attribute=scope_map,
    )
    raw_calendar = build_promo_calendar(
        promotions, products, schema, product_id_col=spec.product_dim_key
    )
    if raw_calendar.empty:
        raise UnresolvedColumnError(
            "Le calendrier promotionnel reconstruit est vide alors que "
            f"{len(promotions)} promotions sont déclarées : vérifiez la résolution "
            f"des portées ({scope_map})."
        )
    promo_calendar_agg = aggregate_promo_calendar(
        raw_calendar, schema, spec.product_dim_key
    ).rename(columns={spec.product_dim_key: "unique_id"})
    logger.info(
        "Calendrier promotionnel : %s couples produit×jour en promotion.",
        f"{len(promo_calendar_agg):,}",
    )

    # Vérification : le calendrier, construit uniquement depuis dim_promotion,
    # doit couvrir toutes les ventes réellement marquées en promotion.
    sales_dated = sales.copy()
    sales_dated["_ds"] = parse_date_key(sales_dated[spec.date_key])
    verification = verify_promo_calendar(
        sales_dated,
        promo_calendar_agg.rename(columns={"unique_id": spec.product_key}),
        product_col=spec.product_key,
        date_col="_ds",
        sale_promo_key=spec.promo_key,
    )
    logger.info("Vérification du calendrier promo : %s", verification)
    if verification.get("rappel_calendrier", 0) < 0.999:
        raise UnresolvedColumnError(
            "Le calendrier promotionnel ne couvre que "
            f"{verification['rappel_calendrier']:.1%} des ventes promues : "
            "la reconstruction est incomplète."
        )

    table, report = build_analytical_table(
        sales, products, spec, promo_calendar=promo_calendar_agg, web=web
    )
    report.promo_verification = verification

    # --- Stock (livraison du 2026-08-13) -----------------------------------
    # `niveau_stock` est un stock de FIN de journée : les variables dérivées
    # sont construites décalées d'un jour (src/features/stock.py) pour ne
    # jamais exposer au modèle le stock du jour même qu'il doit prévoir.
    stock_map = mapping.get("stock", {})
    if stock_map.get("table"):
        stock_raw = load_cached(stock_map["table"])
        stock_raw["_ds"] = parse_date_key(stock_raw[stock_map["date"]])
        stock_input = stock_raw.rename(
            columns={stock_map["product_key"]: "unique_id", stock_map["stock_level"]: "niveau_stock"}
        )[["unique_id", "_ds", "niveau_stock"]].rename(columns={"_ds": "ds"})
        stock_input["unique_id"] = stock_input["unique_id"].astype(str)

        stock_features = build_stock_features(stock_input)
        before = len(table)
        table = table.merge(stock_features, on=["unique_id", "ds"], how="left")
        assert len(table) == before, "La jointure stock a modifié le nombre de lignes."
        table["jour_censure_stock"] = censorship_mask(table, table["y"])

        taux_couverture = table["stock_fin_jour"].notna().mean()
        taux_rupture = table["indicateur_rupture_lag1"].dropna().astype(int).mean()
        report.notes.append(
            f"Stock intégré ({stock_map['table']}) : {taux_couverture:.1%} des lignes "
            f"couvertes. Taux de rupture mesuré (stock de la veille sous le seuil "
            f"documenté de 20 unités) : {taux_rupture:.4%}. Constat du 2026-08-13 : "
            "ce taux est quasi nul dans cette livraison — voir "
            "reports/13_validation_stock.md. `jour_censure_stock` reste construit "
            "correctement pour rester valide si une future livraison en contient."
        )
    else:
        report.notes.append(
            "Aucune table de stock disponible : jour_censure_stock non calculé."
        )

    processed = PROJECT_ROOT / cfg.get("paths.data_processed", "data/processed")
    processed.mkdir(parents=True, exist_ok=True)
    out_path = processed / "table_analytique.parquet"
    table.to_parquet(out_path, index=False)

    # --- Dataset pricing -----------------------------------------------
    cout_par_produit = (
        products.assign(**{spec.product_dim_key: products[spec.product_dim_key].astype(str)})
        .set_index(spec.product_dim_key)["cout_xof"]
    )
    pricing, pricing_report = build_pricing_dataset(table, cout_par_produit)
    pricing_path = processed / "table_pricing.parquet"
    pricing.to_parquet(pricing_path, index=False)
    logger.info(
        "Table pricing : %s lignes, marge totale %.0f XOF, %s",
        f"{len(pricing):,}",
        pricing_report.marge_totale_xof,
        pricing_report.notes,
    )

    payload = {
        "genere_le": datetime.now(timezone.utc).isoformat(),
        "chemin": str(out_path.relative_to(PROJECT_ROOT)),
        "colonnes": list(map(str, table.columns)),
        "spec": {k: v for k, v in spec.__dict__.items()},
        **report.to_dict(),
    }
    (PROJECT_ROOT / "reports" / "03_table_analytique.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    logger.info(
        "Table analytique : %s lignes, %s produits, %s -> %s (%.1f%% de jours à zéro)",
        f"{len(table):,}",
        report.n_products,
        report.date_min.date(),
        report.date_max.date(),
        100 * report.zero_share,
    )
    return table, payload


def _first_present(df: pd.DataFrame, candidates: list[str]) -> str | None:
    for name in candidates:
        if name in df.columns:
            return name
    return None




def main() -> None:
    parser = argparse.ArgumentParser(description="Construit la table analytique.")
    parser.parse_args()
    run_prepare()


if __name__ == "__main__":
    main()
