# Guide tables → modèles

**Source :** Supabase — schéma en étoile (9 tables), voir `04_data_warehouse/DATA_DICTIONARY.md`
pour le détail complet des colonnes.

Ce document répond à une question : quelles tables utiliser pour quel modèle.

---

## 1. Prévision de la demande

| Table | Colonnes utiles | Rôle |
|---|---|---|
| `fact_ventes` | `quantite`, `date_key`, `produit_key`, `montant_net_xof` | Variable cible (quantité vendue par produit et par jour) |
| `dim_date` | `date_complete`, `mois`, `jour_semaine`, `est_weekend` | Features calendaires (saisonnalité, effet week-end) |
| `dim_produit` | `categorie`, `marque`, `prix_base_xof` | Features produit (chaque catégorie a sa propre saisonnalité) |
| `dim_promotion` | `remise_pct`, `date_debut`, `date_fin` | Signal exogène : une promotion active fait mécaniquement monter la demande |
| `fact_stock` | `niveau_stock`, `quantite_vendue`, `quantite_reapprovisionnee`, `produit_key`, `date_key` | Contrainte de stock, indispensable pour distinguer une absence de demande d'une rupture de stock |

**Construction typique :** agréger `fact_ventes` par `produit_key` × `date_key` (somme
de `quantite`) pour obtenir une série temporelle par produit, puis joindre `dim_date`,
`dim_produit` et `fact_stock` pour les features et pour identifier les jours de
rupture (`niveau_stock` bas ou nul).

---

## 2. Simulation de remise

| Table | Colonnes utiles | Rôle |
|---|---|---|
| `fact_ventes` | `quantite`, `montant_net_xof`, `produit_key`, `date_key` | Prix effectif payé (`montant_net_xof / quantite`) et effet sur la quantité |
| `dim_produit` | `prix_base_xof`, `cout_xof`, `categorie` | Prix catalogue, coût (pour la marge), élasticité par catégorie |
| `dim_promotion` | `remise_pct` | Variation de prix historique (non randomisée — voir limite ci-dessous) |
| `dim_date` | `mois`, `est_weekend` | Contrôle de l'effet saisonnier |
| `fact_experimentation_prix` | `treatment_group`, `discount_applied`, `units_sold_window_7j`, `revenue_window_xof_7j`, `margin_window_xof_7j` | Expérience randomisée synthétique, conçue pour une analyse causale — voir limite ci-dessous |

**Construction typique :** pour une analyse à partir des données historiques,
régresser `quantite` sur le prix effectif en contrôlant par mois et catégorie.
`cout_xof` permet de transformer une élasticité estimée en recommandation de prix
sous contrainte de marge minimale.

**Limite à connaître :** les remises historiques (`dim_promotion`) ne sont pas
randomisées — leur variation est confondue avec d'autres facteurs (catégorie,
saisonnalité), ce qui ne permet pas d'estimer un effet causal à partir de
`fact_ventes` seule. `fact_experimentation_prix` propose un protocole randomisé
(assignation persistante par produit, groupes de traitement stratifiés), mais reste
une expérience synthétique — voir `05_journal_experimentation_v4/README_journal_v4.md`
pour l'analyse de significativité associée.

Note : `promo_key` est nullable dans `fact_ventes` — une vente sans promotion a
`promo_key = null`, ce qui correspond au cas normal. Filtrer sur
`statut_commande = 'confirmee'` pour exclure les commandes annulées ou retournées
d'une analyse de demande réelle.

---

## 3. Recommandation produit

| Table | Colonnes utiles | Rôle |
|---|---|---|
| `fact_evenements_web` | `session_id`, `client_key`/`anonymous_id`, `produit_key`, `type_event`, `event_timestamp` | Funnel de navigation complet (view / add_to_cart / purchase) |
| `fact_ventes` | `order_id`, `client_key`, `produit_key` | Paniers réels : plusieurs lignes partagent le même `order_id`, signal direct pour du market basket analysis |
| `fact_exposition_reco` | `slate_id`, `rank`, `model_score`, `viewed_after_impression`, `added_to_cart_after`, `purchased_after` | Journal d'exposition : distingue un produit ignoré d'un produit jamais montré, utile pour une évaluation hors ligne de type NDCG |
| `dim_produit` | `categorie`, `marque` | Features content-based (similarité de catégorie ou de marque) |
| `dim_client` | `segment_fidelite`, `region` | Personnalisation par segment, pour les visiteurs connus |

**Construction typique :**
- **Market basket analysis** : grouper `fact_ventes` par `order_id`, extraire les
  paires de `produit_key` co-achetés dans un même panier.
- **Collaborative filtering** : matrice client × produit à partir de `fact_ventes`
  (achats confirmés) ou de `fact_evenements_web` filtré sur `type_event = 'purchase'`.
- **Content-based** : similarité entre produits via `categorie`/`marque`, utile pour
  le démarrage à froid (produit sans historique).
- **Évaluation hors ligne** : `fact_exposition_reco` permet de comparer directement
  ce qui a été montré à ce qui a été effectivement vu, ajouté au panier ou acheté,
  sans reconstruire ce signal à partir du funnel seul.
- **Filtrage qualité** : exclure les sessions marquées comme bot avant tout
  entraînement.

---

## Rappels transverses

- Toutes les jointures se font sur les clés de substitution (`produit_key`,
  `client_key`, `date_key`, `promo_key`), jamais sur les identifiants métier
  (`product_id`, `customer_id`).
- Les tables de faits sont déjà nettoyées (doublons, valeurs hors plage et clés
  orphelines retirées lors du contrôle qualité).
- `dim_produit` et `dim_client` ont une structure SCD Type 2 (`valid_from`,
  `valid_to`, `is_current`) mais ne comportent qu'un seul snapshot à ce stade —
  `prix_base_xof` doit être traité comme le prix actuel, pas comme un historique.
