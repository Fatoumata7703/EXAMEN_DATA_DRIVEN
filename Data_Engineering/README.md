# Data Engineering — DATA-PRICE

Livrables data engineering du projet DATA-PRICE (Mozart Codjo), organisés par lot.
Toutes les données sont synthétiques (statut `synthetic_academic_experiment`).

## Contenu

| Dossier | Contenu |
|---|---|
| `01_architecture/` | Architecture technique + schéma de données (docx), à jour au 22/08 |
| `02_jeu_de_donnees/` | 3 scripts de génération numérotés + les 6 tables source, reproductibilité vérifiée au bit près |
| `03_pipeline_ingestion/` | Pipeline Airflow Raw→Bronze→Silver→Gold, testable sans Airflow (`run_local_test.py`) |
| `04_data_warehouse/` | SQL de création du schéma en étoile (7 tables) + dictionnaire de données |
| `05_journal_experimentation_v4/` | `fact_experimentation_prix` et `fact_exposition_reco` — v4, reconstruites suite à l'audit DS, avec lineage (script, seed, empreinte SHA-256) |
| `06_qualite_donnees/` | Suite great_expectations (non exécutée faute d'accès réseau en développement — à lancer et vérifier) |
| `07_documentation_transfert/` | Documents de handoff pour l'équipe data science |

## État à jour du 23 août

- Schéma en étoile complet en ligne sur Supabase (7 tables historiques + 2 tables du
  journal d'expérimentation/exposition).
- Un bug sur `product_impressions` (fact_experimentation_prix v4) a été corrigé le 22
  août — détail complet dans `05_journal_experimentation_v4/README_journal_v4.md`.
  Si tu réimportes cette table, utilise le fichier daté d'aujourd'hui, pas une version
  antérieure.
- `great_expectations` n'a jamais pu être exécuté dans l'environnement de
  développement (pas d'accès réseau) — le script est prêt et vérifié en pandas pur,
  mais son exécution réelle reste à confirmer.

## Reproductibilité

- Jeu de données source : seed=42, reproductibilité vérifiée au bit près (voir
  `02_jeu_de_donnees/README.md`).
- Journal d'expérimentation/exposition v4 : seeds 47/48/49, empreintes SHA-256
  documentées, reproductibilité vérifiée par double exécution indépendante (voir
  `05_journal_experimentation_v4/README_journal_v4.md`).
