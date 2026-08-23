# Suite great_expectations — qualité des données

Contrôle qualité formel des 6 tables source, en complément des règles codées
directement dans `pipeline/transforms.py` (fonction `run_dq_checkpoint`).
Positionnée entre les zones Bronze et Silver du pipeline d'ingestion.

## Installation et exécution

```bash
pip install great_expectations
python run_data_quality.py
```

Génère un site Data Docs HTML dans `gx/uncommitted/data_docs/local_site/index.html` —
rapport visuel de chaque règle et de son résultat, consultable dans un navigateur.

## Résultats attendus

Validés au préalable par exécution pandas pure (`dry_run_check.py`), sur les données
du dossier `02_jeu_de_donnees/donnees/` :

| Table | Règles | Anomalies attendues |
|---|---|---|
| dim_products | 4 | 15 lignes avec catégorie en casse anormale |
| dim_customers | 4 | 0 (les valeurs manquantes sont sous le seuil de tolérance de 10%) |
| promotions | 3 | 0 |
| fact_transactions | 8 | 0 |
| stock_daily | 5 | 0 |
| web_events | 4 | 0 |

Les anomalies volontaires sur `dim_products` et `dim_customers` sont détectées et
signalées, sans bloquer le passage en zone Silver (seuil de tolérance configurable).

## Intégration dans le pipeline

Ce script est autonome : il valide les tables et génère les Data Docs, sans modifier
le pipeline d'ingestion. L'intégration directe dans le DAG Airflow (remplacement de
`run_dq_checkpoint()` par les expectations formalisées ici) constitue une évolution
possible, sans changement de structure du pipeline — les résultats détaillés (via
`unexpected_index_list`, activé par `result_format=COMPLETE` dans ce script)
permettraient de reconstruire le même mécanisme d'isolement des lignes en anomalie.
