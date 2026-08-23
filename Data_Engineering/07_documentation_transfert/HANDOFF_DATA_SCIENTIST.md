# Handoff — Schéma en étoile pour l'entraînement des modèles

**Destinataire :** Data Scientist
**Version :** v1 — 2026-08-12
**Contenu :** `lake/gold/star_schema/` — 6 tables prêtes à l'emploi

## En bref

Ce sont des données **synthétiques mais cohérentes** (saisonnalité, élasticité prix,
funnel de navigation, ruptures de stock — tout est calibré et documenté). Elles ont
traversé le pipeline complet Raw → Bronze → Silver → Gold : dédupliquées, typées,
et les anomalies volontaires (doublons, FK orphelines, quantités négatives) ont été
isolées avant d'arriver ici. Tu peux les utiliser directement, sans retravail de nettoyage.

## Les 6 tables

| Table | Lignes | Grain | Sert pour |
|---|---|---|---|
| `fact_ventes` | 85 419 | 1 ligne = 1 produit vendu dans une commande | Forecasting, pricing |
| `fact_evenements_web` | 374 792 | 1 ligne = 1 événement (view/cart/purchase) | Recommandation |
| `dim_produit` | 300 | 1 ligne = 1 produit (SCD2, voir plus bas) | Features produit, jointure avec les 2 faits |
| `dim_client` | 5 000 | 1 ligne = 1 client (SCD2) | Segmentation, jointure avec les 2 faits |
| `dim_date` | 546 | 1 ligne = 1 jour, du 2025-02-01 au 2026-07-31 | Saisonnalité, jointure par date_key |
| `dim_promotion` | 120 | 1 ligne = 1 campagne de remise | Élasticité prix (jointure optionnelle sur fact_ventes) |

## Comment joindre

Toutes les clés sont des clés de substitution (`produit_key`, `client_key`, `date_key`,
`promo_key`) — pas les identifiants métier (`product_id`, `customer_id`). C'est voulu :
ça prépare le terrain pour l'historisation (voir SCD2 ci-dessous), donc joins-toi
toujours sur les clés `_key`, pas sur `product_id`/`customer_id` directement.

```
fact_ventes.produit_key       -> dim_produit.produit_key
fact_ventes.client_key        -> dim_client.client_key
fact_ventes.date_key          -> dim_date.date_key
fact_ventes.promo_key         -> dim_promotion.promo_key   (nullable : pas de promo)

fact_evenements_web.produit_key -> dim_produit.produit_key
fact_evenements_web.client_key  -> dim_client.client_key
fact_evenements_web.date_key    -> dim_date.date_key
```

100 % des clés de `fact_ventes` et `fact_evenements_web` sont résolues (vérifié — voir
la section anomalies plus bas pour comprendre pourquoi ce n'était pas le cas au premier
run).

## ⚠️ Point important : SCD Type 2 pas encore alimenté dans le temps

`dim_produit` et `dim_client` ont les colonnes `valid_from`, `valid_to`, `is_current`
— la structure est prête pour l'historisation (garder trace des changements de prix ou
de segment client dans le temps). **Mais à ce stade il n'y a qu'un seul snapshot** :
toutes les lignes ont `is_current=True` et `valid_to` vide. Si tu as besoin de savoir
"quel était le prix à la date X" pour du feature engineering historique, ce n'est pas
encore fiable — considère `prix_base_xof` comme le prix actuel, pas un historique.
Je te préviendrai quand l'historisation réelle sera branchée.

## Anomalies déjà traitées (pour info, pas pour toi à re-découvrir)

| Anomalie | Où | Volume | Traitement |
|---|---|---|---|
| Doublons exacts | toutes tables | ~425 lignes (fact_transactions) | Supprimés dès l'étape Bronze |
| Quantités négatives | fact_ventes | 85 lignes | Isolées, exclues de fact_ventes |
| `product_id` orpheline (`P99999`) | fact_ventes ET fact_evenements_web | 42 + 72 lignes | Isolées, exclues des deux tables de faits |
| Casse incohérente sur les catégories | dim_produit | 15 lignes | Corrigée (mappée vers la forme canonique) |
| Valeurs manquantes région/âge | dim_client | 293 lignes | Conservées avec le libellé "Non renseigné" plutôt que supprimées — traite ça comme une catégorie à part entière si tu fais du feature engineering catégoriel |

Le point `product_id` orpheline vaut le détour : la même anomalie injectée dans les
transactions s'est propagée naturellement jusque dans les logs de navigation (une
session d'achat sur ce produit fantôme avait bien généré des vues avant l'achat). Les
deux tables de faits l'ont donc filtrée indépendamment.

## Suite

Je finalise en parallèle la suite `great_expectations` (règles de qualité formalisées,
remplaçant les vérifications codées à la main utilisées pour produire cette version) et
je te enverrai une v2 si des lignes supplémentaires changent de statut. Rien ne devrait
changer structurellement (mêmes tables, mêmes clés).
