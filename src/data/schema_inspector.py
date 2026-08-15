"""Inspection du schéma réel : tables, colonnes, types, clés, volumes.

Rien n'est supposé sur la nomenclature : tout est lu depuis la base.
Fonctionne avec les deux backends (SQL direct ou REST, avec dégradation
explicite des informations disponibles en REST).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

import pandas as pd

from src.data.connection import DataSource, PostgresSource, RestSource
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


@dataclass
class TableSchema:
    name: str
    columns: pd.DataFrame
    n_rows: int
    primary_key: list[str] = field(default_factory=list)
    foreign_keys: list[dict[str, str]] = field(default_factory=list)
    sample: pd.DataFrame | None = None

    @property
    def column_names(self) -> list[str]:
        return self.columns["column_name"].tolist()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "n_rows": self.n_rows,
            "primary_key": self.primary_key,
            "foreign_keys": self.foreign_keys,
            "columns": self.columns.to_dict(orient="records"),
        }


@dataclass
class SchemaSnapshot:
    backend: str
    schema: str
    tables: dict[str, TableSchema]
    foreign_keys: pd.DataFrame
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "schema": self.schema,
            "notes": self.notes,
            "tables": {name: t.to_dict() for name, t in self.tables.items()},
            "foreign_keys": self.foreign_keys.to_dict(orient="records")
            if not self.foreign_keys.empty
            else [],
        }


def inspect_schema(
    source: DataSource,
    expected_tables: Sequence[str] | None = None,
    sample_rows: int = 5,
) -> SchemaSnapshot:
    """Construit un instantané complet du schéma."""
    notes: list[str] = []

    if isinstance(source, PostgresSource):
        table_names = source.list_tables()
        all_cols = source.all_columns()
        pk_df = source.primary_keys()
        fk_df = source.foreign_keys()
    elif isinstance(source, RestSource):
        candidates = list(expected_tables or [])
        # PostgREST publie la liste des tables exposées dans son OpenAPI :
        # inutile de deviner, on complète simplement la liste attendue.
        try:
            candidates = list(dict.fromkeys(candidates + list(source._definitions())))
        except Exception:  # noqa: BLE001 - repli sur la liste configurée
            pass
        if not candidates:
            raise ValueError(
                "Backend REST : fournir `expected_tables` (aucune table découverte)."
            )
        table_names = source.probe_tables(candidates)
        all_cols = pd.DataFrame()
        pk_df, fk_df = source.declared_keys()
        if pk_df.empty and fk_df.empty:
            pk_df = pd.DataFrame(columns=["table_name", "column_name"])
            fk_df = pd.DataFrame(
                columns=["source_table", "source_column", "target_table", "target_column"]
            )
            notes.append(
                "Backend REST sans OpenAPI exploitable : types INFÉRÉS depuis un "
                "échantillon et clés NON lisibles. Les relations rapportées sont "
                "des hypothèses fondées sur les noms de colonnes."
            )
        else:
            notes.append(
                "Backend REST : types, clés primaires et clés étrangères lus dans le "
                "schéma OpenAPI publié par PostgREST — donc déclarés, pas inférés. "
                "Seuls les commentaires de colonnes restent inaccessibles."
            )
    else:  # pragma: no cover - défensif
        raise TypeError(f"Backend inconnu : {type(source)}")

    if expected_tables:
        missing = [t for t in expected_tables if t not in table_names]
        if missing:
            notes.append(f"Tables attendues absentes du schéma : {missing}")

    tables: dict[str, TableSchema] = {}
    for name in table_names:
        try:
            n_rows = source.count_rows(name)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Comptage impossible pour %s : %s", name, exc)
            n_rows = -1

        if isinstance(source, PostgresSource) and not all_cols.empty:
            cols = (
                all_cols[all_cols["table_name"] == name]
                .drop(columns=["table_name"])
                .reset_index(drop=True)
            )
        else:
            cols = source.describe_columns(name)

        pk = (
            pk_df[pk_df["table_name"] == name]["column_name"].tolist()
            if not pk_df.empty
            else []
        )
        fks = (
            fk_df[fk_df["source_table"] == name].to_dict(orient="records")
            if not fk_df.empty
            else []
        )
        try:
            sample = source.fetch_table(name, limit=sample_rows, page_size=sample_rows)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Échantillon impossible pour %s : %s", name, exc)
            sample = None

        tables[name] = TableSchema(
            name=name,
            columns=cols,
            n_rows=n_rows,
            primary_key=pk,
            foreign_keys=fks,
            sample=sample,
        )
        logger.info("Table %-24s | %8s lignes | %2d colonnes", name, f"{n_rows:,}", len(cols))

    return SchemaSnapshot(
        backend=source.backend,
        schema=source.schema,
        tables=tables,
        foreign_keys=fk_df,
        notes=notes,
    )


def infer_relations_by_name(snapshot: SchemaSnapshot) -> pd.DataFrame:
    """Relations *présumées* : colonne d'une table de faits portant le même nom
    qu'une clé primaire (ou qu'une colonne se terminant par ``_id``) d'une dimension.

    Utilisé uniquement quand les FK déclarées sont absentes (REST, ou schéma
    sans contraintes). Le résultat est une hypothèse à valider.
    """
    dim_keys: dict[str, list[str]] = {}
    for name, table in snapshot.tables.items():
        keys = list(table.primary_key)
        if not keys:
            # Sans clé primaire déclarée, on ne considère comme cible qu'une table
            # de dimension : une table de faits ne peut pas être le côté « 1 »
            # d'une relation devinée par nom.
            if name.lower().startswith("fact"):
                continue
            keys = [c for c in table.column_names if c.lower().endswith(("_id", "_key", "_sk"))]
        dim_keys[name] = keys

    rows: list[dict[str, Any]] = []
    for src_name, src_table in snapshot.tables.items():
        for col in src_table.column_names:
            for tgt_name, keys in dim_keys.items():
                if tgt_name == src_name:
                    continue
                if col in keys:
                    rows.append(
                        {
                            "source_table": src_name,
                            "source_column": col,
                            "target_table": tgt_name,
                            "target_column": col,
                            "origin": "inféré (nom identique)",
                        }
                    )
    return pd.DataFrame(rows)
