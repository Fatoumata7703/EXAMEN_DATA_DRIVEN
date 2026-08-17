# Optimisation avancée — forecasting

## Verdict

La décision validée reste inchangée pour le quotidien : **CrostonOptimized**. Le gain quotidien du challenger direct n'est que de 0,69 %, inférieur au seuil d'amélioration de 5 %, même si le bootstrap apparié indique un petit avantage statistique.

Pour la planification cumulée à 30 jours, **LightGBM direct par horizon** devient le candidat expérimental principal : WAPE30 = 0,2583 contre 0,3106 pour le LightGBM_Tweedie validé, soit 16,83 % de gain relatif, sur les six fenêtres. Cette conclusion ne crée aucun « vainqueur global » et ne remplace pas encore l'artefact validé.

## Protocole temporel

- Données : 300 produits × 546 jours, du 2025-02-01 au 2026-07-31.
- Six fenêtres externes non chevauchantes de 30 jours, démarrant le 2026-02-02, 2026-03-04, 2026-04-03, 2026-05-03, 2026-06-02 et 2026-07-02.
- Un modèle distinct produit directement chaque cible J+1 à J+30 depuis le même cutoff ; aucune récursion.
- Le tuning contrôlé utilise un pseudo-cutoff strictement antérieur à la fenêtre externe, seulement pour J+1/J+7/J+14/J+30. La fenêtre externe n'est jamais utilisée pour choisir les hyperparamètres.
- Le stock futur et les achats web contemporains sont exclus. La remise future n'est utilisable que sous l'hypothèse explicite d'un calendrier promotionnel planifié, connu et gelé au cutoff.
- Les challengers globaux utilisent des origines d'entraînement espacées de 14 jours et des hyperparamètres fixés avant les tests externes.

## LightGBM direct par horizon

| Fenêtre | Début test | WAPE jour | WAPE cumul 7 j | WAPE cumul 30 j | Biais |
|---:|---|---:|---:|---:|---:|
| 1 | 2026-02-02 | 1,0901 | 0,4382 | 0,2679 | +0,0167 |
| 2 | 2026-03-04 | 1,1151 | 0,4763 | 0,2888 | -0,0503 |
| 3 | 2026-04-03 | 1,0844 | 0,4690 | 0,2489 | -0,0580 |
| 4 | 2026-05-03 | 1,0611 | 0,4516 | 0,2587 | -0,0614 |
| 5 | 2026-06-02 | 1,0711 | 0,4335 | 0,2528 | -0,0484 |
| 6 | 2026-07-02 | 1,1000 | 0,4590 | 0,2327 | +0,0461 |
| **Moyenne** | — | **1,0870** | **0,4546** | **0,2583** | **-0,0259** |

Objectifs : WAPE30 < 0,27 atteint ; biais absolu moyen < 0,05 atteint ; WAPE7 < 0,42 non atteint ; gain quotidien ≥ 5 % non atteint.

Comparaisons appariées au grain produit-fenêtre, 3 000 tirages :

- WAPE jour vs CrostonOptimized : différence -0,00691, IC95 % [-0,01356 ; -0,00029], 1 800 unités. Gain crédible mais trop faible pour changer la décision quotidienne.
- WAPE30 vs LightGBM_Tweedie validé : différence -0,05267, IC95 % [-0,06048 ; -0,04488], 1 800 unités. Gain stable sur 6/6 fenêtres.

## Challengers globaux

| Modèle | WAPE jour | WAPE cumul 7 j | WAPE cumul 30 j | Biais | Statut |
|---|---:|---:|---:|---:|---|
| LightGBM direct par horizon | 1,0870 | 0,4546 | **0,2583** | -0,0259 | candidat cumul 30 j |
| Ensemble expanding | 1,0895 | 0,4568 | 0,2588 | -0,0162 | challenger |
| XGBoost Poisson | 1,0936 | 0,4571 | 0,2593 | -0,0039 | challenger |
| LightGBM global Tweedie | 1,0901 | 0,4574 | 0,2600 | -0,0128 | challenger |
| CatBoost Tweedie | 1,0916 | 0,4582 | 0,2618 | -0,0136 | challenger |
| Hurdle global | 1,0910 | 0,4591 | 0,2621 | -0,0149 | challenger |
| CatBoost Poisson | 1,0945 | 0,4610 | 0,2626 | -0,0072 | challenger |
| LightGBM quantile p50 | 0,9571 | 0,7227 | 0,6875 | -0,6829 | rejeté |

