# 15 — Backtest instrumenté des baselines (h=30, 6 fenêtres)

_Généré le 2026-08-14T08:18:45.686450+00:00._

## Fenêtres exactes

| # | fin entraînement | début validation | fin validation | historique (j) | produits évalués | dont nouveaux post-cutoff |
|---|---|---|---|---|---|---|
| 1 | 2026-02-01 | 2026-02-02 | 2026-03-03 | 366 | 265 | 18 |
| 2 | 2026-03-03 | 2026-03-04 | 2026-04-02 | 396 | 275 | 10 |
| 3 | 2026-04-02 | 2026-04-03 | 2026-05-02 | 426 | 283 | 8 |
| 4 | 2026-05-02 | 2026-05-03 | 2026-06-01 | 456 | 292 | 9 |
| 5 | 2026-06-01 | 2026-06-02 | 2026-07-01 | 486 | 300 | 8 |
| 6 | 2026-07-01 | 2026-07-02 | 2026-07-31 | 516 | 300 | 0 |

## Séries à somme réelle nulle sur la fenêtre

0 couple(s) (produit, fenêtre) à vente cumulée nulle sur l'horizon. Traitement : elles contribuent 0 au numérateur et 0 au dénominateur de la WAPE poolée (sans effet), mais leur WAPE **individuelle** est indéfinie (0/0) — exclues des moyennes par produit, comptées séparément, jamais assimilées à une erreur nulle.

## Clipping (prévisions négatives)

| modèle | n. négatives | min prédit | WAPE avant clip | WAPE après clip |
|---|---:|---:|---:|---:|
| AutoARIMA | 59 | -1.076 | nan | nan |
| AutoETS | 23 | -0.283 | nan | nan |
| CrostonOptimized | 0 | 0.000 | nan | nan |
| Naive | 0 | 0.000 | nan | nan |
| SeasonalNaive7 | 0 | 0.000 | nan | nan |
| TSB | 0 | 0.000 | nan | nan |
| WindowAverage28 | 0 | 0.036 | nan | nan |

## Résultats globaux — quantité cumulée par produit sur l'horizon (métrique de sélection)

_WAPE globale = SUM(|y-ŷ|) / SUM(y) sur toutes les observations poolées, jamais la moyenne des WAPE individuelles. Échelle MASE propre à chaque (produit, fenêtre)._

| modele           |   WAPE |     MAE |    RMSE |   RMSSE |    MASE |   sMAPE |   biais |   biais_relatif |   taux_sous_prevision |   cout_asymetrique_1_5x |   cout_asymetrique_2x |
|:-----------------|-------:|--------:|--------:|--------:|--------:|--------:|--------:|----------------:|----------------------:|------------------------:|----------------------:|
| AutoETS          | 0.2881 | 10.5616 | 14.5082 |  5.3409 |  5.8924 |  0.3412 |  1.8755 |          0.0512 |                0.4222 |                 12.7331 |               14.9047 |
| CrostonOptimized | 0.3243 | 11.8877 | 16.0348 |  5.7695 |  6.6618 |  0.3656 |  1.5765 |          0.0430 |                0.4641 |                 14.4655 |               17.0433 |
| WindowAverage28  | 0.3441 | 12.6137 | 16.8676 |  6.2093 |  7.1248 |  0.4348 | -1.4870 |         -0.0406 |                0.5184 |                 16.1389 |               19.6641 |
| TSB              | 0.4115 | 15.0844 | 20.0293 |  7.4863 |  8.7293 |  0.4768 |  0.0778 |          0.0021 |                0.5329 |                 18.8360 |               22.5877 |
| AutoARIMA        | 0.4412 | 16.1711 | 27.2114 | 10.4921 |  9.3361 |  0.5269 |  2.6537 |          0.0724 |                0.4408 |                 19.5505 |               22.9298 |
| SeasonalNaive7   | 0.4982 | 18.2601 | 23.7336 |  8.9907 | 10.6679 |  0.5916 | -0.2612 |         -0.0071 |                0.5423 |                 22.8904 |               27.5207 |
| Naive            | 1.1180 | 40.9802 | 55.5648 | 21.8565 | 24.7014 |  1.4075 |  0.5872 |          0.0160 |                0.6566 |                 51.0784 |               61.1767 |

