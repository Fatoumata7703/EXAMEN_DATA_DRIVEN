"""Pipeline d'audit (phase 1) — 100 % lecture seule.

    python -m src.pipelines.audit [--refresh] [--limit N] [--no-cache]

Produit :
  * ``reports/01_schema.md``          : schéma réel découvert (tables, colonnes, clés, volumes)
  * ``reports/02_audit_qualite.md``   : contrôles de qualité et diagnostic
  * ``reports/audit_snapshot.json``   : résultats bruts, exploitables par les tests
  * ``reports/mapping_propose.yaml``  : mapping colonne -> rôle métier, à valider
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from src.config.settings import PROJECT_ROOT, load_config
from src.data import audit_checks as checks
from src.data.audit_checks import CheckResult
from src.data.connection import get_data_source
from src.data.extract import extract_all
from src.data.mapping import (
    CONFIG_KEY_BY_ROLE,
    best_join_column,
    mapping_report,
    match_tables,
    merge_with_config,
    propose_mapping,
)
from src.data.schema_inspector import inspect_schema, infer_relations_by_name
from src.utils.logging_utils import get_logger, setup_logging

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Utilitaires de mise en forme
# ---------------------------------------------------------------------------
def df_to_md(df: pd.DataFrame | None, max_rows: int = 40, floatfmt: str = "{:.4g}") -> str:
    if df is None or len(df) == 0:
        return "_(aucune donnée)_\n"
    view = df.head(max_rows).copy()
    for col in view.columns:
        if pd.api.types.is_float_dtype(view[col]):
            view[col] = view[col].map(lambda v: "" if pd.isna(v) else floatfmt.format(v))
    header = "| " + " | ".join(str(c) for c in view.columns) + " |"
    sep = "| " + " | ".join("---" for _ in view.columns) + " |"
    lines = [header, sep]
    for _, row in view.iterrows():
        lines.append("| " + " | ".join("" if pd.isna(v) else str(v) for v in row.tolist()) + " |")
    suffix = f"\n_({len(df)} lignes, {max_rows} affichées)_\n" if len(df) > max_rows else "\n"
    return "\n".join(lines) + "\n" + suffix


STATUS_ICON = {"ok": "🟢", "alerte": "🟠", "critique": "🔴", "non_applicable": "⚪"}


def check_to_md(result: CheckResult) -> str:
    icon = STATUS_ICON.get(result.status, "•")
    out = f"### {icon} {result.name}\n\n{result.summary}\n\n"
    if result.details:
        out += "```\n" + json.dumps(checks._jsonable(result.details), indent=2, ensure_ascii=False) + "\n```\n\n"
    if result.table is not None and len(result.table):
        out += df_to_md(result.table) + "\n"
    return out


# ---------------------------------------------------------------------------
# Préparation des ventes (résolution des dates, quantités, montants)
# ---------------------------------------------------------------------------
@dataclass
class SalesView:
    """Vue normalisée des ventes, avec traçabilité des choix effectués."""

    df: pd.DataFrame
    date_col: str
    product_col: str | None
    quantity_col: str | None
    amount_col: str | None
    notes: list[str]


def resolve_sales(
    frames: dict[str, pd.DataFrame], mapping: dict[str, dict[str, str | None]]
) -> SalesView:
    """Construit une vue des ventes avec une vraie colonne date (``_ds``)."""
    notes: list[str] = []
    ventes_map = mapping.get("ventes", {})
    table = ventes_map.get("table")
    if not table or table not in frames:
        raise RuntimeError("Table de ventes introuvable dans les données extraites.")
    sales = frames[table].copy()

    raw_date = ventes_map.get("date")
    if not raw_date or raw_date not in sales.columns:
        raise RuntimeError(
            f"Aucune colonne de date identifiée dans {table}. "
            f"Renseignez schema_mapping.ventes.date_column dans config/config.yaml."
        )

    series = sales[raw_date]
    is_datetime_like = pd.api.types.is_datetime64_any_dtype(series)
    parsed = pd.to_datetime(series, errors="coerce") if not is_datetime_like else series

    date_map = mapping.get("date", {})
    dim_date_table = date_map.get("table")
    dim_date = frames.get(dim_date_table) if dim_date_table else None

    # Cas 1 : la colonne est déjà une date exploitable
    if parsed.notna().mean() > 0.95 and not pd.api.types.is_numeric_dtype(series):
        sales["_ds"] = pd.to_datetime(parsed).dt.normalize()
        notes.append(f"Date lue directement depuis `{table}.{raw_date}`.")
    # Cas 2 : clé numérique vers dim_date
    elif dim_date is not None and not dim_date.empty:
        dim_date_col = date_map.get("date")
        # On cherche dans dim_date la colonne portant le même nom (normalisé)
        # que la clé de la table de faits, puis la clé primaire déclarée.
        join_key = None
        for candidate in dim_date.columns:
            if checks_normalize(candidate) == checks_normalize(raw_date):
                join_key = candidate
                break
        if join_key is None:
            fallback = date_map.get("line_id")
            if fallback and fallback in dim_date.columns:
                join_key = fallback
        # La colonne date de la dimension ne peut pas être la clé de jointure.
        if dim_date_col == join_key:
            others = [
                c
                for c in dim_date.columns
                if c != join_key and pd.api.types.is_datetime64_any_dtype(dim_date[c])
            ]
            dim_date_col = others[0] if others else None
        if join_key is None or dim_date_col is None:
            raise RuntimeError(
                f"Impossible de résoudre `{table}.{raw_date}` via {dim_date_table} : "
                "clé de jointure ou colonne date de la dimension non identifiée."
            )
        lookup = dim_date[[join_key, dim_date_col]].drop_duplicates()
        sales = sales.merge(
            lookup.rename(columns={join_key: raw_date, dim_date_col: "_ds"}),
            on=raw_date,
            how="left",
        )
        sales["_ds"] = pd.to_datetime(sales["_ds"], errors="coerce").dt.normalize()
        notes.append(
            f"Date résolue par jointure `{table}.{raw_date}` -> "
            f"`{dim_date_table}.{join_key}` -> `{dim_date_col}`."
        )
    else:
        raise RuntimeError(
            f"`{table}.{raw_date}` n'est pas une date exploitable et aucune dimension "
            "date utilisable n'a été trouvée."
        )

    n_bad = int(sales["_ds"].isna().sum())
    if n_bad:
        notes.append(f"{n_bad} ligne(s) sans date exploitable (exclues des analyses temporelles).")

    return SalesView(
        df=sales,
        date_col="_ds",
        product_col=ventes_map.get("product_key"),
        quantity_col=ventes_map.get("quantity"),
        amount_col=ventes_map.get("amount"),
        notes=notes,
    )


def _identity_columns(
    table: str, mapping: dict[str, dict[str, str | None]], df: pd.DataFrame
) -> list[str] | None:
    """Clé d'unicité à tester pour une table, à défaut de clé primaire déclarée.

    On ne se fie pas au nom : on retient la première colonne candidate dont les
    valeurs sont **effectivement uniques**. Sans candidate unique, on ne teste
    aucune clé — signaler des « doublons » sur une clé étrangère de table de
    faits n'aurait aucun sens (une même clé y apparaît légitimement N fois).
    """
    candidates: list[str] = []
    for roles in mapping.values():
        if roles.get("table") != table:
            continue
        for role in ("line_id", "product_key", "promotion_key", "client_key"):
            col = roles.get(role)
            if col and col in df.columns and col not in candidates:
                candidates.append(col)
    candidates += [
        c
        for c in df.columns
        if checks_normalize(c).endswith(("_id", "_key")) and c not in candidates
    ]
    for col in candidates:
        if df[col].is_unique:
            return [col]
    return None


def _scd_start_column(dim: pd.DataFrame) -> str | None:
    """Colonne de début de validité d'une dimension SCD (``valid_from``...).

    Candidate — et seulement candidate — au rôle de date de lancement produit :
    le contrôle `dates_lancement` vérifie ensuite qu'aucune vente ne la précède
    avant de l'utiliser comme telle.
    """
    for col in dim.columns:
        norm = checks_normalize(col)
        if norm in {"valid_from", "date_debut_validite", "debut_validite", "effective_from"}:
            if pd.api.types.is_datetime64_any_dtype(dim[col]):
                return col
    return None


def enrich_sales(
    view: SalesView, frames: dict[str, pd.DataFrame], mapping: dict[str, dict[str, str | None]]
) -> tuple[pd.DataFrame, dict[str, str], list[str]]:
    """Joint les dimensions produit et promotion à la table de faits.

    Nécessaire ici car la table de ventes ne porte ni prix unitaire ni taux de
    remise : ils vivent respectivement dans la dimension produit et la dimension
    promotion. Renvoie (ventes enrichies, colonnes ajoutées par rôle, notes).
    """
    df = view.df
    added: dict[str, str] = {}
    notes: list[str] = []
    ventes_map = mapping.get("ventes", {})

    # --- Dimension produit ------------------------------------------------
    prod_map = mapping.get("produit", {})
    prod_table = prod_map.get("table")
    fact_prod_key = ventes_map.get("product_key")
    if prod_table and prod_table in frames and fact_prod_key in df.columns:
        dim = frames[prod_table]
        # La clé de jointure est déterminée par recouvrement réel des valeurs,
        # pas par le nom : une dimension porte souvent clé de substitution ET
        # clé naturelle, et seule la première joint avec la table de faits.
        join_key, overlap = best_join_column(df[fact_prod_key], dim)
        if join_key:
            notes.append(
                f"Clé de jointure produit retenue : `{prod_table}.{join_key}` "
                f"(recouvrement des valeurs : {overlap:.1%})."
            )
            wanted = {
                "prix_dim": prod_map.get("unit_price"),
                "categorie_dim": prod_map.get("category"),
                "marque_dim": prod_map.get("brand"),
                "libelle_dim": prod_map.get("label"),
                "lancement_dim": prod_map.get("launch_date") or _scd_start_column(dim),
            }
            cols = {alias: col for alias, col in wanted.items() if col and col in dim.columns}
            if dim[join_key].duplicated().any():
                notes.append(
                    f"⚠ `{prod_table}.{join_key}` contient des doublons : la jointure "
                    "produit peut dupliquer des lignes de vente. Vérifier la gestion SCD."
                )
            lookup = dim[[join_key] + list(cols.values())].drop_duplicates(subset=[join_key])
            lookup = lookup.rename(columns={v: k for k, v in cols.items()})
            before = len(df)
            df = df.merge(lookup, left_on=fact_prod_key, right_on=join_key, how="left")
            if len(df) != before:
                notes.append(f"⚠ La jointure produit a modifié le nombre de lignes ({before} -> {len(df)}).")
            added.update({alias: alias for alias in cols})
            notes.append(
                f"Ventes enrichies par `{prod_table}` sur `{join_key}` : {list(cols.values())}."
            )

    # --- Dimension promotion ---------------------------------------------
    promo_map = mapping.get("promotion", {})
    promo_table = promo_map.get("table")
    fact_promo_key = ventes_map.get("promotion_key")
    if promo_table and promo_table in frames and fact_promo_key and fact_promo_key in df.columns:
        dim = frames[promo_table]
        join_key, overlap = best_join_column(df[fact_promo_key], dim)
        if join_key:
            notes.append(
                f"Clé de jointure promotion retenue : `{promo_table}.{join_key}` "
                f"(recouvrement des valeurs : {overlap:.1%})."
            )
            wanted = {
                "remise_pct_dim": promo_map.get("discount_rate"),
                "promo_debut": promo_map.get("start_date"),
                "promo_fin": promo_map.get("end_date"),
            }
            cols = {alias: col for alias, col in wanted.items() if col and col in dim.columns}
            lookup = dim[[join_key] + list(cols.values())].drop_duplicates(subset=[join_key])
            lookup = lookup.rename(columns={v: k for k, v in cols.items()})
            df = df.merge(lookup, left_on=fact_promo_key, right_on=join_key, how="left")
            added.update({alias: alias for alias in cols})
            notes.append(
                f"Ventes enrichies par `{promo_table}` sur `{join_key}` : {list(cols.values())}."
            )
    return df, added, notes


def checks_normalize(name: str) -> str:
    from src.data.mapping import normalize

    return normalize(name)


def infer_frequency(dates: pd.Series) -> tuple[str, dict[str, Any]]:
    """Déduit la fréquence d'observation dominante à partir des dates distinctes."""
    days = pd.Series(sorted(pd.to_datetime(dates).dt.normalize().dropna().unique()))
    if len(days) < 3:
        return "indeterminee", {"n_jours_distincts": int(len(days))}
    gaps = days.diff().dt.days.dropna()
    modal = int(gaps.mode().iloc[0])
    share_daily = float((gaps == 1).mean())
    span = (days.max() - days.min()).days + 1
    density = len(days) / span if span else 0
    if modal == 1 and share_daily > 0.8:
        freq = "D"
    elif modal in (7,):
        freq = "W"
    elif 28 <= modal <= 31:
        freq = "MS"
    else:
        freq = "D_irreguliere"
    return freq, {
        "ecart_modal_jours": modal,
        "part_ecarts_1j": share_daily,
        "densite_jours_couverts": float(density),
        "n_jours_distincts": int(len(days)),
    }


