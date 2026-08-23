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
| `fact_ventes` | 84 319 | 1 ligne = 1 produit vendu dans une commande (plusieurs lignes peuvent partager le même `order_id` si panier multi-produits) |
| `fact_evenements_web` | 657 480 | 1 ligne = 1 événement de navigation |
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
| vente_id | text (PK) | Identifiant unique de la ligne (1 produit dans un panier) |
| produit_key | text (FK → dim_produit) | |
| client_key | text (FK → dim_client) | |
| date_key | text (FK → dim_date) | |
| promo_key | text (FK → dim_promotion, nullable) | Null = pas de promo, c'est normal |
| quantite | int | |
| montant_net_xof | numeric | Montant réellement payé |
| order_id | text | Identifiant de commande — **partagé par toutes les lignes d'un même panier**. Un panier contient 1 à 4 produits (55% à 1 seul, 45% multi-produits). |
| statut_commande | text | `confirmee` (~95%), `annulee` (~3%), `retournee` (~2%). Les lignes annulées/retournées sont conservées, pas supprimées — filtrer sur `statut_commande = 'confirmee'` pour la demande réelle. |

## `fact_evenements_web`

| Colonne | Type | Description |
|---|---|---|
| event_id | text (PK) | |
| session_id | text | Regroupe les événements d'une même visite. Fin de session = 30 min d'inactivité. |
| produit_key | text (FK → dim_produit) | |
| client_key | text (FK → dim_client, nullable) | Rempli uniquement pour les visiteurs connus |
| anonymous_id | text (nullable) | Rempli uniquement pour les visiteurs anonymes. **Mutuellement exclusif avec client_key** (jamais les deux, jamais aucun des deux) |
| date_key | text (FK → dim_date) | |
| event_timestamp | timestamptz | Horodatage complet, UTC explicite (marché Dakar = UTC+0, donc heure locale = heure UTC) |
| type_event | text | view / add_to_cart / purchase (pas de "clic" distinct d'une "vue" — non modélisé) |
| appareil | text | mobile / desktop / tablet |
| source_trafic | text | organic_search / social_media / direct / email_campaign / paid_ads / affiliate |
| canal | text | Toujours `web` — pas d'app mobile distincte simulée |
| order_id | text (nullable) | Rempli **uniquement** sur les événements `purchase`, relie l'événement à la commande dans `fact_ventes` |
| quantity | int (nullable) | Rempli **uniquement** sur les événements `purchase` |
| est_bot | boolean | ~1% des sessions (mais ~5,4% des lignes, car une session bot génère 15-40 événements en rafale) |

## `fact_stock`

| Colonne | Type | Description |
|---|---|---|
| produit_key | text (FK → dim_produit) | |
| date_key | text (FK → dim_date) | |
| niveau_stock | int | Stock en fin de journée. Clé primaire composite (produit_key, date_key) |
| quantite_vendue | int | Quantité vendue ce jour-là, tous statuts confondus (confirmée/annulée/retournée) |
| quantite_reapprovisionnee | int | Quantité rajoutée au stock ce jour-là (0 la plupart des jours) |

Réconciliation exacte : `niveau_stock(t) = niveau_stock(t-1) - quantite_vendue(t) + quantite_reapprovisionnee(t)`,
vérifiée à résidu zéro sur les 117 763 lignes. Le stock est décrémenté à l'achat quel que
soit le statut final de la commande — aucune réintégration en stock au moment d'une
annulation/retour n'est modélisée dans cette version.

## Ce qui n'est PAS dans Supabase

Les tables intermédiaires du pipeline (`dim_products`, `dim_customers`, `fact_transactions`,
`promotions`, `web_events` — les noms anglais bruts) existent seulement dans la zone Silver
du data lake local, pas dans Supabase.
