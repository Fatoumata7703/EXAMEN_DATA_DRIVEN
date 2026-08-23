# Data Engineering — DATA-PRICE

Livrables data engineering du projet DATA-PRICE, organisés par lot. Les données
utilisées sont entièrement synthétiques (statut `synthetic_academic_experiment`).

## Contenu

| Dossier | Contenu |
|---|---|
| `01_architecture/` | Architecture technique et schéma de données |
| `02_jeu_de_donnees/` | Scripts de génération du jeu de données synthétique et tables source |
| `03_pipeline_ingestion/` | Pipeline d'ingestion (Raw → Bronze → Silver → Gold) |
| `04_data_warehouse/` | Schéma en étoile : script de création SQL et dictionnaire de données |
| `05_journal_experimentation_v4/` | Journal d'expérimentation de prix et d'exposition aux recommandations |
| `06_qualite_donnees/` | Suite de contrôle qualité (great_expectations) |
| `07_documentation_transfert/` | Documentation de transfert vers l'équipe data science |

## État du schéma de données

Le schéma en étoile compte 9 tables, hébergées dans un entrepôt PostgreSQL (Supabase) :
4 dimensions (produit, client, date, promotion) et 5 tables de faits (ventes,
événements web, stock, expérimentation de prix, exposition aux recommandations).

Les deux tables du journal d'expérimentation (`fact_experimentation_prix`,
`fact_exposition_reco`) sont en version 4 : elles ont fait l'objet de plusieurs
cycles d'audit indépendant (voir `05_journal_experimentation_v4/README_journal_v4.md`
pour l'historique complet des corrections et leur justification).

## Reproductibilité

- Jeu de données source : seed fixée, reproductibilité vérifiée bit à bit (détail dans
  `02_jeu_de_donnees/README.md`).
- Journal d'expérimentation/exposition : seeds documentées, empreintes SHA-256,
  reproductibilité vérifiée par double exécution indépendante (détail dans
  `05_journal_experimentation_v4/README_journal_v4.md`).
