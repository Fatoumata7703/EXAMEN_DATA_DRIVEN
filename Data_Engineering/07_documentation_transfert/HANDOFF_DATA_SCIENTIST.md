# Handoff — Schéma en étoile pour l'entraînement des modèles

**Destinataire :** équipe data science
**Contenu :** entrepôt de données Supabase (PostgreSQL) — 9 tables

## Vue d'ensemble

Les données sont synthétiques mais cohérentes (saisonnalité, élasticité prix, funnel
de navigation, ruptures de stock) et ont traversé le pipeline complet Raw → Bronze →
Silver → Gold : typées, dédupliquées, avec un contrôle qualité appliqué avant leur
matérialisation dans le schéma en étoile. Le dictionnaire de données complet figure
dans `04_data_warehouse/DATA_DICTIONARY.md`.

## Les 9 tables

| Table | Lignes | Grain |
|---|---|---|
| `dim_produit` | 300 | 1 ligne = 1 produit |
| `dim_client` | 5 000 | 1 ligne = 1 client |
| `dim_date` | 546 | 1 ligne = 1 jour (2025-02-01 → 2026-07-31) |
| `dim_promotion` | 120 | 1 ligne = 1 campagne de remise |
| `fact_ventes` | 84 319 | 1 ligne = 1 produit vendu dans une commande |
| `fact_evenements_web` | 657 392 | 1 ligne = 1 événement de navigation |
| `fact_stock` | 117 763 | 1 ligne = niveau de stock d'un produit en fin de journée |
| `fact_experimentation_prix` | 11 799 | 1 ligne = une décision de prix pour un produit, une semaine |
| `fact_exposition_reco` | 221 080 | 1 ligne = une recommandation affichée à un visiteur |

## Règles de jointure

Toutes les jointures se font sur les clés de substitution (`produit_key`,
`client_key`, `date_key`, `promo_key`), jamais sur les identifiants métier
(`product_id`, `customer_id`). Cette convention prépare l'historisation des
dimensions produit et client (SCD Type 2).

```
fact_ventes.produit_key             -> dim_produit.produit_key
fact_ventes.client_key              -> dim_client.client_key
fact_ventes.date_key                -> dim_date.date_key
fact_ventes.promo_key               -> dim_promotion.promo_key      (nullable)

fact_evenements_web.produit_key     -> dim_produit.produit_key
fact_evenements_web.client_key      -> dim_client.client_key
fact_evenements_web.date_key        -> dim_date.date_key

fact_experimentation_prix.produit_key -> dim_produit.produit_key

fact_exposition_reco.produit_key    -> dim_produit.produit_key
fact_exposition_reco.client_key     -> dim_client.client_key        (nullable)
fact_exposition_reco.session_id     -> fact_evenements_web.session_id
```

100 % des clés sont résolues (vérifié).

## Historisation (SCD Type 2)

`dim_produit` et `dim_client` portent les colonnes `valid_from`, `valid_to`,
`is_current`, préparant la traçabilité des changements de prix ou de segment client
dans le temps. À ce stade, un seul snapshot existe par entité : toutes les lignes ont
`is_current = true` et `valid_to` vide. Le champ `prix_base_xof` doit être considéré
comme le prix catalogue actuel, pas comme un historique de prix.

## Tables d'expérimentation et d'exposition

`fact_experimentation_prix` et `fact_exposition_reco` portent le statut
`synthetic_academic_experiment` : ce sont des expériences randomisées entièrement
simulées, pas des expériences réellement exécutées en production. Elles permettent de
tester un pipeline d'analyse causale de bout en bout (assignation randomisée,
garde-fous, contrôle des fuites de cible, inférence statistique au grain correct),
sans revendiquer d'effet commercial réel. Le détail de leur construction et des
corrections apportées au fil des audits figure dans
`05_journal_experimentation_v4/README_journal_v4.md`.

Trois champs demandés lors de la spécification initiale (prix concurrents, budget de
campagne marketing, ventes perdues) ne sont pas inclus, faute de source fiable pour
les renseigner dans ce projet — choix documenté plutôt que colonnes vides.

## Anomalies connues sur les dimensions

| Anomalie | Table | Volume | Traitement |
|---|---|---|---|
| Casse incohérente sur les catégories | `dim_produit` | 15 lignes | Normalisée vers la forme canonique |
| Valeurs manquantes (région, tranche d'âge) | `dim_client` | 293 lignes | Conservées avec le libellé "Non renseigné" |

Ces deux anomalies sont volontaires, injectées pour démontrer la capacité du
pipeline à les détecter. Elles ne concernent que les dimensions produit et client ;
les tables de faits ne présentent pas d'anomalie résiduelle après le passage par le
contrôle qualité (Bronze → Silver).
