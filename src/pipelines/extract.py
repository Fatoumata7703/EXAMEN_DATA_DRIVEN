"""Pipeline d'extraction — copie locale (Parquet) des tables sources.

    python -m src.pipelines.extract [--tables t1 t2] [--refresh] [--limit N]

Lecture seule : aucune écriture n'est effectuée sur la base.
"""

from __future__ import annotations

import argparse

from src.config.settings import PROJECT_ROOT, load_config
from src.data.connection import get_data_source
from src.data.extract import extract_all
from src.data.schema_inspector import inspect_schema
from src.utils.logging_utils import get_logger, setup_logging

logger = get_logger(__name__)


def main() -> None:
    cfg = load_config()
    setup_logging(
        level=cfg.get("logging.level", "INFO"),
        json_output=bool(cfg.get("logging.json", False)),
        log_file=PROJECT_ROOT / cfg.get("logging.file", "reports/logs/pipeline.log"),
    )
    parser = argparse.ArgumentParser(description="Extraction paginée des tables sources.")
    parser.add_argument("--tables", nargs="*", default=None, help="Tables à extraire (défaut : toutes).")
    parser.add_argument("--refresh", action="store_true", help="Force la ré-extraction.")
    parser.add_argument("--limit", type=int, default=None, help="Limite de lignes par table.")
    args = parser.parse_args()

    expected = list(cfg.get("database.fact_tables", [])) + list(cfg.get("database.dim_tables", []))
    source = get_data_source()
    try:
        tables = args.tables
        if not tables:
            snapshot = inspect_schema(source, expected_tables=expected, sample_rows=1)
            tables = list(snapshot.tables)
        frames = extract_all(
            tables,
            page_size=int(cfg.get("database.page_size", 1000)),
            limit=args.limit,
            refresh=args.refresh,
            source=source,
        )
    finally:
        source.close()

    total = sum(len(df) for df in frames.values())
    logger.info("Extraction terminée : %d tables, %s lignes au total", len(frames), f"{total:,}")


if __name__ == "__main__":
    main()