## Stabilité par fenêtre

| modele           |      1 |      2 |      3 |      4 |      5 |      6 |   ecart_type |
|:-----------------|-------:|-------:|-------:|-------:|-------:|-------:|-------------:|
| WindowAverage28  | 0.3485 | 0.3589 | 0.3287 | 0.3492 | 0.3425 | 0.3389 |       0.0103 |
| CrostonOptimized | 0.3477 | 0.3305 | 0.3051 | 0.3153 | 0.3338 | 0.3174 |       0.0153 |
| TSB              | 0.4353 | 0.4193 | 0.3934 | 0.4143 | 0.3969 | 0.4139 |       0.0154 |
| SeasonalNaive7   | 0.5486 | 0.5085 | 0.4908 | 0.5136 | 0.4555 | 0.4798 |       0.0319 |
| AutoETS          | 0.3509 | 0.3136 | 0.2699 | 0.2624 | 0.2734 | 0.2701 |       0.035  |
| Naive            | 1.138  | 1.1336 | 1.0734 | 1.1759 | 1.1281 | 1.0632 |       0.0426 |
| AutoARIMA        | 0.3528 | 0.3205 | 0.2726 | 1.1316 | 0.2697 | 0.2717 |       0.3422 |

## Par catégorie

| modèle | categorie | WAPE | MAE | n |
|---|---|---:|---:|---:|
| AutoARIMA | Alimentation & Epicerie | nan | nan | 6801 |
| AutoARIMA | Beaute & Soins | nan | nan | 6445 |
| AutoARIMA | Bebe & Enfant | nan | nan | 7073 |
| AutoARIMA | Electronique & High-Tech | nan | nan | 6898 |
| AutoARIMA | Maison & Cuisine | nan | nan | 5507 |
| AutoARIMA | Mode & Vetements | nan | nan | 6118 |
| AutoARIMA | Sport & Loisirs | nan | nan | 5035 |
| AutoARIMA | Telephonie & Accessoires | nan | nan | 6858 |
| AutoETS | Alimentation & Epicerie | nan | nan | 6801 |
| AutoETS | Beaute & Soins | nan | nan | 6445 |
| AutoETS | Bebe & Enfant | nan | nan | 7073 |
| AutoETS | Electronique & High-Tech | nan | nan | 6898 |
| AutoETS | Maison & Cuisine | nan | nan | 5507 |
| AutoETS | Mode & Vetements | nan | nan | 6118 |
| AutoETS | Sport & Loisirs | nan | nan | 5035 |
| AutoETS | Telephonie & Accessoires | nan | nan | 6858 |
| CrostonOptimized | Alimentation & Epicerie | nan | nan | 6801 |
| CrostonOptimized | Beaute & Soins | nan | nan | 6445 |
| CrostonOptimized | Bebe & Enfant | nan | nan | 7073 |
| CrostonOptimized | Electronique & High-Tech | nan | nan | 6898 |
| CrostonOptimized | Maison & Cuisine | nan | nan | 5507 |
| CrostonOptimized | Mode & Vetements | nan | nan | 6118 |
| CrostonOptimized | Sport & Loisirs | nan | nan | 5035 |
| CrostonOptimized | Telephonie & Accessoires | nan | nan | 6858 |
| Naive | Alimentation & Epicerie | nan | nan | 6801 |
| Naive | Beaute & Soins | nan | nan | 6445 |
| Naive | Bebe & Enfant | nan | nan | 7073 |
| Naive | Electronique & High-Tech | nan | nan | 6898 |
| Naive | Maison & Cuisine | nan | nan | 5507 |
| Naive | Mode & Vetements | nan | nan | 6118 |
| Naive | Sport & Loisirs | nan | nan | 5035 |
| Naive | Telephonie & Accessoires | nan | nan | 6858 |
| SeasonalNaive7 | Alimentation & Epicerie | nan | nan | 6801 |
| SeasonalNaive7 | Beaute & Soins | nan | nan | 6445 |
| SeasonalNaive7 | Bebe & Enfant | nan | nan | 7073 |
| SeasonalNaive7 | Electronique & High-Tech | nan | nan | 6898 |
| SeasonalNaive7 | Maison & Cuisine | nan | nan | 5507 |
| SeasonalNaive7 | Mode & Vetements | nan | nan | 6118 |
| SeasonalNaive7 | Sport & Loisirs | nan | nan | 5035 |
| SeasonalNaive7 | Telephonie & Accessoires | nan | nan | 6858 |
| TSB | Alimentation & Epicerie | nan | nan | 6801 |
| TSB | Beaute & Soins | nan | nan | 6445 |
| TSB | Bebe & Enfant | nan | nan | 7073 |
| TSB | Electronique & High-Tech | nan | nan | 6898 |
| TSB | Maison & Cuisine | nan | nan | 5507 |
| TSB | Mode & Vetements | nan | nan | 6118 |
| TSB | Sport & Loisirs | nan | nan | 5035 |
| TSB | Telephonie & Accessoires | nan | nan | 6858 |
| WindowAverage28 | Alimentation & Epicerie | nan | nan | 6801 |
| WindowAverage28 | Beaute & Soins | nan | nan | 6445 |
| WindowAverage28 | Bebe & Enfant | nan | nan | 7073 |
| WindowAverage28 | Electronique & High-Tech | nan | nan | 6898 |
| WindowAverage28 | Maison & Cuisine | nan | nan | 5507 |
| WindowAverage28 | Mode & Vetements | nan | nan | 6118 |
| WindowAverage28 | Sport & Loisirs | nan | nan | 5035 |
| WindowAverage28 | Telephonie & Accessoires | nan | nan | 6858 |

