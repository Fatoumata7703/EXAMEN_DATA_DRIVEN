# Guide tables → modèles

**Pour :** Data Scientist
**Source :** Supabase — schéma en étoile (7 tables), voir `DATA_DICTIONARY.md` pour le détail complet des colonnes.

Ce document répond à une seule question : **quelles tables utiliser pour quel modèle.**

**Mise à jour** : `fact_ventes` porte maintenant `order_id` (paniers multi-produits) et
`statut_commande` ; `fact_evenements_web` porte `session_id`, `event_timestamp` complet,
`anonymous_id`, `order_id`, `quantity`, `canal`, `source_trafic`, `est_bot` — voir la
section reco ci-dessous, ce sont ces champs qui en changent le plus la portée.

---

## 1. Forecasting de la demande

| Table | Colonnes utiles | Rôle |
|---|---|---|
| `fact_ventes` | `quantite`, `date_key`, `produit_key`, `montant_net_xof` | Variable cible (quantité vendue par produit et par jour) |
| `dim_date` | `date_complete`, `mois`, `jour_semaine`, `est_weekend` | Features calendaires (saisonnalité, effet weekend) |
| `dim_produit` | `categorie`, `marque`, `prix_base_xof` | Features produit (chaque catégorie a sa propre saisonnalité) |
| `dim_promotion` | `remise_pct`, `date_debut`, `date_fin` | Signal exogène : une promo active fait mécaniquement monter la demande |
| `fact_stock` | `niveau_stock`, `quantite_vendue`, `quantite_reapprovisionnee`, `produit_key`, `date_key` | Contrainte de stock — indispensable pour distinguer une vraie absence de demande d'une rupture de stock. Réconciliation exacte possible avec les 2 nouvelles colonnes (v3). |

**Construction typique :** agréger `fact_ventes` par `produit_key` × `date_key` (somme de `quantite`) pour obtenir une série temporelle par produit, puis joindre `dim_date`, `dim_produit` et `fact_stock` (sur `produit_key`+`date_key`) pour les features et pour identifier les jours de rupture (`niveau_stock` bas ou nul).

---

## 2. Pricing dynamique

| Table | Colonnes utiles | Rôle |
|---|---|---|
| `fact_ventes` | `quantite`, `montant_net_xof`, `produit_key`, `date_key` | Calculer le prix effectif payé (`montant_net_xof / quantite`) et son effet sur la quantité |
| `dim_produit` | `prix_base_xof`, `cout_xof`, `categorie` | Prix catalogue, coût (pour la marge), élasticité par catégorie |
| `dim_promotion` | `remise_pct` | Variation de prix contrôlée — base idéale pour estimer l'élasticité prix/demande |
| `dim_date` | `mois`, `est_weekend` | Contrôler l'effet saisonnier pour isoler le véritable effet prix |

**Construction typique :** pour chaque produit, régresser `quantite` sur le prix effectif (avec `remise_pct` comme instrument naturel de variation de prix), en contrôlant par mois/catégorie. `cout_xof` te sert à transformer une élasticité en recommandation de prix optimal sous contrainte de marge minimale.

⚠️ **Rappel** : `promo_key` est nullable dans `fact_ventes` — une vente sans promo a `promo_key = null`, ce n'est pas une donnée manquante à traiter, c'est le cas normal. Filtre sur `statut_commande = 'confirmee'` pour exclure les commandes annulées/retournées de l'analyse de demande réelle.

---

## 3. Recommandation produit

| Table | Colonnes utiles | Rôle |
|---|---|---|
| `fact_evenements_web` | `session_id`, `client_key`/`anonymous_id`, `produit_key`, `type_event`, `event_timestamp` | Funnel de navigation complet (view/add_to_cart/purchase) — base du collaborative filtering et des signaux d'intérêt implicite |
| `fact_ventes` | `order_id`, `client_key`, `produit_key` | **Paniers réels** : plusieurs lignes partagent le même `order_id` — c'est le signal direct pour du market basket analysis ("les clients qui achètent X achètent aussi Y dans le même panier") |
| `dim_produit` | `categorie`, `marque` | Features content-based (recommander par similarité de catégorie/marque) |
| `dim_client` | `segment_fidelite`, `region` | Personnalisation par segment (uniquement pour les visiteurs connus) |

**Construction typique :**
- **Market basket analysis (nouveau)** : grouper `fact_ventes` par `order_id`, extraire les paires/combos de `produit_key` co-achetés dans le même panier (règles d'association, type Apriori/FP-Growth) — c'est le signal le plus direct pour du cross-sell.
- **Collaborative filtering** : matrice client × produit à partir de `fact_ventes` (achats confirmés) ou `fact_evenements_web` filtré sur `type_event = 'purchase'` (signal plus dense).
- **Content-based** : similarité entre produits via `categorie`/`marque` dans `dim_produit`, utile pour le cold-start (nouveau produit sans historique).
- **Funnel de conversion** : `fact_evenements_web` groupé par `session_id`, trié par `event_timestamp`, permet de reconstituer le parcours `view → add_to_cart → purchase` complet par session et par produit.
- **Visiteurs anonymes** : `anonymous_id` (rempli uniquement quand `client_key` est vide) permet d'inclure le comportement de navigation des visiteurs non connectés dans les modèles de contenu, même sans historique d'achat rattachable à un client identifié.
- **Filtrage qualité** : exclure `est_bot = true` avant tout entraînement — sinon les sessions bot (rafales de vues sans intention réelle) polluent le signal.
- **Hybride recommandé** : combiner panier + funnel + content-based, d'autant que le funnel complet permet de pondérer les signaux (une vue pèse moins qu'un ajout panier, qui pèse moins qu'un achat).

---

## Rappels transverses (valables pour les 3 modèles)

- Toutes les jointures se font sur les clés de substitution (`produit_key`, `client_key`, `date_key`, `promo_key`) — jamais sur `product_id`/`customer_id` directement (voir `HANDOFF_DATA_SCIENTIST.md`).
- Les données sont déjà nettoyées (doublons, quantités négatives, FK orphelines retirées) — pas besoin de re-filtrer.
- `dim_produit`/`dim_client` ont une structure SCD Type 2 (`valid_from`/`valid_to`/`is_current`) mais un seul snapshot existe pour l'instant — traite `prix_base_xof` comme le prix actuel, pas un historique.
