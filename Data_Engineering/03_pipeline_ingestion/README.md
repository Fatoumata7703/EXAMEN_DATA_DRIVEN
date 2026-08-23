# Pipeline d'ingestion — Raw → Bronze → Silver → Gold

## Contenu

```
pipeline/transforms.py                 Logique métier (extraction, typage, contrôle qualité,
                                        agrégation). Indépendante d'Airflow, testable en local.
dags/ecommerce_lake_ingestion_dag.py   DAG Airflow : orchestration au-dessus de transforms.py.
run_local_test.py                      Exécute la séquence complète du pipeline sans Airflow.
```

## Principe d'architecture

La logique métier est isolée dans `pipeline/transforms.py`, indépendamment d'Airflow.
Le DAG (`dags/ecommerce_lake_ingestion_dag.py`) se limite à orchestrer ces fonctions :
déclarer les tâches, leurs dépendances, et laisser Airflow gérer les reprises et le
parallélisme. Cette séparation permet de valider l'intégralité de la logique du
pipeline (`run_local_test.py`) indépendamment d'un environnement Airflow installé,
ce qui facilite les tests et le développement.

## Stockage du Data Lake

Les quatre zones du Data Lake (Raw, Bronze, Silver, Gold) sont matérialisées comme un
dossier local dans cette implémentation, qui sert de prototype. En production, ce même
emplacement serait un bucket de stockage objet (S3 ou MinIO) — le code de
`pipeline/transforms.py` est structuré pour que ce changement se limite à remplacer
les variables `LAKE_ROOT`/`SOURCE_DIR` par un client de stockage objet, sans modifier
la logique métier.

## Le contrôle qualité

La tâche `silver` du DAG appelle `load_silver()`, qui applique `run_dq_checkpoint()` —
le contrôle qualité s'exécute à l'intérieur du pipeline, entre Bronze et Silver, pas
après. Les règles actuelles (doublons, valeurs hors plage, clés orphelines, valeurs
manquantes) sont codées directement dans `transforms.py`. Une suite `great_expectations`
équivalente et plus formelle est disponible séparément dans `06_qualite_donnees/` ;
son intégration directe dans le DAG (remplacement de `run_dq_checkpoint()`) reste une
évolution possible, sans changement de structure du pipeline.

Comportement du contrôle qualité :
- les lignes en anomalie sont isolées dans une partition dédiée (`silver_rejects`), pas supprimées ;
- si le taux d'erreur dépasse un seuil configurable (10 % par défaut), la tâche échoue
  explicitement plutôt que de laisser passer des données dégradées vers Silver et Gold.

## Résultat d'une exécution complète

| Table | Bronze | Silver (valides) | Rejetées |
|---|---|---|---|
| dim_products | 300 | 300 | 0 |
| dim_customers | 5 000 | 5 000 | 0 |
| promotions | 120 | 120 | 0 |
| fact_transactions | 84 319 | 84 319 | 0 |
| stock_daily | 117 763 | 117 763 | 0 |
| web_events | 657 392 | 657 392 | 0 |

`dim_products` et `dim_customers` conservent des anomalies volontaires (casse
incohérente sur les catégories, valeurs manquantes sur la région et la tranche d'âge)
— signalées par le contrôle qualité mais non bloquantes, pour illustrer la détection
sans perte de données. Le détail figure dans `02_jeu_de_donnees/SOURCE_DATA_DICTIONARY.md`.

La zone Gold produit également deux tables agrégées : `daily_sales_by_product` (grain
jour × produit) et `product_performance` (grain produit), utilisées pour la prévision
de la demande et l'analyse de performance produit.

## Déploiement sur un environnement Airflow

1. Installer Airflow (voir la documentation officielle pour la version recommandée).
2. Copier `pipeline/` et `dags/ecommerce_lake_ingestion_dag.py` dans le dossier `dags/`
   de l'installation Airflow cible (ou exposer `pipeline/` comme package importable).
3. Adapter `SOURCE_DIR` et `LAKE_ROOT` dans `pipeline/transforms.py` pour pointer vers
   les emplacements de stockage cibles.
4. Activer le DAG `ecommerce_lake_ingestion` dans l'interface Airflow.