## Par classe ABC (par fenêtre)

| modèle | classe_abc | WAPE | MAE | n |
|---|---|---:|---:|---:|
| AutoARIMA | A | 1.1211 | 1.5955 | 11280 |
| AutoARIMA | B | 1.1671 | 1.4312 | 15540 |
| AutoARIMA | C | 1.1639 | 1.3538 | 23040 |
| AutoARIMA | nan | nan | nan | 875 |
| AutoETS | A | 1.0511 | 1.4959 | 11280 |
| AutoETS | B | 1.1131 | 1.3651 | 15540 |
| AutoETS | C | 1.1077 | 1.2885 | 23040 |
| AutoETS | nan | nan | nan | 875 |
| CrostonOptimized | A | 1.0512 | 1.4960 | 11280 |
| CrostonOptimized | B | 1.1134 | 1.3654 | 15540 |
| CrostonOptimized | C | 1.1199 | 1.3026 | 23040 |
| CrostonOptimized | nan | nan | nan | 875 |
| Naive | A | 1.3224 | 1.8820 | 11280 |
| Naive | B | 1.3676 | 1.6772 | 15540 |
| Naive | C | 1.3884 | 1.6149 | 23040 |
| Naive | nan | nan | nan | 875 |
| SeasonalNaive7 | A | 1.2961 | 1.8445 | 11280 |
| SeasonalNaive7 | B | 1.3422 | 1.6459 | 15540 |
| SeasonalNaive7 | C | nan | nan | 23040 |
| SeasonalNaive7 | nan | nan | nan | 875 |
| TSB | A | 1.0677 | 1.5194 | 11280 |
| TSB | B | 1.1256 | 1.3803 | 15540 |
| TSB | C | 1.1202 | 1.3031 | 23040 |
| TSB | nan | nan | nan | 875 |
| WindowAverage28 | A | 1.0310 | 1.4673 | 11280 |
| WindowAverage28 | B | nan | nan | 15540 |
| WindowAverage28 | C | nan | nan | 23040 |
| WindowAverage28 | nan | nan | nan | 875 |

## Par profil de demande (par fenêtre)

