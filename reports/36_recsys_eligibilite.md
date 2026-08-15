# 36 — Recommandation V1 : rapport d'éligibilité (avant tout entraînement lourd)

_Généré le 2026-08-14T20:31:33.071649+00:00. Forecasting V1 et Pricing V1 sont figés — aucune donnée ni pipeline de ces phases n'a été modifié pour produire ce rapport._

## 0. Colonnes vérifiées (lecture seule, sur les 7 tables demandées)

| Table | Colonnes réelles |
|---|---|
| `fact_ventes` | `vente_id, produit_key, client_key, date_key, promo_key, quantite, montant_net_xof` |
| `fact_evenements_web` | `event_id, produit_key, client_key, date_key, type_event, appareil` |
| `dim_client` | `client_key, customer_id, region, age_bracket, segment_fidelite, valid_from, valid_to, is_current` |
| `dim_produit` | `produit_key, product_id, product_name, categorie, marque, prix_base_xof, cout_xof, valid_from, valid_to, is_current` |
| `dim_date` | `date_key, date_complete, annee, mois, jour, jour_semaine, est_weekend` |
| `dim_promotion` | `promo_key, promotion_id, portee, cible, remise_pct, date_debut, date_fin` |
| `fact_stock` | `produit_key, date_key, niveau_stock` |

**Points impératifs vérifiés empiriquement (pas supposés) :**

- `vente_id` : 85,419 valeurs distinctes pour 85,419 lignes — confirmé : une ligne de vente, jamais un identifiant de commande. Aucune reconstruction de panier multi-produits n'est faite.
- `order_id` absent de `fact_ventes` : **True**. `session_id` métier absent de `fact_evenements_web` : **True**. `event_timestamp` absent : **True**. → aucune règle « achetés ensemble », aucune recommandation séquentielle présentée comme fiable.
- `client_key` dans `fact_evenements_web` : rempli à **100.0 %** (vérifié, pas supposé) — les événements web SONT attribuables aux clients sans fabrication d'identité.
- `produit_key` dans `fact_evenements_web` : rempli à **100.0 %**.

## 1. Qualité exacte des jointures ventes/web

| Contrôle | Résultat |
|---|---:|
| ventes.produit_key -> dim_produit | 0 |
| ventes.client_key -> dim_client | 0 |
| web.produit_key -> dim_produit | 0 |
| web.client_key -> dim_client | 0 |
| vente_id dupliques | 0 |
| event_id dupliques | 0 |
| ventes.client_key null (%) | 0.0 |
| web.client_key null (%) | 0.0 |
| web.produit_key null (%) | 0.0 |

**Intégrité référentielle parfaite** : 0 orphelin sur toutes les jointures testées, 0 doublon de clé de ligne.

## 2. Clients et produits exploitables

- Clients dans `dim_client` : **5,000**
- Clients avec au moins un achat historique : **5,000** (100.0%)
- Produits dans `dim_produit` : **300**
- Produits avec au moins une vente historique : **300** (100.0%)

## 3. Sparsité de la matrice client-produit

- Dimensions : 5,000 clients × 300 produits = 1,500,000 cellules
- Paires (client, produit) distinctes achetées au moins une fois : **82,147**
- Sparsité : **94.5235%** (dense pour un contexte recommandation — la médiane de 16 produits distincts achetés par client sur 300 au catalogue est un signal favorable au filtrage collaboratif).

## 4. Distribution du nombre d'achats (lignes) par client

|       |   n_lignes_vente |
|:------|-----------------:|
| count |           5000.0 |
| mean  |             17.1 |
| std   |              4.2 |
| min   |              4.0 |
| 10%   |             12.0 |
| 25%   |             14.0 |
| 50%   |             17.0 |
| 75%   |             20.0 |
| 90%   |             23.0 |
| 95%   |             24.0 |
| 99%   |             28.0 |
| max   |             34.0 |

## 5. Proportion de clients évaluables, par fenêtre de validation temporelle

|   fenetre | label             | train_end   | test_start   | test_end   |   n_lignes_train |   n_lignes_test |   n_clients_cold_start_pur |   n_clients_evaluables_test |   pct_clients_evaluables |
|----------:|:------------------|:------------|:-------------|:-----------|-----------------:|----------------:|---------------------------:|----------------------------:|-------------------------:|
|         0 | cold_start_dediee | 2025-05-01  | 2025-05-02   | 2025-06-30 |             8296 |            7034 |                        971 |                        3781 |                   0.7562 |
|         1 | principale_1      | 2026-02-01  | 2026-02-02   | 2026-04-02 |            50883 |           10555 |                          0 |                        4396 |                   0.8792 |
|         2 | principale_2      | 2026-04-02  | 2026-04-03   | 2026-06-01 |            61438 |           11997 |                          0 |                        4531 |                   0.9062 |
|         3 | principale_3      | 2026-06-01  | 2026-06-02   | 2026-07-31 |            73435 |           11984 |                          0 |                        4538 |                   0.9076 |

**Constat important** : aux 3 fenêtres principales (coupures tardives, alignées sur les fenêtres du pricing pour comparabilité), **0 client n'a un historique train vide** — tous les clients de `dim_client` ont déjà acheté au moins une fois avant ces dates. Le cold-start réel (aucun achat antérieur) n'existe donc qu'en tout début de période. La fenêtre 0 (coupure au 2025-05-01) est ajoutée spécifiquement pour évaluer ce segment : 971 clients y sont en cold-start pur, dont 717 achètent effectivement dans les 60 jours suivants (évaluables).

## 6. Faisabilité de la personnalisation

**✅ Faisable, avec réserves documentées.** La densité de la matrice client-produit (94.52% de sparsité, très favorable pour ce volume), l'intégrité référentielle parfaite, et la présence confirmée de `client_key`/`produit_key` dans les événements web permettent un filtrage collaboratif implicite et un contenu-based crédibles. **Réserves** : pas de granularité panier (`vente_id` = ligne, pas commande) donc pas de règles d'association produit-produit fiables ; pas de séquence temporelle intra-session (`event_timestamp`/`session_id` absents) donc pas de recommandation séquentielle ; le cold-start réel n'est mesurable que sur une fenêtre dédiée en tout début de période.

## 7. Limites dues aux colonnes manquantes

- **`order_id`** : impossible de savoir quelles lignes de vente appartiennent à la même commande → aucune règle « achetés ensemble » (market basket) construite.
- **`session_id` métier / `event_timestamp`** : impossible d'ordonner les événements web dans le temps à l'intérieur d'une journée → aucune recommandation séquentielle (next-item) construite, seulement des signaux agrégés (ex. compteurs par période).
- **`web_purchase` contemporain** : un événement `type_event='purchase'` le même jour qu'une vente peut en être le reflet direct → jamais utilisé comme feature pour prédire cette même vente (seules les données strictement antérieures au cutoff alimentent l'entraînement).
- **Stock** : `fact_stock` ne fournit qu'un niveau par produit×jour (pas par client) → utilisé uniquement pour un filtre de disponibilité `stock(J-1) > 0` au moment de la recommandation, jamais comme signal contemporain.
