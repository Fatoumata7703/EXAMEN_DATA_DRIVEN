# 18 — Rapport final du backtest (opérationnel, causes de repli séparées)

_Généré le 2026-08-14T11:33:58.338912+00:00. Construit exclusivement depuis `reports/backtest/operational_predictions/` — les 42 checkpoints bruts n'ont jamais été modifiés._

## 1. Évaluation principale — périmètre comparable (produits présents dans le train)

_Sert au classement des modèles et à la sélection du seuil pour LightGBM. Inclut les replis historique/exception/budget (documentés), exclut le cold-start._

**Biais — définitions exactes** (unité : unités de la cible, i.e. quantité) :

- `biais` (signé) = `mean(y_pred − y)` sur les observations poolées — positif = sur-prévision en moyenne, négatif = sous-prévision. C'est un **biais moyen par ligne**, pas un total.
- `biais_normalise` = `SUM(y_pred − y) / SUM(y)` — sans unité, **directement comparable à la WAPE** (même dénominateur). Un `biais_normalise` de +0,05 signifie une sur-prévision cumulée de 5 % du volume réel total.

| modele           |   WAPE |     MAE |    RMSE |   RMSSE |    MASE |   sMAPE |   biais |   biais_normalise |   taux_sous_prevision |   cout_asymetrique_1_5x |   cout_asymetrique_2x |   WAPE_ecart_type |   couverture_native |   taux_fallback |   temps_total_s |   temps_moyen_par_fenetre_s | note                                  |
|:-----------------|-------:|--------:|--------:|--------:|--------:|--------:|--------:|------------------:|----------------------:|------------------------:|----------------------:|------------------:|--------------------:|----------------:|----------------:|----------------------------:|:--------------------------------------|
| AutoETS          | 0.2772 | 10.3250 | 14.1431 |  5.3409 |  5.8924 |  0.2883 |  2.5087 |            0.0673 |                0.4037 |                 12.2791 |               14.2332 |            0.0308 |              0.9922 |          0.0385 |        225.6200 |                     37.6033 |                                       |
| CrostonOptimized | 0.3139 | 11.6934 | 15.7525 |  5.7695 |  6.6618 |  0.3135 |  2.2001 |            0.0591 |                0.4471 |                 14.0667 |               16.4400 |            0.0128 |              1.0000 |          0.0309 |         15.3000 |                      2.5500 |                                       |
| WindowAverage28  | 0.3161 | 11.7759 | 15.3815 |  5.7695 |  6.7913 |  0.3344 |  0.2084 |            0.0056 |                0.4868 |                 14.6677 |               17.5596 |            0.0090 |              0.9669 |          0.0630 |         16.5800 |                      2.7633 |                                       |
| TSB              | 0.4025 | 14.9920 | 19.9197 |  7.4863 |  8.7293 |  0.4282 |  0.6537 |            0.0175 |                0.5181 |                 18.5766 |               22.1612 |            0.0144 |              1.0000 |          0.0309 |         15.4700 |                      2.5783 |                                       |
| AutoARIMA        | 0.4326 | 16.1134 | 27.3295 | 10.4921 |  9.3361 |  0.4799 |  3.3117 |            0.0889 |                0.4230 |                 19.3138 |               22.5142 |            0.3471 |              0.8375 |          0.1883 |      32484.0900 |                   5414.0150 | ⚠️ voir §7 (fenêtre 4 non comparable) |
| SeasonalNaive7   | 0.4909 | 18.2846 | 23.7775 |  8.9907 | 10.6679 |  0.5452 |  0.4795 |            0.0129 |                0.5265 |                 22.7359 |               27.1871 |            0.0315 |              0.9922 |          0.0382 |         16.3900 |                      2.7317 |                                       |
| Naive            | 1.1198 | 41.7136 | 56.2914 | 21.8565 | 24.7014 |  1.3886 |  1.1793 |            0.0317 |                0.6456 |                 51.8472 |               61.9807 |            0.0436 |              1.0000 |          0.0309 |         17.0500 |                      2.8417 |                                       |

## 1bis. Règle de décision multi-critères pour LightGBM

Le seuil n'est **pas** réduit à `WAPE < 0,2772`. LightGBM n'est considéré supérieur à AutoETS que s'il remplit **simultanément** :

