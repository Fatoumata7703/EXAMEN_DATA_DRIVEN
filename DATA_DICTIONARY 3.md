# Data Dictionary — Schéma en étoile (Supabase)

**⚠️ Remplace l'ancienne version de ce document**, qui décrivait le jeu de données brut
avant sa transformation en schéma en étoile. Les noms de tables ci-dessous sont ceux
**réellement présents dans Supabase** — vérifiés contre `create_star_schema.sql`.

## Vue d'ensemble

| Table | Lignes | Grain |
|---|---|---|
| `dim_produit` | 300 | 1 ligne = 1 produit |
| `dim_client` | 5 000 | 1 ligne = 1 client |
| `dim_date` | 546 | 1 ligne = 1 jour (2025-02-01 → 2026-07-31) |
| `dim_promotion` | 120 | 1 ligne = 1 campagne de remise |
| `fact_ventes` | 85 419 | 1 ligne = 1 produit vendu dans une commande |
| `fact_evenements_web` | 374 792 | 1 ligne = 1 événement de navigation |
| `fact_stock` | 117 763 | 1 ligne = niveau de stock d'un produit en fin de journée |

## `dim_produit`

| Colonne | Type | Description |
|---|---|---|
| produit_key | text (PK) | Clé de substitution |
| product_id | text | Identifiant métier stable |
| product_name | text | |
| categorie | text | 8 catégories, casse normalisée |
| marque | text | |
| prix_base_xof | numeric | Prix catalogue actuel |
| cout_xof | numeric | Coût d'achat |
| valid_from / valid_to / is_current | date / date / boolean | SCD Type 2 — un seul snapshot pour l'instant, tout est `is_current=true` |

## `dim_client`

| Colonne | Type | Description |
|---|---|---|
| client_key | text (PK) | Clé de substitution |
| customer_id | text | Identifiant métier stable |
| region | text | "Non renseigné" si manquant à la source |
| age_bracket | text | "Non renseigné" si manquant à la source |
| segment_fidelite | text | nouveau / occasionnel / regulier / vip |
| valid_from / valid_to / is_current | date / date / boolean | SCD Type 2, même remarque que dim_produit |

## `dim_date`

| Colonne | Type | Description |
|---|---|---|
| date_key | text (PK) | Format `YYYYMMDD`, ex: `20250201` |
| date_complete | date | |
| annee / mois / jour | int | |
| jour_semaine | text | |
| est_weekend | boolean | |

## `dim_promotion`

| Colonne | Type | Description |
|---|---|---|
| promo_key | text (PK) | Clé de substitution |
| promotion_id | text | Identifiant métier stable |
| portee | text | `category` ou `product` |
| cible | text | Nom de catégorie ou product_id selon `portee` |
| remise_pct | int | |
| date_debut / date_fin | date | |

## `fact_ventes`

| Colonne | Type | Description |
|---|---|---|
| vente_id | text (PK) | |
| produit_key | text (FK → dim_produit) | |
| client_key | text (FK → dim_client) | |
| date_key | text (FK → dim_date) | |
| promo_key | text (FK → dim_promotion, nullable) | Null = pas de promo, c'est normal |
| quantite | int | |
| montant_net_xof | numeric | Montant réellement payé |

## `fact_evenements_web`

| Colonne | Type | Description |
|---|---|---|
| event_id | text (PK) | |
| produit_key | text (FK → dim_produit) | |
| client_key | text (FK → dim_client) | |
| date_key | text (FK → dim_date) | |
| type_event | text | view / add_to_cart / purchase |
| appareil | text | mobile / desktop / tablet |

## `fact_stock`

| Colonne | Type | Description |
|---|---|---|
| produit_key | text (FK → dim_produit) | |
| date_key | text (FK → dim_date) | |
| niveau_stock | int | Stock en fin de journée. Clé primaire composite (produit_key, date_key) |

## Ce qui n'est PAS dans Supabase

Les tables intermédiaires du pipeline (`dim_products`, `dim_customers`, `fact_transactions`,
`promotions`, `web_events` — les noms anglais bruts) existent seulement dans la zone Silver
du data lake local, pas dans Supabase.
