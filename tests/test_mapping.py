"""Tests du moteur de mapping colonne -> rôle métier (aucune base requise)."""

from __future__ import annotations

import pandas as pd
import pytest

from src.data.mapping import normalize, propose_table_mapping
from src.data.schema_inspector import SchemaSnapshot, TableSchema, infer_relations_by_name


def _table(name: str, columns: list[tuple[str, str]], pk: list[str] | None = None) -> TableSchema:
    df = pd.DataFrame(
        [
            {"column_name": c, "data_type": t, "is_nullable": "YES", "ordinal_position": i + 1}
            for i, (c, t) in enumerate(columns)
        ]
    )
    return TableSchema(name=name, columns=df, n_rows=100, primary_key=pk or [])


def test_normalize_removes_accents_and_separators():
    assert normalize("Quantité-Vendue") == "quantite_vendue"
    assert normalize("SOUS CATÉGORIE") == "sous_categorie"


def test_roles_detected_on_french_schema():
    table = _table(
        "fact_ventes",
        [
            ("vente_id", "integer"),
            ("date_vente", "date"),
            ("produit_id", "integer"),
            ("client_id", "integer"),
            ("promotion_id", "integer"),
            ("quantite", "integer"),
            ("prix_unitaire", "numeric"),
            ("remise", "numeric"),
            ("montant_total", "numeric"),
            ("statut", "text"),
        ],
    )
    mapping = propose_table_mapping(
        table,
        [
            "date",
            "product_key",
            "client_key",
            "promotion_key",
            "quantity",
            "unit_price",
            "discount",
            "amount",
            "status",
            "line_id",
        ],
    )
    assert mapping.roles["date"] == "date_vente"
    assert mapping.roles["product_key"] == "produit_id"
    assert mapping.roles["client_key"] == "client_id"
    assert mapping.roles["promotion_key"] == "promotion_id"
    assert mapping.roles["quantity"] == "quantite"
    assert mapping.roles["unit_price"] == "prix_unitaire"
    assert mapping.roles["discount"] == "remise"
    assert mapping.roles["amount"] == "montant_total"
    assert mapping.roles["status"] == "statut"
    assert mapping.roles["line_id"] == "vente_id"


def test_roles_detected_on_english_schema():
    table = _table(
        "fact_sales",
        [
            ("id", "bigint"),
            ("sale_date", "timestamp"),
            ("product_id", "integer"),
            ("qty", "integer"),
            ("unit_price", "numeric"),
            ("sales_amount", "numeric"),
        ],
    )
    mapping = propose_table_mapping(
        table, ["date", "product_key", "quantity", "unit_price", "amount"]
    )
    assert mapping.roles["date"] == "sale_date"
    assert mapping.roles["product_key"] == "product_id"
    assert mapping.roles["quantity"] == "qty"
    assert mapping.roles["amount"] == "sales_amount"


def test_type_mismatch_is_penalised():
    """Une colonne nommée « quantite » mais typée texte doit être pénalisée."""
    table = _table("fact_ventes", [("quantite_label", "text"), ("quantite", "integer")])
    mapping = propose_table_mapping(table, ["quantity"])
    assert mapping.roles["quantity"] == "quantite"


def test_missing_role_returns_none():
    table = _table("dim_client", [("client_id", "integer"), ("nom", "text")])
    mapping = propose_table_mapping(table, ["quantity", "amount"])
    assert mapping.roles["quantity"] is None
    assert mapping.roles["amount"] is None


def test_infer_relations_by_name():
    snapshot = SchemaSnapshot(
        backend="postgres",
        schema="public",
        tables={
            "fact_ventes": _table("fact_ventes", [("produit_id", "integer"), ("quantite", "integer")]),
            "dim_produit": _table("dim_produit", [("produit_id", "integer"), ("marque", "text")], pk=["produit_id"]),
        },
        foreign_keys=pd.DataFrame(),
    )
    relations = infer_relations_by_name(snapshot)
    assert len(relations) == 1
    assert relations.iloc[0]["source_table"] == "fact_ventes"
    assert relations.iloc[0]["target_table"] == "dim_produit"
