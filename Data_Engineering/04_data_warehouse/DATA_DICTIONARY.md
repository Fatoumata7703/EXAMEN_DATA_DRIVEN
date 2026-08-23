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
| `fact_evenements_web` | 657 392 | 1 ligne = 1 événement de navigation |
| `fact_stock` | 117 763 | 1 ligne = niveau de stock d'un produit en fin de journée |
| `fact_experimentation_prix` | 11 799 | 1 ligne = une décision de prix évaluée pour un produit, une semaine donnée |
| `fact_exposition_reco` | 221 080 | 1 ligne = une recommandation affichée à un visiteur, dans une liste |

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

## `fact_experimentation_prix`

Grain : une décision de prix évaluée pour un produit, une semaine donnée. Table conçue
comme une expérience randomisée synthétique (statut `synthetic_academic_experiment`) :
assignation persistante par produit à un groupe de traitement, pour permettre une
analyse causale de l'effet d'une remise, indépendamment des promotions historiques
(non randomisées).

| Colonne | Type | Description |
|---|---|---|
| decision_id | text (PK) | Identifiant unique de la décision |
| experiment_id | text | Identifiant de la vague hebdomadaire d'expérimentation |
| produit_key | text (FK → dim_produit) | |
| decision_timestamp | timestamptz | Horodatage de la décision, UTC |
| treatment_group | text | `controle_0pct` / `traitement_5pct` / `traitement_10pct` / `traitement_15pct` — assignation persistante par produit sur toute l'expérience, stratifiée par catégorie et classe ABC |
| eligible_for_discount | boolean | Vrai si le prix respecte le plancher (prix ≥ coût) et la marge minimale (5%) |
| discount_proposed / discount_applied | int / int | Remise du groupe assigné, et remise réellement appliquée (0 si le garde-fou bloque la proposition) |
| prix_applique_xof | numeric | Prix recalculé après le contrôle d'éligibilité, à partir de `discount_applied` |
| propensity_score | numeric | Probabilité d'assignation au groupe (0,25 — 4 groupes équiprobables) |
| product_impressions | int | Cumul d'expositions recommandation strictement antérieur à `decision_timestamp` |
| stock_at_decision | int | Stock de clôture de la veille (jamais le jour même de la décision) |
| categorie / classe_abc | text / text | Classe ABC calculée sur une fenêtre de warm-up de 90 jours, strictement antérieure au début de l'expérience |
| cold_start_warmup | boolean | Vrai si le produit n'a eu aucune vente confirmée pendant le warm-up |
| units_sold_window_7j / revenue_window_xof_7j / margin_window_xof_7j | int / numeric / numeric | Résultats simulés comme fonction causale de `discount_applied` (élasticité documentée et bruit contrôlé) |
| fenetre_observation_debut / fin | timestamptz / timestamptz | Bornes explicites de la fenêtre d'observation de 7 jours |
| statut_experience | text | Toujours `synthetic_academic_experiment` |

## `fact_exposition_reco`

Grain : une recommandation affichée à un visiteur, dans une liste (slate). Chaque
liste est construite exclusivement avec des informations disponibles strictement
avant l'impression.

| Colonne | Type | Description |
|---|---|---|
| recommendation_id | text (PK) | Identifiant unique de l'exposition |
| slate_id | text | Identifiant partagé par tous les produits d'une même liste affichée |
| experiment_id / assignment_id | text / text | Identifiants de l'expérience et de l'assignation persistante du visiteur |
| client_key / anonymous_id | text / text | Mutuellement exclusifs — visiteur connu ou anonyme |
| session_id | text (FK → fact_evenements_web) | Session réelle correspondante, toujours renseignée |
| model_version | text | `popularite_globale_v1` (contrôle) ou `challenger_affinite_categorie_v1` (traitement) |
| model_score | numeric | Score calculé par le modèle correspondant, à partir d'informations strictement antérieures à l'impression |
| produit_key | text (FK → dim_produit) | Produit recommandé |
| rank | int | Position dans la liste, dérivée du tri par `model_score` |
| impression_timestamp | timestamptz | Horodatage de l'affichage, UTC — toujours dans les bornes réelles de la session |
| viewed_after_impression / view_timestamp | boolean / timestamptz | Vue postérieure à l'impression (la source ne distingue pas un clic d'une vue) |
| added_to_cart_after / add_to_cart_timestamp | boolean / timestamptz | Ajout au panier postérieur à l'impression |
| purchased_after / purchase_timestamp | boolean / timestamptz | Achat postérieur à l'impression |
| experiment_group | text | `controle` / `traitement`, assignation persistante par client ou visiteur anonyme |
| group_assignment_propensity | numeric | Probabilité d'assignation au groupe d'expérience |
| session_selection_probability | numeric | Probabilité que cette session ait été échantillonnée |
| product_exposure_probability | numeric | Probabilité que ce produit précis figure dans la liste |

## Ce qui n'est PAS dans Supabase

Les tables intermédiaires du pipeline (`dim_products`, `dim_customers`, `fact_transactions`,
`promotions`, `web_events` — les noms anglais bruts) existent seulement dans la zone Silver
du data lake local, pas dans Supabase.