| modèle | profil_demande | WAPE | MAE | n |
|---|---|---:|---:|---:|
| AutoARIMA | erratique | 0.8972 | 1.8731 | 570 |
| AutoARIMA | grumeleux | 1.1406 | 1.4681 | 25950 |
| AutoARIMA | indetermine | 0.9283 | 1.1095 | 210 |
| AutoARIMA | intermittent | 1.1928 | 1.3624 | 22410 |
| AutoARIMA | regulier | 1.0194 | 2.0854 | 720 |
| AutoARIMA | nan | nan | nan | 875 |
| AutoETS | erratique | 0.8979 | 1.8746 | 570 |
| AutoETS | grumeleux | 1.0832 | 1.3943 | 25950 |
| AutoETS | indetermine | 1.1625 | 1.3895 | 210 |
| AutoETS | intermittent | 1.1260 | 1.2861 | 22410 |
| AutoETS | regulier | 0.9590 | 1.9619 | 720 |
| AutoETS | nan | nan | nan | 875 |
| CrostonOptimized | erratique | 0.8544 | 1.7837 | 570 |
| CrostonOptimized | grumeleux | 1.0863 | 1.3982 | 25950 |
| CrostonOptimized | indetermine | 1.2948 | 1.5476 | 210 |
| CrostonOptimized | intermittent | 1.1338 | 1.2949 | 22410 |
| CrostonOptimized | regulier | 0.9918 | 2.0291 | 720 |
| CrostonOptimized | nan | nan | nan | 875 |
| Naive | erratique | 0.9933 | 2.0737 | 570 |
| Naive | grumeleux | 1.3420 | 1.7274 | 25950 |
| Naive | indetermine | 1.1434 | 1.3667 | 210 |
| Naive | intermittent | 1.4245 | 1.6269 | 22410 |
| Naive | regulier | 1.1860 | 2.4264 | 720 |
| Naive | nan | nan | nan | 875 |
| SeasonalNaive7 | erratique | nan | nan | 570 |
| SeasonalNaive7 | grumeleux | nan | nan | 25950 |
| SeasonalNaive7 | indetermine | nan | nan | 210 |
| SeasonalNaive7 | intermittent | nan | nan | 22410 |
| SeasonalNaive7 | regulier | nan | nan | 720 |
| SeasonalNaive7 | nan | nan | nan | 875 |
| TSB | erratique | 0.8591 | 1.7935 | 570 |
| TSB | grumeleux | 1.0946 | 1.4089 | 25950 |
| TSB | indetermine | 1.0298 | 1.2309 | 210 |
| TSB | intermittent | 1.1450 | 1.3077 | 22410 |
| TSB | regulier | 0.9948 | 2.0352 | 720 |
| TSB | nan | nan | nan | 875 |
| WindowAverage28 | erratique | nan | nan | 570 |
| WindowAverage28 | grumeleux | nan | nan | 25950 |
| WindowAverage28 | indetermine | nan | nan | 210 |
| WindowAverage28 | intermittent | nan | nan | 22410 |
| WindowAverage28 | regulier | nan | nan | 720 |
| WindowAverage28 | nan | nan | nan | 875 |

## Par statut (par fenêtre)

| modèle | statut | WAPE | MAE | n |
|---|---|---:|---:|---:|
| AutoARIMA | actif | 1.1523 | 1.4416 | 43710 |
| AutoARIMA | nouveau | 1.1652 | 1.3685 | 6150 |
| AutoARIMA | nan | nan | nan | 875 |
| AutoETS | actif | 1.0891 | 1.3626 | 43710 |
| AutoETS | nouveau | 1.1372 | 1.3356 | 6150 |
| AutoETS | nan | nan | nan | 875 |
| CrostonOptimized | actif | 1.0933 | 1.3679 | 43710 |
| CrostonOptimized | nouveau | 1.1511 | 1.3519 | 6150 |
| CrostonOptimized | nan | nan | nan | 875 |
| Naive | actif | 1.3580 | 1.6990 | 43710 |
| Naive | nouveau | 1.4173 | 1.6646 | 6150 |
| Naive | nan | nan | nan | 875 |
| SeasonalNaive7 | actif | 1.3246 | 1.6573 | 43710 |
| SeasonalNaive7 | nouveau | nan | nan | 6150 |
| SeasonalNaive7 | nan | nan | nan | 875 |
| TSB | actif | 1.1050 | 1.3825 | 43710 |
| TSB | nouveau | 1.1331 | 1.3307 | 6150 |
| TSB | nan | nan | nan | 875 |
| WindowAverage28 | actif | 1.0795 | 1.3506 | 43710 |
| WindowAverage28 | nouveau | nan | nan | 6150 |
| WindowAverage28 | nan | nan | nan | 875 |