Le quantile p50 est rejeté : son WAPE journalier apparemment favorable masque une sous-prévision massive et des cumuls inutilisables. L'ensemble expanding sélectionne modèle et poids exclusivement sur les fenêtres antérieures, mais ne dépasse pas le modèle direct.

## Intervalles conformes strictement antérieurs

Calibration Mondrian par horizon × segment ABC × intermittence. La fenêtre 1 sert uniquement à amorcer les résidus ; les couvertures sont évaluées sur les fenêtres 2 à 6.

| Niveau | Segment | Couverture | Largeur moyenne | N |
|---:|---|---:|---:|---:|
| 80 % | global | 78,76 % | 2,587 | 45 000 |
| 80 % | ABC-A | 78,84 % | 3,015 | 23 910 |
| 80 % | intermittents | 79,66 % | 2,736 | 42 390 |
| 95 % | global | 95,32 % | 4,824 | 45 000 |
| 95 % | ABC-A | 95,16 % | 5,255 | 23 910 |
| 95 % | intermittents | 95,33 % | 4,966 | 42 390 |

Les intervalles natifs p10–p90 de LightGBM quantile surcouvrent environ 89–91 % et accompagnent une médiane très biaisée ; ils ne sont pas retenus.

## Importance et ablations

L'importance par gain à J+30 place `stock_at_cutoff` en tête (42,32 %), puis l'identité produit (4,24 %), le nombre cumulé de jours actifs (4,03 %), la moyenne des ventes sur 56 jours (3,75 %) et l'ADI (3,71 %). Ces importances sont prédictives, corrélées et non causales.

Les ablations emploient exactement le LightGBM global, les mêmes fenêtres et origines, sans retuning :

| Variante | Variables retirées | WAPE30 | Écart vs complet |
|---|---|---:|---:|
| complet | aucune | 0,26005 | — |
| sans web | vues, paniers, tendances/conversion | 0,25913 | -0,00091 |
| sans stock | stock cutoff, dernier/frequence réappro. | 0,26063 | +0,00058 |
| sans promotion | remise planifiée | 0,26212 | +0,00207 |

L'apport marginal du stock et de la promotion est faible mais positif dans ce test global. Le léger mieux sans web montre que le signal web n'est pas robuste dans cette spécification. Une ablation « commandes » n'est pas applicable : aucune variable commande/achat web n'entre dans les features autorisées du forecasting.

## Qualité, ressources et limites

- 54 000 prédictions directes : 0 NaN/infini, 0 valeur négative.
- Tests actifs : cible J+h exacte, perturbation du futur, déterminisme de la construction de cible, absence d'achat web et de stock futur, distinction métrique journalière/cumulative et intégrité des groupes d'ablation.
- Entraînements strictement séquentiels, deux threads par modèle, checkpoints par fenêtre/horizon. Aucun échec ni fallback ; consommation observée autour de 0,55 Go de RSS et durées très inférieures aux budgets configurés.
- Les 300 produits disposent d'historique dans toutes les fenêtres. Le vrai cold-start et l'historique insuffisant ne sont donc pas mesurés empiriquement : usage interdit pour un produit nouveau sans politique de repli dédiée.
- `valid_from` décrit l'âge de version de la dimension, pas nécessairement l'âge commercial ; la feature est nommée et interprétée en conséquence.
- Les gains ne justifient ni causalité stock/promotion, ni prévision au-delà de 30 jours, ni substitution automatique aux décisions validées.

## Décisions autorisées

- Quotidien : conserver CrostonOptimized.
- Cumul 30 jours : LightGBM direct par horizon est **candidat expérimental principal**, à promouvoir seulement après revue et décision explicite.
- Aucun modèle n'est présenté comme vainqueur global.
