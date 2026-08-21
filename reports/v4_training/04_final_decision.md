# 04 — Décision finale V4

Statut : `synthetic_academic_experiment`. Données synthétiques, projet
académique. Aucune performance commerciale réelle n'est revendiquée ; ces
résultats servent à l'évaluation académique et au benchmark de pipeline.

Branche : `v4/pricing-recommendation-training`.
Aucun push, aucune fusion, aucun déploiement, aucune écriture Supabase.
Le forecasting V2 n'a pas été touché : `LightGBM_direct_per_horizon` reste le
modèle de planification 30 jours validé, inchangé.

---

## 1. Décision — pricing

**Aucun modèle n'est promu.** Sur les trois cibles évaluées séparément
(`units_sold_window_7j`, `revenue_window_xof_7j`, `margin_window_xof_7j`), la
baseline `baseline_mediane_produit` obtient la meilleure WAPE et reste la
référence.

| Cible | Meilleur candidat non-baseline | WAPE macro candidat | WAPE macro baseline retenue | Gain |
|---|---|---:|---:|---:|
| `units_sold_window_7j` | `T_learner` | 0,1628 | 0,1342 | **négatif** (−21,3 %) |
| `revenue_window_xof_7j` | `T_learner` | 0,1385 | 0,1299 | **négatif** (−6,6 %) |
| `margin_window_xof_7j` | `T_learner` | 0,1406 | 0,1305 | **négatif** (−7,7 %) |

Raison structurelle, pas un défaut de méthode : la remise, la classe ABC et le
statut cold-start sont des attributs fixes par produit sur toute la durée de
l'expérience (aucune variation intra-produit). La quasi-totalité du signal
prévisible tient donc à l'identité du produit, qu'une baseline par produit
capture directement. Détail complet : `reports/v4_training/01_pricing_results.md`.

Garde-fous vérifiés sur les 11 799 décisions : 0 marge négative, 0 remise sous
le coût, biais absolu de la baseline retenue ≤ 1 % sur les trois cibles.

## 2. Décision — recommandation

**Un modèle est promu sur chacune des trois cibles**, évaluées séparément
contre la baseline `popularite_globale_v1` :

| Cible | Modèle retenu | NDCG@10 | Gain relatif | Fenêtres gagnées (/4) | IC95 % bootstrap | p corrigée Holm |
|---|---|---:|---:|---:|---|---:|
| `viewed_after_impression` | `CatBoostRanker` | 0,01194 | +5,57 % | 4 | [0,00011 ; 0,00118] | 0,168 (non significatif) |
| `added_to_cart_after` | `pointwise_conversion` | 0,01438 | +7,70 % | 4 | [0,00045 ; 0,00163] | 0,018 (significatif) |
| `purchased_after` | `CatBoostRanker` | 0,01258 | +8,57 % | 4 | [0,00042 ; 0,00149] | 0,009 (significatif) |

Critères de promotion appliqués (tous requis) : gain relatif NDCG@10 ≥ 5 %,
perte de Recall@10 ≤ 2 %, intervalle de bootstrap à 95 % entièrement
positif, au moins 3 fenêtres gagnées sur 4, couverture catalogue et
diversité conservées (41–44 % pour les modèles retenus, contre 14–26 %
pour la pure popularité), stabilité contrôle/traitement vérifiée sur la
métrique servie (`as_served_metrics.csv`).

**Constat méthodologique transversal** : avec des slates fermées de 5
candidats, Recall@5/@10/@20 et HitRate@10 sont mathématiquement invariants
au reclassement (seuls NDCG@k et MRR/MAP@10 sont sensibles à l'ordre) —
vérifié par test dédié. Le critère de perte de Recall est donc satisfait
mécaniquement par tout modèle de reclassement dans ce protocole ; le NDCG@10
reste le seul discriminant réel.

**Réserve statistique honnête** : sur `viewed_after_impression`, le gain
franchit le seuil de promotion (bootstrap, fenêtres gagnées) mais sa
p-value corrigée Holm (0,168) ne passe pas le seuil conventionnel de 5 %
une fois corrigée pour la comparaison simultanée des 9 modèles candidats —
signal plus fragile que sur les deux autres cibles, où la significativité
corrigée est atteinte (0,018 et 0,009). Détail complet, y compris la liste
intégrale des candidats et leur éligibilité par cible :
`reports/v4_training/02_recommendation_results.md`.

## 3. Contrôles anti-fuite — synthèse

`reports/v4_training/06_leakage_checks.json` : 17 PASS, 2 WARNING, 1 FAIL.
Le seul échec (`product_impressions` constant par produit) est corrigé par
exclusion de la feature et reconstruction propre depuis les événements web
pré-décision — n'affecte pas le périmètre des modèles retenus.

Décision de sémantique : `product_exposure_probability` est un softmax
théorique sur des slates réellement sélectionnées de façon déterministe
(Top-5 par score). `exposure_probability_status = "deterministic_top_k"` est
ajouté au jeu de données ; cette probabilité n'est jamais utilisée comme poids
IPS.

## 4. Artefacts

```
models/v4/manifests/raw_data_manifest.json
models/v4/pricing/{units_sold_window_7j,revenue_window_xof_7j,margin_window_xof_7j}/
models/v4/recommendation/{viewed_after_impression,added_to_cart_after,purchased_after}/
reports/v4_training/{00..06}*.{md,json,csv}
```

## 5. Échecs et limites assumés

- Contrôle `P-12` (product_impressions) : échec documenté, corrigé par
  reconstruction, sans impact sur le périmètre retenu.
- Aucun modèle pricing promu : conclusion honnête, pas un échec de pipeline —
  la confusion structurelle remise/produit rend la cible largement non
  différentiable des attributs statiques du produit sur cette expérience
  synthétique.
- CatBoost en perte Poisson dégénérait sur les cibles monétaires (WAPE=1,0) ;
  corrigé (perte MAE pour les cibles en XOF).

## 6. Actions nécessitant une autorisation

- Tout `git push` ou fusion vers une branche partagée.
- Toute écriture Supabase (la base reste strictement en lecture seule).
- Tout déploiement.
