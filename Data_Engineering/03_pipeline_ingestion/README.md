# Pipeline d'ingestion — Raw → Bronze → Silver → Gold

## Contenu

```
pipeline/transforms.py          Logique métier (extraction, typage, gate qualité, agrégation).
                                 Ne dépend pas d'Airflow — testable en local.
dags/ecommerce_lake_ingestion_dag.py   Le DAG Airflow : orchestration fine au-dessus de transforms.py.
run_local_test.py               Exécute la même séquence que le DAG, sans Airflow, pour valider la logique.
source_exports/                 Jeu de données synthétique (simulateur des exports amont).
lake/                            Résultat de l'exécution locale : raw/, bronze/, silver/, silver_rejects/, gold/.
```

## Mise à jour (17 août) — pipeline aligné avec les données livrées (v3)

Le pipeline (`pipeline/transforms.py`) a été mis en cohérence avec les données réellement
livrées dans Supabase : `source_exports/` contient maintenant les fichiers v3 (paniers
multi-produits, sessions web enrichies, `fact_stock` réconciliable), remplaçant les
anciens fichiers v1/v2. Une exécution complète (`run_local_test.py`) confirme que le
pipeline produit désormais exactement les mêmes volumes et passe les 4 vérifications de
l'audit du data scientist (0 partout). Les anciens fichiers sont conservés dans
`source_exports_OLD_backup/` par précaution.

## À propos du stockage du Lake (raw/bronze/silver/gold)

Dans ce projet, les 4 zones du Data Lake sont matérialisées comme un **dossier local**
(`lake/`), qui sert de prototype. En production, ce même chemin serait un bucket
**S3 ou MinIO** (stockage objet) — le code de `pipeline/transforms.py` est écrit pour
que ce changement se limite à remplacer `LAKE_ROOT`/`SOURCE_DIR` par un client S3
(`boto3` ou équivalent), sans toucher à la logique métier. Le dossier local n'est donc
pas un raccourci pris à la légère : c'est l'implémentation prototype d'une architecture
documentée pour du stockage objet (voir `Architecture_Technique_Schema_Donnees.docx`,
section "Choix techniques").

## Pourquoi ce découpage

Toute la logique métier est dans `pipeline/transforms.py`, indépendante d'Airflow. Le DAG
(`dags/ecommerce_lake_ingestion_dag.py`) ne fait qu'orchestrer ces fonctions : déclarer les
tâches, leurs dépendances, et laisser Airflow gérer les reprises et le parallélisme.

Avantage concret : `run_local_test.py` exécute exactement la même séquence
(`extract → bronze → silver → gold`) sans avoir besoin d'un environnement Airflow. C'est ce qui
a permis de valider tout le pipeline dans cet environnement, où Airflow n'est pas installable
(pas d'accès réseau pour pip). Le DAG a été vérifié syntaxiquement (`python -m py_compile`) mais
n'a pas pu être exécuté ici — il devra être testé dans ton environnement Airflow réel.

## Le gate qualité

La tâche `silver` (dans le DAG) appelle `load_silver()`, qui elle-même appelle
`run_dq_checkpoint()` — c'est le point d'insertion du contrôle qualité, **à l'intérieur** du
pipeline, pas après. Pour l'instant `run_dq_checkpoint()` contient des règles codées à la main
(doublons, quantités négatives, product_id orphelins, valeurs manquantes, casse incohérente).
À la prochaine étape, cette fonction sera remplacée par une vraie suite `great_expectations`,
sans que le DAG n'ait besoin de changer.

Comportement actuel :
- les lignes en anomalie sont isolées dans `lake/silver_rejects/<table>/ds=.../`, pas perdues ;
- si le taux d'erreur dépasse 10 % (configurable), la tâche échoue explicitement plutôt que de
  laisser passer des données trop dégradées vers Silver/Gold.

## Résultat de l'exécution locale (validation, données v3 — paniers + sessions + corrections d'audit)

| Table | Bronze | Silver (valides) | Rejetées | Raison |
|---|---|---|---|---|
| dim_products | 300 | 300 | 0 | 15 catégories en casse incohérente (signalées, non bloquantes) |
| dim_customers | 5 000 | 5 000 | 0 | 293 valeurs manquantes (signalées, non bloquantes) |
| promotions | 120 | 120 | 0 | — |
| fact_transactions | 84 319 | 84 319 | 0 | Paniers multi-produits (order_id partagé), promotions correctement ciblées |
| stock_daily | 117 763 | 117 763 | 0 | Réconciliation exacte (quantite_vendue, quantite_reapprovisionnee) |
| web_events | 657 392 | 657 392 | 0 | Sessions bornées (≤30 min), funnel toujours vue→achat |

Les 4 anomalies remontées par l'audit du data scientist (ciblage promo, réconciliation
stock, durée de session, ordre du funnel) ont été corrigées directement dans cette
version du pipeline — voir `pipeline/transforms.py`, fonctions `run_dq_checkpoint` et
`build_star_schema`.

Les 425 doublons injectés dans le jeu de données synthétique sont absorbés dès l'étape Bronze
(hygiène technique de base, avant même le gate qualité).

Gold produit deux tables : `daily_sales_by_product.csv` (grain jour × produit, pour le
forecasting) et `product_performance.csv` (grain produit, pour le pricing et le dashboard BI).

## Déployer dans un vrai Airflow

1. Installer Airflow (ex: `pip install apache-airflow` ou via `docker-compose` — voir la doc
   officielle Airflow pour la version recommandée).
2. Copier `pipeline/` et `dags/ecommerce_lake_ingestion_dag.py` dans le dossier `dags/` de ton
   installation Airflow (ou monter `pipeline/` comme package importable, ex: via `PYTHONPATH`
   ou `sys.path.insert` déjà présent en haut du DAG — adapter le chemin à ton déploiement).
3. Adapter `SOURCE_DIR` et `LAKE_ROOT` dans `pipeline/transforms.py` pour pointer vers de vrais
   emplacements (S3/MinIO plutôt que des chemins locaux, une fois hors du prototypage).
4. Activer le DAG `ecommerce_lake_ingestion` dans l'UI Airflow.

## Prochaine étape

Remplacer `run_dq_checkpoint()` par une vraie suite `great_expectations` (expectations
déclaratives, checkpoint, data docs générés automatiquement) — sans changer la structure du
pipeline ni du DAG.