## Par promotion

| modèle | en_promotion | WAPE | MAE | n |
|---|---|---:|---:|---:|
| AutoARIMA | 0 | nan | nan | 43973 |
| AutoARIMA | 1 | nan | nan | 6762 |
| AutoETS | 0 | nan | nan | 43973 |
| AutoETS | 1 | nan | nan | 6762 |
| CrostonOptimized | 0 | nan | nan | 43973 |
| CrostonOptimized | 1 | nan | nan | 6762 |
| Naive | 0 | nan | nan | 43973 |
| Naive | 1 | nan | nan | 6762 |
| SeasonalNaive7 | 0 | nan | nan | 43973 |
| SeasonalNaive7 | 1 | nan | nan | 6762 |
| TSB | 0 | nan | nan | 43973 |
| TSB | 1 | nan | nan | 6762 |
| WindowAverage28 | 0 | nan | nan | 43973 |
| WindowAverage28 | 1 | nan | nan | 6762 |

## Temps d'exécution et fiabilité

| modèle | durée totale (s, 6 fenêtres) | séries OK | replis (exception) | replis (budget) | % replis |
|---|---:|---:|---:|---:|---:|
| AutoARIMA | 32484.1 | 1392 | 0 | 270 | 16.25% |
| AutoETS | 225.6 | 1649 | 13 | 0 | 0.78% |
| CrostonOptimized | 15.3 | 1662 | 0 | 0 | 0.00% |
| Naive | 17.0 | 1662 | 0 | 0 | 0.00% |
| SeasonalNaive7 | 16.4 | 1662 | 0 | 0 | 0.00% |
| TSB | 15.5 | 1662 | 0 | 0 | 0.00% |
| WindowAverage28 | 16.6 | 1662 | 0 | 0 | 0.00% |

### Détail des replis (série, fenêtre, modèle, exception)