def build_daily_series(
    view: SalesView,
    net_quantity: pd.Series,
) -> pd.DataFrame:
    """Agrégation produit x jour (sans remplissage des jours manquants)."""
    df = view.df
    if not view.product_col or view.product_col not in df.columns:
        raise RuntimeError("Clé produit non identifiée : impossible d'agréger par produit.")
    tmp = pd.DataFrame(
        {
            "unique_id": df[view.product_col].astype("string"),
            "ds": df[view.date_col],
            "y": pd.to_numeric(net_quantity, errors="coerce"),
        }
    ).dropna(subset=["unique_id", "ds"])
    return tmp.groupby(["unique_id", "ds"], as_index=False)["y"].sum()


def compute_net_quantity(
    view: SalesView, mapping: dict[str, dict[str, str | None]]
) -> tuple[pd.Series, list[str]]:
    """Quantité nette sous hypothèses explicites (retours/annulations)."""
    df = view.df
    notes: list[str] = []
    qty_col = view.quantity_col
    if not qty_col or qty_col not in df.columns:
        raise RuntimeError("Colonne de quantité non identifiée.")
    qty = pd.to_numeric(df[qty_col], errors="coerce")
    net = qty.copy()

    ventes_map = mapping.get("ventes", {})
    status_col = ventes_map.get("status")
    if status_col and status_col in df.columns:
        modalities = df[status_col].astype("string").str.lower().fillna("")
        cancel_mask = modalities.str.contains(
            "annul|cancel|rejet|refus|echou|failed", regex=True, na=False
        )
        return_mask = modalities.str.contains("retour|return|rembours|refund", regex=True, na=False)
        if cancel_mask.any():
            net = net.where(~cancel_mask, 0.0)
            notes.append(
                f"Hypothèse : {int(cancel_mask.sum())} ligne(s) de statut « annulé » "
                "mises à 0 dans la quantité nette."
            )
        if return_mask.any():
            # Un retour est compté négativement s'il n'est pas déjà signé
            already_negative = (qty < 0) & return_mask
            to_flip = return_mask & ~already_negative
            net = net.where(~to_flip, -net.abs())
            notes.append(
                f"Hypothèse : {int(to_flip.sum())} ligne(s) de statut « retour » "
                "converties en quantité négative."
            )
        if not cancel_mask.any() and not return_mask.any():
            notes.append(
                f"Colonne `{status_col}` présente mais aucune modalité reconnue comme "
                "annulation/retour : quantité nette = quantité brute."
            )
    else:
        notes.append(
            "Aucune colonne de statut exploitable : quantité nette = quantité brute "
            "(les quantités négatives éventuelles sont conservées telles quelles)."
        )
    return net, notes