1. WAPE ≤ 0.2772 (bat AutoETS) **ou** WAPE ≤ 0.2910 (dans les 5 % — « s'en approche clairement ») ;
2. écart-type de la WAPE entre fenêtres ≤ 0.0308 (médiane des baselines — ne dégrade pas la stabilité) ;
3. WAPE sur produits classe A ne dépasse pas 0.3081 (au plus +10 % vs la meilleure baseline sur ce segment) ;
4. `|biais_normalise|` reste sous 0,10 (pas de sur/sous-prévision structurelle excessive) ;
5. le gain de WAPE vs WindowAverage28 (le benchmark de simplicité) justifie la complexité additionnelle — jugé qualitativement, pas seulement numériquement.

**WindowAverage28 reste le benchmark opérationnel de référence** (simplicité, stabilité, meilleur sur produits A et séries intermittentes) : LightGBM doit se comparer aux deux — AutoETS (meilleure WAPE globale) et WindowAverage28 (meilleure robustesse) — pas au seul chiffre WAPE.

## 2. Évaluation opérationnelle complète (toutes les lignes, cold-start inclus)

_Toutes les observations attendues, avec repli documenté (`y_pred_final`). Mesure ce que le pipeline déployé produirait réellement._

| modele           |   WAPE |     MAE |    RMSE |   RMSSE |    MASE |   biais |   biais_normalise |
|:-----------------|-------:|--------:|--------:|--------:|--------:|--------:|------------------:|
| AutoETS          | 0.2881 | 10.5616 | 14.5082 |  5.3409 |  5.8924 |  1.8755 |            0.0512 |
| CrostonOptimized | 0.3243 | 11.8877 | 16.0348 |  5.7695 |  6.6618 |  1.5765 |            0.0430 |
| WindowAverage28  | 0.3265 | 11.9676 | 15.6819 |  5.7695 |  6.7913 | -0.3537 |           -0.0096 |
| TSB              | 0.4115 | 15.0844 | 20.0293 |  7.4863 |  8.7293 |  0.0778 |            0.0021 |
| AutoARIMA        | 0.4412 | 16.1711 | 27.2114 | 10.4921 |  9.3361 |  2.6537 |            0.0724 |
| SeasonalNaive7   | 0.4986 | 18.2752 | 23.7600 |  8.9907 | 10.6679 | -0.0910 |           -0.0025 |
| Naive            | 1.1180 | 40.9802 | 55.5648 | 21.8565 | 24.7014 |  0.5872 |            0.0160 |

## 3. Évaluation cold-start (produits absents du train — repli identique pour tous les modèles)

_Non comparée entre modèles : le repli `ColdStartZero` est strictement identique quel que soit le modèle demandé._

- Produits concernés : 53
- Lignes : 875
- Quantité réelle totale non prévue : 953
- Part de zéros réels : 57.49%
- MAE du repli zéro : 1.0891
- WAPE du repli zéro : 1.0000
- Biais : -1.0891 (négatif = sous-prévision structurelle, attendu puisque la prévision est toujours 0)

## 4. Métriques natives et couverture (fiabilité par modèle)

_Calculées uniquement sur les prédictions réellement produites par le modèle demandé — **non comparables entre modèles** sans passer par le support commun (§5)._

| modele           |   couverture_native |   n_produits_natifs |   n_produits_eligibles |   WAPE_natif |   MAE_natif |
|:-----------------|--------------------:|--------------------:|-----------------------:|-------------:|------------:|
| AutoETS          |              0.9922 |                1649 |                   1662 |       0.2722 |     10.1292 |
| AutoARIMA        |              0.8375 |                1392 |                   1662 |       0.2839 |     10.5249 |
| WindowAverage28  |              0.9669 |                1607 |                   1662 |       0.3120 |     11.6357 |
| CrostonOptimized |              1.0000 |                1662 |                   1662 |       0.3139 |     11.6934 |
| TSB              |              1.0000 |                1662 |                   1662 |       0.4025 |     14.9920 |
| SeasonalNaive7   |              0.9922 |                1662 |                   1675 |       0.4896 |     18.1546 |
| Naive            |              1.0000 |                1662 |                   1662 |       1.1198 |     41.7136 |

## 5. Comparaison sur support commun (par fenêtre)

|   window | modele           |   n_produits_support_commun |   WAPE |     MAE |
|---------:|:-----------------|----------------------------:|-------:|--------:|
|        1 | Naive            |                         239 | 1.1150 | 41.5314 |
|        1 | SeasonalNaive7   |                         239 | 0.5302 | 19.7490 |
|        1 | WindowAverage28  |                         239 | 0.3097 | 11.5350 |
|        1 | AutoETS          |                         239 | 0.3065 | 11.4161 |
|        1 | AutoARIMA        |                         239 | 0.3215 | 11.9747 |
|        1 | CrostonOptimized |                         239 | 0.3174 | 11.8237 |
|        1 | TSB              |                         239 | 0.4121 | 15.3502 |
|        2 | Naive            |                         249 | 1.1244 | 40.8072 |
|        2 | SeasonalNaive7   |                         249 | 0.4943 | 17.9398 |
|        2 | WindowAverage28  |                         249 | 0.3109 | 11.2843 |
|        2 | AutoETS          |                         249 | 0.2876 | 10.4373 |
|        2 | AutoARIMA        |                         249 | 0.2931 | 10.6383 |
|        2 | CrostonOptimized |                         249 | 0.3090 | 11.2164 |
|        2 | TSB              |                         249 | 0.4068 | 14.7631 |
|        3 | Naive            |                         266 | 1.0790 | 42.3195 |
|        3 | SeasonalNaive7   |                         266 | 0.4854 | 19.0376 |
|        3 | WindowAverage28  |                         266 | 0.2983 | 11.7003 |
|        3 | AutoETS          |                         266 | 0.2542 |  9.9696 |
|        3 | AutoARIMA        |                         266 | 0.2568 | 10.0728 |
|        3 | CrostonOptimized |                         266 | 0.2894 | 11.3500 |
|        3 | TSB              |                         266 | 0.3833 | 15.0318 |
|        4 | Naive            |                         276 | 1.1953 | 45.3261 |
|        4 | SeasonalNaive7   |                         276 | 0.5004 | 18.9746 |
|        4 | WindowAverage28  |                         276 | 0.3183 | 12.0714 |
|        4 | AutoETS          |                         276 | 0.2504 |  9.4964 |
|        4 | CrostonOptimized |                         276 | 0.3013 | 11.4249 |
|        4 | TSB              |                         276 | 0.4004 | 15.1818 |
|        5 | Naive            |                         285 | 1.1337 | 41.8351 |
|        5 | SeasonalNaive7   |                         285 | 0.4474 | 16.5088 |
|        5 | WindowAverage28  |                         285 | 0.3167 | 11.6852 |
|        5 | AutoETS          |                         285 | 0.2568 |  9.4765 |
|        5 | AutoARIMA        |                         285 | 0.2492 |  9.1973 |
|        5 | CrostonOptimized |                         285 | 0.3164 | 11.6746 |
|        5 | TSB              |                         285 | 0.3839 | 14.1662 |
|        6 | Naive            |                         292 | 1.0639 | 38.5274 |
|        6 | SeasonalNaive7   |                         292 | 0.4779 | 17.3048 |
|        6 | WindowAverage28  |                         292 | 0.3175 | 11.4988 |
|        6 | AutoETS          |                         292 | 0.2639 |  9.5574 |
|        6 | AutoARIMA        |                         292 | 0.2664 |  9.6479 |
|        6 | CrostonOptimized |                         292 | 0.3131 | 11.3393 |
|        6 | TSB              |                         292 | 0.4057 | 14.6897 |

Modèles exclus du support commun (couverture native < 90 % sur la fenêtre concernée) :

- fenêtre 4 : ['AutoARIMA'] — couverture {'AutoARIMA': np.float64(0.0459)}

## 6. Taux de statut par modèle (doit sommer à 100 %)

| modele           |   n_produits_fenetres |   %_success_valid_prediction |   %_success_invalid_prediction_fallback |   %_exception_fallback |   %_budget_fallback |   %_cold_start_fallback |   somme_% |
|:-----------------|----------------------:|-----------------------------:|----------------------------------------:|-----------------------:|--------------------:|------------------------:|----------:|
| CrostonOptimized |                  1715 |                        96.91 |                                    0.00 |                   0.00 |                0.00 |                    3.09 |    100.00 |
| TSB              |                  1715 |                        96.91 |                                    0.00 |                   0.00 |                0.00 |                    3.09 |    100.00 |
| Naive            |                  1715 |                        96.91 |                                    0.00 |                   0.00 |                0.00 |                    3.09 |    100.00 |
| SeasonalNaive7   |                  1728 |                        96.18 |                                    0.75 |                   0.00 |                0.00 |                    3.07 |    100.00 |
| AutoETS          |                  1715 |                        96.15 |                                    0.00 |                   0.76 |                0.00 |                    3.09 |    100.00 |
| WindowAverage28  |                  1715 |                        93.70 |                                    3.21 |                   0.00 |                0.00 |                    3.09 |    100.00 |
| AutoARIMA        |                  1715 |                        81.17 |                                    0.00 |                   0.00 |               15.74 |                    3.09 |    100.00 |

## 7. Cas AutoARIMA — fenêtre 4

**AutoARIMA, fenêtre 4 — NON COMPARABLE / COUVERTURE INSUFFISANTE**

| Catégorie | Produits |
|---|---:|
| Présents dans le test | 292 |
| — dont présents dans le train (éligibles à AutoARIMA) | 283 |
| — dont cold-start (absents du train) | 9 |
| Sur les 283 éligibles : vrais ajustements AutoARIMA | 13 |
| Sur les 283 éligibles : replis budget | 270 |
| Sur les 283 éligibles : replis exception | 0 |
| Sur les 283 éligibles : autres replis (historique insuffisant) | 0 |
| **Somme (cold-start + succès + budget + exception + autre)** | **292** (= test : True) |

**Origine de l'incohérence 283 vs 292 signalée** : 283 = produits éligibles (présents dans le train, seuls ceux-là sont *tentés* par le modèle) — c'est le dénominateur correct, utilisé ci-dessus et dans tout le reste du rapport. 292 = 283 éligibles + 9 produits cold-start apparus après le cutoff, qui n'entrent jamais dans la boucle d'ajustement et ne sont donc ni un succès ni un échec du modèle. Une version antérieure de ce rapport utilisait par erreur 292 comme dénominateur de couverture (13/292 = 4,5 %) ; le calcul correct, corrigé ici, est **13/283 = 4.59%**.

- Performance **opérationnelle** du pipeline `AutoARIMA + repli` (toutes les 292 lignes, cold-start inclus) : WAPE = 1.1316.
- Aucune métrique « AutoARIMA pur » n'est calculée sur les 13 séries seules : cet échantillon est sélectionné par l'ordre d'exécution de la boucle, pas par tirage représentatif — le comparer aux autres modèles serait trompeur.
- Coût : 29 237,6 s (8 h 07) pour cette seule fenêtre, pour 4.6% de couverture réelle — à intégrer explicitement dans la recommandation finale (coût/bénéfice défavorable).

## 8. WindowAverage28 / SeasonalNaive7 — historique insuffisant par fenêtre

|   fenetre | modele          |   seuil_historique_jours |   produits_sous_le_seuil |   lignes_repli_historique_insuffisant | modele_repli_utilise    |
|----------:|:----------------|-------------------------:|-------------------------:|--------------------------------------:|:------------------------|
|         1 | SeasonalNaive7  |                        7 |                       20 |                                    48 | Naive                   |
|         1 | WindowAverage28 |                       28 |                       26 |                                   240 | AvailableHistoryAverage |
|         2 | SeasonalNaive7  |                        7 |                       11 |                                    22 | Naive                   |
|         2 | WindowAverage28 |                       28 |                       26 |                                   480 | AvailableHistoryAverage |
|         3 | SeasonalNaive7  |                        7 |                       11 |                                    29 | Naive                   |
|         3 | WindowAverage28 |                       28 |                       17 |                                   270 | AvailableHistoryAverage |
|         4 | SeasonalNaive7  |                        7 |                       12 |                                    58 | Naive                   |
|         4 | WindowAverage28 |                       28 |                       16 |                                   210 | AvailableHistoryAverage |
|         5 | SeasonalNaive7  |                        7 |                       10 |                                    24 | Naive                   |
|         5 | WindowAverage28 |                       28 |                       15 |                                   210 | AvailableHistoryAverage |
|         6 | SeasonalNaive7  |                        7 |                        2 |                                    20 | Naive                   |
|         6 | WindowAverage28 |                       28 |                        8 |                                   240 | AvailableHistoryAverage |

> Un modèle nécessitant un repli fréquent (WindowAverage28, SeasonalNaive7 en début d'historique) doit être lu avec cette réserve, même si sa métrique opérationnelle finale paraît bonne — la couverture native (§4) qualifie ce qu'il a réellement appris.

## 9. Stabilité entre fenêtres (périmètre principal)

_Écart-type de la WAPE entre les 6 fenêtres — un modèle instable peut avoir une bonne moyenne mais une fiabilité opérationnelle douteuse._

| modele           |   WAPE_moyenne |   WAPE_ecart_type |   coefficient_variation |
|:-----------------|---------------:|------------------:|------------------------:|
| WindowAverage28  |         0.3162 |            0.0090 |                  0.0283 |
| CrostonOptimized |         0.3143 |            0.0128 |                  0.0406 |
| TSB              |         0.4029 |            0.0144 |                  0.0359 |
| AutoETS          |         0.2790 |            0.0308 |                  0.1105 |
| SeasonalNaive7   |         0.4923 |            0.0315 |                  0.0640 |
| Naive            |         1.1208 |            0.0436 |                  0.0389 |
| AutoARIMA        |         0.4272 |            0.3471 |                  0.8125 |

## 10. Meilleur modèle par segment

**Produits classe ABC = A** (recalculée par fenêtre sur le train uniquement) :

| modele           | segment        |   WAPE |     MAE |   n_produits_fenetres |
|:-----------------|:---------------|-------:|--------:|----------------------:|
| AutoETS          | classe ABC = A | 0.2801 | 11.9583 |                   376 |
| CrostonOptimized | classe ABC = A | 0.3063 | 13.0771 |                   376 |
| WindowAverage28  | classe ABC = A | 0.3074 | 13.1227 |                   376 |
| TSB              | classe ABC = A | 0.3992 | 17.0448 |                   376 |
| AutoARIMA        | classe ABC = A | 0.4273 | 18.2419 |                   376 |
| SeasonalNaive7   | classe ABC = A | 0.4759 | 20.3191 |                   376 |
| Naive            | classe ABC = A | 1.0740 | 45.8537 |                   376 |

**Séries au profil intermittent** (ADI/CV², recalculé par fenêtre sur le train uniquement) :

| modele           | segment               |   WAPE |     MAE |   n_produits_fenetres |
|:-----------------|:----------------------|-------:|--------:|----------------------:|
| AutoETS          | profil = intermittent | 0.2695 |  9.2342 |                   747 |
| CrostonOptimized | profil = intermittent | 0.3098 | 10.6158 |                   747 |
| WindowAverage28  | profil = intermittent | 0.3141 | 10.7638 |                   747 |
| TSB              | profil = intermittent | 0.4004 | 13.7202 |                   747 |
| AutoARIMA        | profil = intermittent | 0.4446 | 15.2334 |                   747 |
| SeasonalNaive7   | profil = intermittent | 0.4824 | 16.5288 |                   747 |
| Naive            | profil = intermittent | 1.1757 | 40.2851 |                   747 |

## 11. Sélection du seuil

- **Meilleur modèle, périmètre comparable :** AutoETS — WAPE 0.2772
- **Meilleure baseline simple :** WindowAverage28 — WAPE 0.3161
- **Meilleur modèle statistique :** AutoETS — WAPE 0.2772
- **Modèle le plus stable entre fenêtres :** WindowAverage28 — écart-type WAPE 0.0090
- **Modèle le moins biaisé :** WindowAverage28 — biais +0.2084
- **Meilleur modèle sur les produits classe A :** AutoETS — WAPE 0.2801
- **Meilleur modèle sur les séries intermittentes :** AutoETS — WAPE 0.2695

**AutoARIMA est marqué NON COMPARABLE sur la fenêtre 4** pour cause de couverture insuffisante (4,6 % < 90 %) et d'un coût de 8 h 07 sur cette seule fenêtre — à peser explicitement dans le choix final, indépendamment de sa métrique agrégée.

**Seuil que LightGBM devra battre (périmètre comparable) : WAPE < 0.2772** (modèle AutoETS).

Aucun modèle n'est sélectionné comme définitif à ce stade.