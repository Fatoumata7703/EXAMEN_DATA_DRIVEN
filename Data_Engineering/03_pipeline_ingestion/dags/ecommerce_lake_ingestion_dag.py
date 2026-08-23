"""
DAG d'ingestion : Sources -> Raw -> Bronze -> Silver -> Gold.

Toute la logique métier vit dans pipeline/transforms.py (testable indépendamment
d'Airflow). Ce fichier n'est qu'une orchestration : il déclare les tâches, leurs
dépendances, et laisse Airflow gérer les reprises, le parallélisme et le suivi.

Le gate qualité est la tâche `silver` : elle appelle run_dq_checkpoint() en interne
(voir transforms.py) puis écrit soit en Silver, soit en quarantaine. À l'étape
suivante, run_dq_checkpoint() sera remplacé par une vraie suite great_expectations
sans que ce DAG n'ait besoin de changer.

Dynamic task mapping (.expand) : les 4 étapes tournent une fois par table de
RAW_TABLES, sans dupliquer le code — Airflow instancie une tâche par table au moment
de l'exécution.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pendulum
from airflow.decorators import dag, task
from airflow.exceptions import AirflowException

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # ajoute le dossier contenant pipeline/ ; à adapter selon l'emplacement de déploiement Airflow

from pipeline.transforms import (  # noqa: E402
    RAW_TABLES,
    build_gold_tables,
    extract_to_raw,
    load_bronze,
    load_silver,
)

default_args = {
    "owner": "data-engineering",
    "retries": 2,
    "retry_delay": pendulum.duration(minutes=5),
}


@dag(
    dag_id="ecommerce_lake_ingestion",
    description="Ingestion Raw -> Bronze -> Silver -> Gold pour la plateforme pricing/forecasting/reco",
    schedule="@daily",
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    default_args=default_args,
    tags=["ecommerce", "lake", "ingestion"],
)
def ecommerce_lake_ingestion():

    @task
    def extract(table: str, ds: str = None) -> dict:
        return extract_to_raw(table, ds)

    @task
    def bronze(ctx: dict) -> dict:
        return load_bronze(ctx)

    @task
    def silver(ctx: dict) -> dict:
        try:
            return load_silver(ctx)
        except ValueError as e:
            # taux d'erreur au-dessus du seuil : on fait échouer la tâche plutôt que
            # de laisser passer des données dégradées vers Silver/Gold
            raise AirflowException(str(e))

    @task
    def gold(silver_ctxs: list[dict]) -> dict:
        return build_gold_tables(silver_ctxs)

    raw_ctxs = extract.expand(table=RAW_TABLES)
    bronze_ctxs = bronze.expand(ctx=raw_ctxs)
    silver_ctxs = silver.expand(ctx=bronze_ctxs)
    gold(silver_ctxs)


ecommerce_lake_ingestion()