# ---------------------------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------------------------
def run_audit(refresh: bool = False, limit: int | None = None, use_cache: bool = True) -> dict[str, Any]:
    cfg = load_config()
    setup_logging(
        level=cfg.get("logging.level", "INFO"),
        json_output=bool(cfg.get("logging.json", False)),
        log_file=PROJECT_ROOT / cfg.get("logging.file", "reports/logs/pipeline.log"),
    )
    reports_dir = PROJECT_ROOT / cfg.get("paths.reports", "reports")
    reports_dir.mkdir(parents=True, exist_ok=True)

    expected = list(cfg.get("database.fact_tables", [])) + list(cfg.get("database.dim_tables", []))
    page_size = int(cfg.get("database.page_size", 1000))

    # --- 1. Schéma -------------------------------------------------------
    source = get_data_source()
    try:
        snapshot = inspect_schema(source, expected_tables=expected)
        table_aliases = match_tables(snapshot, cfg.get("schema_mapping", {}) or {})
        logger.info("Correspondance tables logiques -> réelles : %s", table_aliases)
        proposals = propose_mapping(snapshot, table_aliases)
        merged = merge_with_config(proposals, cfg.get("schema_mapping", {}) or {})
        inferred_relations = infer_relations_by_name(snapshot)

        # --- 2. Extraction ------------------------------------------------
        tables_to_extract = [t for t in snapshot.tables]
        frames = extract_all(
            tables_to_extract,
            page_size=page_size,
            limit=limit,
            refresh=refresh or not use_cache,
            source=source,
        )
    finally:
        source.close()

    # --- 3. Contrôles génériques ----------------------------------------
    # Colonnes indispensables (leur absence rend la modélisation impossible) et
    # colonnes dont la vacuité est attendue par construction.
    ventes_roles = merged.get("ventes", {})
    required_by_table = {
        ventes_roles.get("table"): [
            c
            for c in (
                ventes_roles.get("date"),
                ventes_roles.get("product_key"),
                ventes_roles.get("quantity"),
                ventes_roles.get("amount"),
            )
            if c
        ]
    }
    sparse_by_table = {
        ventes_roles.get("table"): [c for c in (ventes_roles.get("promotion_key"),) if c]
    }

    results: list[CheckResult] = []
    for name, df in frames.items():
        pk = snapshot.tables[name].primary_key if name in snapshot.tables else []
        # Sans clés déclarées (backend REST), on teste l'unicité de l'identifiant
        # de ligne détecté par le mapping.
        key_columns = pk or _identity_columns(name, merged, df)
        results.append(
            checks.check_missing_values(
                df,
                name,
                required_columns=required_by_table.get(name),
                expected_sparse=sparse_by_table.get(name),
            )
        )
        results.append(checks.check_duplicates(df, name, key_columns=key_columns))

    # --- 4. Contrôles ventes --------------------------------------------
    view = resolve_sales(frames, merged)
    ventes_map = merged.get("ventes", {})
    sales, enriched_cols, enrich_notes = enrich_sales(view, frames, merged)
    view.df = sales
    view.notes.extend(enrich_notes)

    freq, freq_details = infer_frequency(sales[view.date_col])
    results.append(checks.check_date_coverage(sales, view.date_col))
    results.append(checks.check_calendar_gaps(sales, view.date_col))
    # Le prix unitaire et le taux de remise peuvent venir des dimensions
    # (c'est le cas ici : la table de faits ne porte que quantité et montant).
    price_col = ventes_map.get("unit_price") or enriched_cols.get("prix_dim")
    discount_col = ventes_map.get("discount") or enriched_cols.get("remise_pct_dim")
    results.append(
        checks.check_negative_and_zero(
            sales,
            {
                "quantite": ventes_map.get("quantity"),
                "montant": ventes_map.get("amount"),
                "prix_unitaire": price_col,
                "remise": discount_col,
            },
        )
    )
    results.append(
        checks.check_returns_and_cancellations(
            sales,
            ventes_map.get("status"),
            ventes_map.get("return_flag"),
            ventes_map.get("quantity"),
        )
    )
    results.append(
        checks.check_amount_consistency(
            sales,
            ventes_map.get("quantity"),
            price_col,
            ventes_map.get("amount"),
            discount_col,
        )
    )

    # Intégrité référentielle faits -> dimensions.
    # La clé côté dimension est déterminée par recouvrement de valeurs : une
    # dimension porte souvent une clé de substitution ET une clé naturelle, et
    # comparer la mauvaise produirait un faux « 100 % d'orphelines ».
    dimension_links = {
        "produit": "product_key",
        "client": "client_key",
        "promotion": "promotion_key",
    }
    for logical, role in dimension_links.items():
        dim_map = merged.get(logical, {})
        dim_table = dim_map.get("table")
        fact_key = ventes_map.get(role)
        if not dim_table or dim_table not in frames or not fact_key or fact_key not in sales.columns:
            continue
        dim_key, _ = best_join_column(sales[fact_key], frames[dim_table], min_overlap=0.0)
        results.append(
            checks.check_referential_integrity(
                sales, fact_key, frames[dim_table], dim_key, f"ventes->{logical}"
            )
        )

    # Dates de lancement : décide si l'on peut compléter les zéros depuis le
    # lancement déclaré ou seulement depuis la première vente observée.
    launch_col = enriched_cols.get("lancement_dim")
    if launch_col and launch_col in sales.columns and view.product_col:
        launch_series = (
            sales[[view.product_col, launch_col]]
            .dropna()
            .drop_duplicates(subset=[view.product_col])
            .set_index(view.product_col)[launch_col]
        )
        results.append(
            checks.check_launch_dates(sales, view.date_col, view.product_col, launch_series)
        )
    else:
        results.append(
            CheckResult(
                "dates_lancement",
                "non_applicable",
                "Aucune date de mise en vente disponible : la fenêtre d'activité "
                "de chaque produit sera bornée par sa première vente observée.",
            )
        )

    # Fenêtres promotionnelles
    if enriched_cols.get("promo_debut") and ventes_map.get("promotion_key"):
        results.append(
            checks.check_promotion_windows(
                sales,
                view.date_col,
                ventes_map["promotion_key"],
                enriched_cols["promo_debut"],
                enriched_cols["promo_fin"],
            )
        )

    # --- 5. Séries produit x jour ---------------------------------------
    net_qty, net_notes = compute_net_quantity(view, merged)
    daily = build_daily_series(view, net_qty)
    profile = checks.series_profile(daily)
    classified = checks.classify_series(
        profile,
        adi_threshold=float(cfg.get("segmentation.adi_threshold", 1.32)),
        cv2_threshold=float(cfg.get("segmentation.cv2_threshold", 0.49)),
        min_history_days=int(cfg.get("target.min_history_days", 90)),
        min_nonzero_points=int(cfg.get("target.min_nonzero_points", 12)),
    )

    daily_total = daily.groupby("ds", as_index=False)["y"].sum()
    results.append(checks.check_atypical_periods(daily_total))

    # Promotions : indicateur au niveau ligne de vente
    promo_key = ventes_map.get("promotion_key")
    if promo_key and promo_key in sales.columns:
        sales["_promo_flag"] = sales[promo_key].notna().astype(int)
        results.append(
            checks.check_promotion_coverage(sales, "_promo_flag", view.date_col, view.product_col)
        )
    else:
        results.append(
            CheckResult(
                "couverture_promotions",
                "non_applicable",
                "Aucune clé de promotion identifiée dans la table de ventes ; "
                "la liaison promotion<->vente devra être établie via dim_promotion "
                "(fenêtres de dates) et documentée comme hypothèse.",
            )
        )

    # --- 6. Synthèse cible / granularité --------------------------------
    n_products = int(daily["unique_id"].nunique())
    span_days = int((daily["ds"].max() - daily["ds"].min()).days + 1) if len(daily) else 0
    density = float(len(daily) / max(n_products * span_days, 1))
    zero_share = float((daily["y"] <= 0).mean()) if len(daily) else np.nan

    summary = {
        "genere_le": datetime.now(timezone.utc).isoformat(),
        "backend": snapshot.backend,
        "schema": snapshot.schema,
        "tables": {n: int(t.n_rows) for n, t in snapshot.tables.items()},
        "frequence_detectee": freq,
        "frequence_details": freq_details,
        "n_produits_series": n_products,
        "span_jours": span_days,
        "densite_produit_jour": density,
        "part_points_nuls_observes": zero_share,
        "mapping": merged,
        "notes_dates": view.notes,
        "notes_quantite_nette": net_notes,
        "notes_schema": snapshot.notes,
        "checks": [r.to_dict() for r in results],
        "repartition_profils": classified["profil_demande"].value_counts().to_dict()
        if not classified.empty
        else {},
        "repartition_cycle_vie": classified["statut_cycle_vie"].value_counts().to_dict()
        if not classified.empty
        else {},
    }

    # --- 7. Écriture des livrables --------------------------------------
    _write_schema_report(reports_dir / "01_schema.md", snapshot, proposals, inferred_relations)
    _write_quality_report(
        reports_dir / "02_audit_qualite.md",
        summary,
        results,
        classified,
        daily,
        daily_total,
        merged,
    )
    (reports_dir / "audit_snapshot.json").write_text(
        json.dumps(checks._jsonable(summary), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    _write_mapping_yaml(reports_dir / "mapping_propose.yaml", merged)

    interim = PROJECT_ROOT / cfg.get("paths.data_interim", "data/interim")
    interim.mkdir(parents=True, exist_ok=True)
    daily.to_parquet(interim / "ventes_produit_jour.parquet", index=False)
    classified.to_parquet(interim / "profil_series.parquet", index=False)
    logger.info("Audit terminé. Rapports dans %s", reports_dir)
    return summary


def _write_mapping_yaml(path: Path, merged: dict[str, dict[str, str | None]]) -> None:
    """Écrit la proposition au format attendu par ``config/config.yaml``."""
    out: dict[str, dict[str, Any]] = {}
    for logical, roles in merged.items():
        entry: dict[str, Any] = {"table": roles.get("table")}
        key_map = CONFIG_KEY_BY_ROLE.get(logical, {})
        for role, column in roles.items():
            if role == "table":
                continue
            cfg_key = key_map.get(role, role)
            entry[cfg_key] = column
        out[logical] = entry
    header = (
        "# Proposition automatique — À VALIDER PUIS RECOPIER dans config/config.yaml\n"
        "# (section schema_mapping). Généré par `python -m src.pipelines.audit`.\n"
    )
    path.write_text(header + yaml.safe_dump({"schema_mapping": out}, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _write_schema_report(path: Path, snapshot, proposals, inferred_relations: pd.DataFrame) -> None:
    lines = [
        "# 01 — Schéma réel découvert",
        "",
        f"_Généré le {datetime.now().strftime('%Y-%m-%d %H:%M')} — backend `{snapshot.backend}`, schéma `{snapshot.schema}`._",
        "",
    ]
    if snapshot.notes:
        lines += ["> **Limites d'accès :**", ""] + [f"> - {n}" for n in snapshot.notes] + [""]

    overview = pd.DataFrame(
        [
            {
                "table": name,
                "lignes": t.n_rows,
                "colonnes": len(t.columns),
                "cle_primaire": ", ".join(t.primary_key) or "—",
            }
            for name, t in snapshot.tables.items()
        ]
    ).sort_values("lignes", ascending=False)
    lines += ["## Vue d'ensemble", "", df_to_md(overview, max_rows=100), ""]

    lines += ["## Détail des colonnes", ""]
    for name, table in snapshot.tables.items():
        lines += [f"### `{name}` — {table.n_rows:,} lignes", ""]
        cols = table.columns.copy()
        keep = [c for c in ["column_name", "data_type", "udt_name", "is_nullable", "column_default"] if c in cols.columns]
        lines += [df_to_md(cols[keep], max_rows=100), ""]
        if table.sample is not None and len(table.sample):
            lines += ["**Échantillon :**", "", df_to_md(table.sample, max_rows=5), ""]

    lines += ["## Clés étrangères déclarées", "", df_to_md(snapshot.foreign_keys, max_rows=100), ""]
    if snapshot.foreign_keys.empty:
        lines += [
            "> Aucune contrainte de clé étrangère déclarée dans la base. "
            "Les relations ci-dessous sont **inférées par nom de colonne** et doivent être validées.",
            "",
            df_to_md(inferred_relations, max_rows=100),
            "",
        ]

    lines += ["## Mapping proposé (colonne réelle -> rôle métier)", ""]
    lines += [
        "> Cette table est une **proposition heuristique**, pas une vérité. "
        "Toute correction se fait dans `config/config.yaml` (section `schema_mapping`), "
        "qui est toujours prioritaire.",
        "",
        df_to_md(mapping_report(proposals), max_rows=200),
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_quality_report(
    path: Path,
    summary: dict[str, Any],
    results: list[CheckResult],
    classified: pd.DataFrame,
    daily: pd.DataFrame,
    daily_total: pd.DataFrame,
    merged: dict[str, dict[str, str | None]],
) -> None:
    n_critique = sum(1 for r in results if r.status == "critique")
    n_alerte = sum(1 for r in results if r.status == "alerte")

    lines = [
        "# 02 — Audit de qualité des données",
        "",
        f"_Généré le {datetime.now().strftime('%Y-%m-%d %H:%M')}._",
        "",
        f"**Bilan : {n_critique} point(s) critique(s), {n_alerte} alerte(s) "
        f"sur {len(results)} contrôles.**",
        "",
        "## Volumétrie",
        "",
        df_to_md(
            pd.DataFrame(
                [{"table": k, "lignes": v} for k, v in summary["tables"].items()]
            ).sort_values("lignes", ascending=False),
            max_rows=50,
        ),
        "",
        "## Fréquence et granularité observées",
        "",
        f"- Fréquence détectée : **{summary['frequence_detectee']}**",
        f"- Détail : `{json.dumps(checks._jsonable(summary['frequence_details']), ensure_ascii=False)}`",
        f"- Séries produit : **{summary['n_produits_series']}**",
        f"- Amplitude de l'historique : **{summary['span_jours']} jours**",
        f"- Densité produit×jour observée (lignes présentes / cellules possibles) : "
        f"**{summary['densite_produit_jour']:.2%}**",
        "",
        "> Une densité faible signifie que la plupart des couples produit×jour n'ont "
        "**aucune ligne** de vente. Cela ne veut pas dire « vente = 0 » : cela peut aussi "
        "signifier produit non lancé, indisponible, ou en rupture. Le remplissage par zéro "
        "n'est donc appliqué qu'à l'intérieur de la fenêtre d'activité de chaque produit "
        "(`target.fill_policy: active_window`).",
        "",
        "## Hypothèses retenues",
        "",
    ]
    for note in summary["notes_dates"] + summary["notes_quantite_nette"] + summary["notes_schema"]:
        lines.append(f"- {note}")
    lines += ["", "## Résultats des contrôles", ""]
    for result in results:
        lines.append(check_to_md(result))

    if not classified.empty:
        lines += ["## Typologie des séries", ""]
        prof = classified["profil_demande"].value_counts().rename_axis("profil").reset_index(name="n_series")
        prof["part"] = prof["n_series"] / prof["n_series"].sum()
        life = (
            classified["statut_cycle_vie"].value_counts().rename_axis("statut").reset_index(name="n_series")
        )
        life["part"] = life["n_series"] / life["n_series"].sum()
        lines += [
            "**Profil de demande (Syntetos-Boylan-Croston, seuils ADI=1.32 / CV²=0.49)**",
            "",
            df_to_md(prof),
            "",
            "**Statut de cycle de vie**",
            "",
            df_to_md(life),
            "",
            "**Top 15 séries par volume**",
            "",
            df_to_md(
                classified.sort_values("total", ascending=False)
                .head(15)[
                    [
                        "unique_id",
                        "total",
                        "n_jours_avec_vente",
                        "span_jours",
                        "taux_jours_sans_vente",
                        "adi",
                        "cv2",
                        "profil_demande",
                        "statut_cycle_vie",
                    ]
                ],
                max_rows=15,
            ),
            "",
        ]

    if len(daily_total):
        lines += [
            "## Série agrégée (tous produits)",
            "",
            df_to_md(daily_total.tail(15), max_rows=15),
            "",
        ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit lecture seule de la base Supabase.")
    parser.add_argument("--refresh", action="store_true", help="Ignore le cache Parquet et ré-extrait.")
    parser.add_argument("--limit", type=int, default=None, help="Limite de lignes par table (tests).")
    parser.add_argument("--no-cache", action="store_true", help="N'utilise pas le cache local.")
    args = parser.parse_args()
    run_audit(refresh=args.refresh, limit=args.limit, use_cache=not args.no_cache)


if __name__ == "__main__":
    main()
