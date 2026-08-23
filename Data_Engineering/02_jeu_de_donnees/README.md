# Jeu de données synthétique documenté et scripts de génération

## Contenu

```
scripts/
  01_generate_dimensions.py     dim_products, dim_customers, promotions
  02_generate_transactions.py   fact_transactions, stock_daily
  03_generate_web_events.py     web_events
donnees/
  dim_products.csv
  dim_customers.csv
  promotions.csv
  fact_transactions.csv.gz
  stock_daily.csv.gz
  web_events.csv.gz
SOURCE_DATA_DICTIONARY.md       dictionnaire complet des 6 tables ci-dessus
```

## Organisation des scripts

`dim_products`, `dim_customers` et `promotions` sont générés indépendamment de la
logique transactionnelle : ils ne dépendent d'aucun panier ni d'aucune session
utilisateur. `fact_transactions`, `stock_daily` et `web_events` reposent en revanche
sur une simulation de paniers et de sessions de navigation cohérente entre elles
(un produit acheté dans une session doit correspondre à un événement de navigation
réel, un panier peut contenir plusieurs produits, le stock doit se réconcilier avec
les ventes). Séparer la génération en trois scripts numérotés, exécutés dans l'ordre,
reflète cette dépendance et permet de régénérer uniquement la partie transactionnelle
si nécessaire, sans retoucher aux référentiels produit/client/promotion.

## Reproductibilité

Une exécution complète (01 → 02 → 03) produit des fichiers identiques bit à bit à
ceux du dossier `donnees/` (seed fixée à 42 dans l'ensemble des trois scripts).

```bash
cd scripts
python3 01_generate_dimensions.py
python3 02_generate_transactions.py
python3 03_generate_web_events.py
```

Les scripts écrivent par défaut dans `../donnees/` (relatif à leur propre
emplacement). Un autre répertoire de sortie peut être précisé via la variable
d'environnement `OUT_DIR`.

## Utilisation en aval

- Pipeline d'ingestion : voir `03_pipeline_ingestion/`
- Schéma en étoile (Supabase) : voir `04_data_warehouse/`
- Journal d'expérimentation et d'exposition : voir `05_journal_experimentation_v4/`
