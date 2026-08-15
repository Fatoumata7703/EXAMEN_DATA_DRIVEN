"""Extraction paginée des tables sources vers un cache local Parquet.

Le cache évite de re-solliciter la base à chaque exécution et garantit la
reproductibilité de l'audit et des entraînements (les fichiers portent
l'horodatage et le nombre de lignes extraites).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

import pandas as pd

from src.config.settings import PROJECT_ROOT, load_config
from src.data.coercion import coerce_datetime_columns, coerce_decimal_columns
from src.data.connection import DataSource, get_data_source
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)

MANIFEST_NAME = "_manifest.json"


def raw_dir() -> Path:
    cfg = load_config()
    path = PROJECT_ROOT / cfg.get("paths.data_raw", "data/raw")
    path.mkdir(parents=True, exist_ok=True)
    return path


def extract_table(
    source: DataSource,
    table: str,
    page_size: int = 1000,
    limit: int | None = None,
    cache: bool = True,
    refresh: bool = False,
) -> pd.DataFrame:
    """Extrait une table entière (pagination) avec cache Parquet."""
    target = raw_dir() / f"{table}.parquet"
    if cache and target.exists() and not refresh:
        df = pd.read_parquet(target)
        logger.info("Cache utilisé pour %s (%s lignes) — %s", table, f"{len(df):,}", target.name)
        return df

    df = coerce_decimal_columns(
        coerce_datetime_columns(source.fetch_table(table, page_size=page_size, limit=limit))
    )
    if cache and not df.empty:
        # Les colonnes d'objets hétérogènes (JSON) sont sérialisées en texte.
        safe = df.copy()
        for col in safe.columns:
            if safe[col].dtype == object:
                sample = safe[col].dropna()
                if len(sample) and isinstance(sample.iloc[0], (dict, list)):
                    safe[col] = safe[col].apply(
                        lambda v: json.dumps(v, ensure_ascii=False) if v is not None else None
                    )
        safe.to_parquet(target, index=False)
        logger.info("Écrit %s (%s lignes)", target.name, f"{len(df):,}")
    return df


def extract_all(
    tables: Sequence[str],
    page_size: int = 1000,
    limit: int | None = None,
    refresh: bool = False,
    source: DataSource | None = None,
) -> dict[str, pd.DataFrame]:
    """Extrait plusieurs tables et met à jour le manifeste du cache."""
    own_source = source is None
    src = source or get_data_source()
    frames: dict[str, pd.DataFrame] = {}
    manifest: dict[str, dict] = {}
    try:
        for table in tables:
            df = extract_table(
                src, table, page_size=page_size, limit=limit, refresh=refresh
            )
            frames[table] = df
            manifest[table] = {
                "n_rows": int(len(df)),
                "n_cols": int(df.shape[1]),
                "columns": list(map(str, df.columns)),
                "extracted_at": datetime.now(timezone.utc).isoformat(),
                "backend": src.backend,
                "truncated": limit is not None and len(df) >= limit,
            }
    finally:
        if own_source:
            src.close()

    manifest_path = raw_dir() / MANIFEST_NAME
    existing: dict = {}
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
    existing.update(manifest)
    manifest_path.write_text(
        json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return frames


def load_cached(table: str) -> pd.DataFrame:
    path = raw_dir() / f"{table}.parquet"
    if not path.exists():
        raise FileNotFoundError(
            f"Cache absent pour '{table}'. Lancez d'abord : python -m src.pipelines.extract"
        )
    return pd.read_parquet(path)
