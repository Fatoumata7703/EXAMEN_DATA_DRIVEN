# Jeu de données synthétique documenté + scripts de génération

Livrable : "Jeu de données (synthétique documenté) et scripts d'ingestion".

## Contenu

```
scripts/
  01_generate_dimensions.py     dim_products, dim_customers, promotions
  02_generate_transactions.py   fact_transactions, stock_daily (paniers réels, audité)
  03_generate_web_events.py     web_events (sessions, funnel, anonymes, bots)
donnees/
  dim_products.csv
  dim_customers.csv
  promotions.csv
  fact_transactions.csv.gz
  stock_daily.csv.gz
  web_events.csv.gz
SOURCE_DATA_DICTIONARY.md       dictionnaire complet des 6 tables ci-dessus
```

## Pourquoi 3 scripts et pas 1

`dim_products`/`dim_customers`/`promotions` ne dépendent d'aucun panier ni d'aucune
session — ils n'ont jamais changé depuis la première génération. `fact_transactions`,
`stock_daily` et `web_events` ont en revanche été régénérés le 16-17 août suite à un
audit du data scientist qui a révélé 4 bugs (paniers non natifs, promotions mal
ciblées, stock non réconciliable, sessions incohérentes) — tous corrigés et vérifiés.
Séparer en 3 scripts numérotés documente cette histoire au lieu de la cacher dans un
seul fichier monolithique où la moitié du code serait obsolète sans que ce soit visible.

## Reproductibilité — vérifiée, pas supposée

Une exécution complète (01 → 02 → 03) dans un environnement propre produit des
fichiers **identiques au bit près** à ceux du dossier `donnees/` (vérifié avec
`DataFrame.equals()` sur les 6 tables avant cette livraison, seed=42 partout).

```bash
export OUT_DIR=./donnees
export SOURCE_DIR=./donnees
cd scripts
python3 01_generate_dimensions.py
python3 02_generate_transactions.py
python3 03_generate_web_events.py
```

## Ce jeu de données alimente directement

- Le pipeline d'ingestion (livrable séparé : Raw → Bronze → Silver → Gold)
- Le schéma en étoile dans Supabase (voir `DATA_DICTIONARY.md`, livrable séparé)
- Le journal d'exposition/expérimentation (voir `README_journal_v2.md`, livrable séparé)
