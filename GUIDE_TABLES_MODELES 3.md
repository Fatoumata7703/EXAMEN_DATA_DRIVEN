# Guide tables → modèles

**Pour :** Data Scientist
**Source :** Supabase — schéma en étoile (6 tables), voir `HANDOFF_DATA_SCIENTIST.md` pour le détail complet des colonnes.

Ce document répond à une seule question : **quelles tables utiliser pour quel modèle.**

---

## 1. Forecasting de la demande

| Table | Colonnes utiles | Rôle |
|---|---|---|
| `fact_ventes` | `quantite`, `date_key`, `produit_key`, `montant_net_xof` | Variable cible (quantité vendue par produit et par jour) |
| `dim_date` | `date_complete`, `mois`, `jour_semaine`, `est_weekend` | Features calendaires (saisonnalité, effet weekend) |
| `dim_produit` | `categorie`, `marque`, `prix_base_xof` | Features produit (chaque catégorie a sa propre saisonnalité) |
| `dim_promotion` | `remise_pct`, `date_debut`, `date_fin` | Signal exogène : une promo active fait mécaniquement monter la demande |
| `fact_stock` | `niveau_stock`, `produit_key`, `date_key` | Contrainte de stock — indispensable pour distinguer une vraie absence de demande d'une rupture de stock |

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

⚠️ **Rappel** : `promo_key` est nullable dans `fact_ventes` — une vente sans promo a `promo_key = null`, ce n'est pas une donnée manquante à traiter, c'est le cas normal.

---

## 3. Recommandation produit

| Table | Colonnes utiles | Rôle |
|---|---|---|
| `fact_evenements_web` | `client_key`, `produit_key`, `type_event`, `date_key` | Funnel de navigation (view/add_to_cart/purchase) — base du collaborative filtering et des signaux d'intérêt implicite |
| `fact_ventes` | `client_key`, `produit_key` | Historique d'achats confirmés — matrice client × produit pour le collaborative filtering |
| `dim_produit` | `categorie`, `marque` | Features content-based (recommander par similarité de catégorie/marque) |
| `dim_client` | `segment_fidelite`, `region` | Personnalisation par segment |

**Construction typique :**
- **Collaborative filtering** : matrice client × produit à partir de `fact_ventes` (achats) ou `fact_evenements_web` filtré sur `type_event = 'purchase'` (signal plus dense).
- **Content-based** : similarité entre produits via `categorie`/`marque` dans `dim_produit`, utile pour le cold-start (nouveau produit sans historique).
- **Hybride recommandé** : combiner les deux, d'autant que le funnel complet (`view` → `add_to_cart` → `purchase`) dans `fact_evenements_web` permet de pondérer les signaux (une vue pèse moins qu'un achat).

---

## Rappels transverses (valables pour les 3 modèles)

- Toutes les jointures se font sur les clés de substitution (`produit_key`, `client_key`, `date_key`, `promo_key`) — jamais sur `product_id`/`customer_id` directement (voir `HANDOFF_DATA_SCIENTIST.md`).
- Les données sont déjà nettoyées (doublons, quantités négatives, FK orphelines retirées) — pas besoin de re-filtrer.
- `dim_produit`/`dim_client` ont une structure SCD Type 2 (`valid_from`/`valid_to`/`is_current`) mais un seul snapshot existe pour l'instant — traite `prix_base_xof` comme le prix actuel, pas un historique.
