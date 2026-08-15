"""Garde-fous lecture seule et validation des identifiants SQL."""

from __future__ import annotations

import pytest

from src.data.connection import ReadOnlyViolation, assert_read_only, quote_ident


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO fact_ventes VALUES (1)",
        "update fact_ventes set quantite = 0",
        "DELETE FROM dim_produit",
        "DROP TABLE fact_ventes",
        "TRUNCATE fact_ventes",
        "CREATE TABLE t (a int)",
        "ALTER TABLE fact_ventes ADD COLUMN x int",
        "GRANT ALL ON fact_ventes TO public",
    ],
)
def test_write_statements_are_rejected(sql):
    with pytest.raises(ReadOnlyViolation):
        assert_read_only(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM fact_ventes",
        "SELECT count(*) FROM dim_produit WHERE marque = 'x'",
        "-- delete me\nSELECT 1",
        "/* update later */ SELECT 1",
    ],
)
def test_read_statements_are_allowed(sql):
    assert_read_only(sql)  # ne doit pas lever


def test_quote_ident_rejects_injection():
    assert quote_ident("fact_ventes") == '"fact_ventes"'
    for bad in ['a"; DROP TABLE x; --', "a b", "1table", ""]:
        with pytest.raises(ValueError):
            quote_ident(bad)
