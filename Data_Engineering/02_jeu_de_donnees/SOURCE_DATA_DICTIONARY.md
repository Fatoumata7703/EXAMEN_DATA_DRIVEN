# Data Dictionary — Jeu de données synthétique (source)

Documente les **6 tables source**, telles que produites par les scripts
`01_generate_dimensions.py` → `02_generate_transactions.py` → `03_generate_web_events.py`.
Ce sont les tables qui entrent dans le pipeline d'ingestion (zone Raw), **avant**
transformation en schéma en étoile. Pour le schéma en étoile final (Gold, dans
Supabase), voir `DATA_DICTIONARY.md` (livrable séparé, déjà fourni).

Contexte : marché e-commerce simulé (Afrique de l'Ouest, XOF/FCFA), période
**2025-02-01 → 2026-07-31** (546 jours), seed=42 (reproductible à l'identique).

## Vue d'ensemble

| Table | Lignes | Généré par |
|---|---|---|
| `dim_products` | 300 | 01_generate_dimensions.py |
| `dim_customers` | 5 000 | 01_generate_dimensions.py |
| `promotions` | 120 | 01_generate_dimensions.py |
| `fact_transactions` | 84 319 | 02_generate_transactions.py |
| `stock_daily` | 117 763 | 02_generate_transactions.py |
| `web_events` | 657 392 | 03_generate_web_events.py |

## `dim_products`

| Colonne | Type | Description |
|---|---|---|
| product_id | string (PK) | ex: `P00001` |
| product_name | string | |
| category | string | 8 catégories. ⚠️ 15 lignes ont la casse en MAJUSCULES (anomalie volontaire, corrigée en aval en Gold) |
| brand | string | |
| base_price_xof | float | prix catalogue |
| cost_xof | float | coût d'achat |
| popularity_score | float | facteur de demande de base utilisé par la simulation |
| launch_date | date | le produit n'apparaît dans aucune vente avant cette date |
| initial_stock | int | stock de départ |

## `dim_customers`

| Colonne | Type | Description |
|---|---|---|
| customer_id | string (PK) | ex: `C000001` |
| full_name | string | |
| region | string | 10 villes du Sénégal. ⚠️ ~3% de nulls (anomalie volontaire) |
| age_bracket | string | 5 tranches. ⚠️ ~3% de nulls (anomalie volontaire) |
| signup_date | date | |
| loyalty_segment | string | nouveau / occasionnel / regulier / vip |

## `promotions`

| Colonne | Type | Description |
|---|---|---|
| promotion_id | string (PK) | |
| scope | string | `category` ou `product` |
| target | string | nom de catégorie ou `product_id` selon `scope` |
| discount_pct | int | 5 à 40% |
| start_date / end_date | date | |

## `fact_transactions`

Grain : une ligne = un produit dans un panier. Plusieurs lignes partagent le même
`order_id` si le panier contient plusieurs produits (généré nativement par
`02_generate_transactions.py`, pas un regroupement a posteriori — voir le
docstring du script pour le détail de la méthode).

| Colonne | Type | Description |
|---|---|---|
| ligne_id_origine | string (PK) | identifiant unique de la ligne |
| order_id | string | identifiant de commande, partagé par les lignes d'un même panier (1 à 4 produits) |
| order_status | string | confirmee (~95%) / annulee (~3%) / retournee (~2%) |
| customer_id | string (FK → dim_customers) | |
| product_id | string (FK → dim_products) | |
| order_date | date | |
| quantity | int | |
| unit_price_xof | float | prix réellement payé (remise déjà appliquée) |
| promotion_id | string (FK → promotions, nullable) | tracé directement à la source — corrigé après l'audit du 16 août (ne plus jamais réattribuer une promotion après coup par simple correspondance de `discount_pct`) |
| discount_pct_applied | int | 0 si pas de promo |

## `stock_daily`

Grain : niveau de stock d'un produit en fin de journée.

| Colonne | Type | Description |
|---|---|---|
| product_id | string (FK) | |
| date | date | |
| stock_level | int | stock en fin de journée, après réapprovisionnement éventuel |
| quantite_vendue | int | quantité vendue ce jour-là, tous statuts confondus |
| quantite_reapprovisionnee | int | quantité rajoutée ce jour-là (0 la plupart des jours) |

Réconciliation exacte : `stock_level(t) = stock_level(t-1) - quantite_vendue(t) + quantite_reapprovisionnee(t)`,
vérifiée à résidu zéro sur les 117 763 lignes (audit du 16 août).

## `web_events`

Grain : un événement de navigation (view / add_to_cart / purchase).

| Colonne | Type | Description |
|---|---|---|
| event_id | string (PK) | |
| session_id | string | fin de session = 30 min d'inactivité (vérifié, 0 violation) |
| customer_id | string (FK, nullable) | rempli uniquement pour les visiteurs connus |
| anonymous_id | string (nullable) | rempli uniquement pour les visiteurs anonymes (~35% des sessions de navigation pure). Mutuellement exclusif avec customer_id |
| product_id | string (FK) | |
| event_type | string | view / add_to_cart / purchase |
| event_timestamp | datetime ISO | UTC explicite |
| device | string | mobile (72%) / desktop (22%) / tablet (6%) |
| referral_source | string | organic_search, social_media, direct, email_campaign, paid_ads, affiliate |
| canal | string | toujours `web` (pas d'app mobile simulée) |
| order_id | string, nullable | rempli uniquement sur les événements `purchase`, relie à `fact_transactions.order_id` |
| quantity | int, nullable | rempli uniquement sur les événements `purchase` |
| est_bot | boolean | ~1% des sessions (rafale d'événements sans pacing réaliste) |

## Anomalies volontaires (pour le travail de data quality en aval)

| Anomalie | Où | Volume |
|---|---|---|
| Casse incohérente | dim_products.category | 15 lignes |
| Valeurs manquantes | dim_customers.region / age_bracket | ~3% |
| Doublons exacts | absorbés dès l'étape Bronze du pipeline | — |

## Ordre de génération et reproductibilité

```
01_generate_dimensions.py   -> dim_products.csv, dim_customers.csv, promotions.csv
02_generate_transactions.py -> fact_transactions.csv.gz, stock_daily.csv.gz
03_generate_web_events.py   -> web_events.csv.gz
```

Exécuter dans cet ordre (02 et 03 dépendent des fichiers produits par 01, 03 dépend
aussi de 02). Reproductibilité vérifiée : une exécution complète depuis zéro produit
des fichiers **identiques au bit près** à ceux livrés ici (seed=42 partout).

```bash
export OUT_DIR=./donnees
export SOURCE_DIR=./donnees
python3 01_generate_dimensions.py
python3 02_generate_transactions.py
python3 03_generate_web_events.py
```
