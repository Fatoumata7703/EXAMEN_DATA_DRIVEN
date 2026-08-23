"""
Exécute la même séquence que le DAG Airflow (extract -> bronze -> silver -> gold),
mais en appel direct Python, pour valider la logique métier sans avoir Airflow installé.
Utile en local pendant le développement ; le DAG réel fera exactement ce que fait ce script,
avec en plus l'orchestration, les reprises et le parallélisme gérés par Airflow.
"""

import sys
sys.path.insert(0, "/home/claude/airflow_project")

from pipeline.transforms import RAW_TABLES, extract_to_raw, load_bronze, load_silver, build_gold_tables

DS = "2026-08-12"

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
