"""
Exécute la séquence complète du pipeline d'ingestion (extract -> bronze -> silver ->
gold) par appel direct des fonctions Python, indépendamment d'un environnement
Airflow installé. Le DAG Airflow orchestre exactement la même logique, en ajoutant
la gestion des reprises et du parallélisme.
"""

import sys
from pathlib import Path
from datetime import date

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.transforms import RAW_TABLES, extract_to_raw, load_bronze, load_silver, build_gold_tables

DS = date.today().isoformat()

print(f"=== Pipeline d'ingestion — run local (ds={DS}) ===\n")

silver_ctxs = []
for table in RAW_TABLES:
    print(f"--- {table} ---")
    raw_ctx = extract_to_raw(table, DS)
    bronze_ctx = load_bronze(raw_ctx)
    print(f"[{table}] bronze : {bronze_ctx['n_rows']} lignes")
    try:
        silver_ctx = load_silver(bronze_ctx)
        silver_ctxs.append(silver_ctx)
    except ValueError as e:
        print(f"[{table}] ÉCHEC : {e}")
    print()

print("--- gold ---")
gold_paths = build_gold_tables(silver_ctxs)
print("\n=== Terminé ===")
print("Chemins gold :", gold_paths)