| modele    |   fenetre | serie     | exception                                                                          | repli   | raison               |
|:----------|----------:|:----------|:-----------------------------------------------------------------------------------|:--------|:---------------------|
| AutoETS   |         1 | PRD000099 | IndexError: too many indices for array: array is 1-dimensional, but 2 were indexed | Naive   | exception_modele     |
| AutoETS   |         1 | PRD000175 | NotImplementedError: tiny datasets                                                 | Naive   | exception_modele     |
| AutoETS   |         2 | PRD000044 | NotImplementedError: tiny datasets                                                 | Naive   | exception_modele     |
| AutoETS   |         3 | PRD000133 | NotImplementedError: tiny datasets                                                 | Naive   | exception_modele     |
| AutoETS   |         3 | PRD000170 | NotImplementedError: tiny datasets                                                 | Naive   | exception_modele     |
| AutoETS   |         3 | PRD000270 | NotImplementedError: tiny datasets                                                 | Naive   | exception_modele     |
| AutoETS   |         4 | PRD000042 | NotImplementedError: tiny datasets                                                 | Naive   | exception_modele     |
| AutoETS   |         4 | PRD000115 | NotImplementedError: tiny datasets                                                 | Naive   | exception_modele     |
| AutoETS   |         4 | PRD000179 | NotImplementedError: tiny datasets                                                 | Naive   | exception_modele     |
| AutoARIMA |         4 | PRD000013 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000014 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000015 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000016 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000018 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000019 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000020 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000021 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000022 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000023 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000024 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000025 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000026 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000027 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000028 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000029 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000030 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000031 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000032 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000033 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000035 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000037 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000038 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000039 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000041 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000042 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000043 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000044 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000046 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000047 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000048 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000049 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000050 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000051 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000052 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000053 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000054 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000055 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000056 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000057 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000058 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000059 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000060 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000061 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000062 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000063 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000064 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000065 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000066 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000067 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000068 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000069 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000070 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000071 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000072 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000073 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000074 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000075 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000076 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000077 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000078 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000079 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000080 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000081 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000082 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000083 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000084 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000085 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000086 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000088 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000089 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000090 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000091 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000092 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000093 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000094 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000095 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000096 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000097 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000098 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000099 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000100 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000101 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000102 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000103 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000104 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000105 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000106 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000107 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000108 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000109 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000110 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000111 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000112 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000113 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000114 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000115 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000116 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000118 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000119 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000120 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000121 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000122 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000123 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000124 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000125 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000126 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000127 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000128 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000129 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000130 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000131 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000132 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000133 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000134 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000135 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000136 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000137 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000138 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000139 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000140 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000143 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000144 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000145 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000146 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000147 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000148 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000149 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000150 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000151 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000152 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000153 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000154 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000155 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000156 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000157 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000159 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000160 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000161 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000162 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000163 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000164 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000165 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000166 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000167 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000168 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000169 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000170 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000171 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000172 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000173 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000174 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000175 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000176 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000178 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000179 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000180 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000181 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000182 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000183 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000184 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000185 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000187 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000188 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000189 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000190 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000191 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000192 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000193 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000194 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000195 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000196 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000197 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000198 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000199 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000200 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000201 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000203 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000204 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000205 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000206 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000207 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000208 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000209 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000210 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000211 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000212 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000213 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000214 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000215 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000216 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000217 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000218 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000219 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000220 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000221 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000222 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000223 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000224 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000225 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000226 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000227 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000228 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000229 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000230 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000231 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000232 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000233 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000234 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000235 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000236 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000237 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000238 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000239 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000240 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000241 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000243 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000244 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000245 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000246 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000247 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000248 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000249 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000250 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000251 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000252 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000254 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000255 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000257 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000258 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000259 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000260 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000261 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000262 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000263 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000264 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000265 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000266 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000267 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000269 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000270 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000271 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000272 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000273 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000274 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000275 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000276 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000277 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000278 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000279 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000280 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000281 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000282 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000283 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000284 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000285 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000286 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000287 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000288 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000289 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000290 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000291 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000292 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000293 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000294 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000295 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000296 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000297 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000298 |                                                                                    | Naive   | budget_temps_depasse |
| AutoARIMA |         4 | PRD000299 |                                                                                    | Naive   | budget_temps_depasse |
| AutoETS   |         5 | PRD000045 | NotImplementedError: tiny datasets                                                 | Naive   | exception_modele     |
| AutoETS   |         5 | PRD000242 | NotImplementedError: tiny datasets                                                 | Naive   | exception_modele     |
| AutoETS   |         6 | PRD000141 | NotImplementedError: tiny datasets                                                 | Naive   | exception_modele     |
| AutoETS   |         6 | PRD000268 | NotImplementedError: tiny datasets                                                 | Naive   | exception_modele     |

> ⚠️ **AutoARIMA** : 16.2% de prédictions issues d'un repli Naive — résultats à interpréter comme *Naive partiel*, pas comme le modèle nommé.
## Synthèse

- **Meilleur modèle (toutes catégories) :** AutoETS — WAPE 0.2881
- **Meilleure baseline simple :** WindowAverage28 — WAPE 0.3441
- **Meilleur modèle statistique :** AutoETS — WAPE 0.2881

**Seuil que LightGBM devra battre : WAPE < 0.2881** (modèle AutoETS, métrique = quantité cumulée par produit sur h=30, poolée).

Fichiers de prédictions : `data\interim\backtest/*.parquet` (42 fichiers).

Aucun modèle n'est sélectionné comme définitif à ce stade.