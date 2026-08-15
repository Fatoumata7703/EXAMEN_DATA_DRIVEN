# 21 — Rapport final comparatif : baselines vs LightGBM

_Généré le 2026-08-14T11:34:10.695866+00:00. Périmètre : identique à l'évaluation « principale » du rapport 18 (produits présents dans le train au cutoff, cold-start exclu). Les prédictions LightGBM du scénario A (qui contiennent aussi des produits cold-start non gérés par le modèle lui-même) sont filtrées sur exactement ce même périmètre avant tout calcul._

## 0. Résumé des contrôles pré-rapport

- 24/24 checkpoints LightGBM présents (`data/interim/backtest_lightgbm/`), 4 modèles × 6 fenêtres.
- 24/24 lignes de journal `statut: succes`, aucun échec, aucun repli budget/exception.
- 0 NaN, 0 Inf, 0 valeur négative sur les 202 940 prédictions LightGBM (`y_pred`).
- **Constat à interpréter avec prudence** : sur toutes les fenêtres, `y_pred` minimal observé reste nettement au-dessus de 0 (ex. fenêtre 6, modèle direct : min = 0,29) alors que 52,7 % des vraies valeurs `y` sont exactement 0 (forte intermittence). Le modèle direct converge vers une valeur proche de la moyenne plutôt que de résoudre nettement le cas « zéro vs positif » au niveau de chaque ligne, et son biais moyen dérive légèrement à la hausse avec l'horizon (effet d'accumulation attendu d'une stratégie récursive). Ce constat motive de lire le classifieur hurdle (§4) comme une tentative de correction, pas comme acquise.

## 1. Évaluation principale — WAPE, MASE, RMSSE, biais, stabilité, coût

| modele           |   WAPE |     MAE |    RMSE |   RMSSE |    MASE |   sMAPE |   biais |   biais_normalise |   taux_sous_prevision |   cout_asymetrique_1_5x |   cout_asymetrique_2x |   WAPE_ecart_type |   couverture_native |   taux_fallback |   temps_total_s |   temps_moyen_par_fenetre_s |
|:-----------------|-------:|--------:|--------:|--------:|--------:|--------:|--------:|------------------:|----------------------:|------------------------:|----------------------:|------------------:|--------------------:|----------------:|----------------:|----------------------------:|
| AutoETS          | 0.2772 | 10.3250 | 14.1431 |  5.3409 |  5.8924 |  0.2883 |  2.5087 |            0.0673 |                0.4037 |                 12.2791 |               14.2332 |            0.0308 |              0.9922 |          0.0385 |        225.6200 |                     37.6033 |
| LightGBM_Hurdle  | 0.3082 | 11.4809 | 14.5736 |  5.7856 |  6.9200 |  0.3150 |  4.6763 |            0.1255 |                0.3616 |                 13.1821 |               14.8832 |            0.0321 |              1.0000 |          0.0000 |        300.0300 |                     50.0050 |
| LightGBM_Tweedie | 0.3123 | 11.6328 | 14.6265 |  6.0396 |  7.1780 |  0.3198 |  6.0227 |            0.1617 |                0.3123 |                 13.0353 |               14.4378 |            0.0341 |              1.0000 |          0.0000 |        276.7600 |                     46.1267 |
| CrostonOptimized | 0.3139 | 11.6934 | 15.7525 |  5.7695 |  6.6618 |  0.3135 |  2.2001 |            0.0591 |                0.4471 |                 14.0667 |               16.4400 |            0.0128 |              1.0000 |          0.0309 |         15.3000 |                      2.5500 |
| WindowAverage28  | 0.3161 | 11.7759 | 15.3815 |  5.7695 |  6.7913 |  0.3344 |  0.2084 |            0.0056 |                0.4868 |                 14.6677 |               17.5596 |            0.0090 |              0.9669 |          0.0630 |         16.5800 |                      2.7633 |
| LightGBM_Poisson | 0.3451 | 12.8542 | 15.8271 |  6.5639 |  7.9490 |  0.3451 |  9.2079 |            0.2472 |                0.2130 |                 13.7658 |               14.6774 |            0.0278 |              1.0000 |          0.0000 |        280.3600 |                     46.7267 |
| LightGBM_direct  | 0.3512 | 13.0818 | 15.9958 |  6.7133 |  8.1239 |  0.3507 |  8.9258 |            0.2396 |                0.2365 |                 14.1209 |               15.1599 |            0.0379 |              1.0000 |          0.0000 |        311.1100 |                     51.8517 |
| TSB              | 0.4025 | 14.9920 | 19.9197 |  7.4863 |  8.7293 |  0.4282 |  0.6537 |            0.0175 |                0.5181 |                 18.5766 |               22.1612 |            0.0144 |              1.0000 |          0.0309 |         15.4700 |                      2.5783 |
| AutoARIMA        | 0.4326 | 16.1134 | 27.3295 | 10.4921 |  9.3361 |  0.4799 |  3.3117 |            0.0889 |                0.4230 |                 19.3138 |               22.5142 |            0.3471 |              0.8375 |          0.1883 |      32484.0900 |                   5414.0150 |
| SeasonalNaive7   | 0.4909 | 18.2846 | 23.7775 |  8.9907 | 10.6679 |  0.5452 |  0.4795 |            0.0129 |                0.5265 |                 22.7359 |               27.1871 |            0.0315 |              0.9922 |          0.0382 |         16.3900 |                      2.7317 |
| Naive            | 1.1198 | 41.7136 | 56.2914 | 21.8565 | 24.7014 |  1.3886 |  1.1793 |            0.0317 |                0.6456 |                 51.8472 |               61.9807 |            0.0436 |              1.0000 |          0.0309 |         17.0500 |                      2.8417 |

_Pour les baselines, `couverture_native`/`taux_fallback` proviennent du rapport 18 (replis historique/exception/budget documentés). Pour LightGBM, la couverture est 1,0 par construction sur ce périmètre filtré (aucun mécanisme de repli — le modèle produit toujours une prédiction brute, cf. §0)._

## 2. Règle de décision multi-critères appliquée (§1bis du rapport 18)

| modele           | 1_WAPE<=AutoETS*1.05   |   WAPE |   seuil_WAPE | 2_stabilite<=mediane_baselines   |   ecart_type_WAPE |   seuil_stabilite | 3_ABC_A<=+10%_meilleure_baseline   |   WAPE_classe_A |   seuil_ABC_A | 4_|biais_normalise|<0.10   |   biais_normalise |   gain_vs_WindowAverage28_% | accepte_4_criteres_numeriques   |
|:-----------------|:-----------------------|-------:|-------------:|:---------------------------------|------------------:|------------------:|:-----------------------------------|----------------:|--------------:|:---------------------------|------------------:|----------------------------:|:--------------------------------|
| LightGBM_direct  | False                  | 0.3512 |       0.2910 | False                            |            0.0379 |            0.0308 | False                              |          0.3295 |        0.3081 | False                      |            0.2396 |                    -11.0900 | False                           |
| LightGBM_Poisson | False                  | 0.3451 |       0.2910 | True                             |            0.0278 |            0.0308 | False                              |          0.3311 |        0.3081 | False                      |            0.2472 |                     -9.1600 | False                           |
| LightGBM_Tweedie | False                  | 0.3123 |       0.2910 | False                            |            0.0341 |            0.0308 | True                               |          0.2964 |        0.3081 | False                      |            0.1617 |                      1.2200 | False                           |
| LightGBM_Hurdle  | False                  | 0.3082 |       0.2910 | False                            |            0.0321 |            0.0308 | False                              |          0.3143 |        0.3081 | False                      |            0.1255 |                      2.5000 | False                           |

## 3. Meilleur modèle par segment

**Produits classe ABC = A :**

| modele           | segment        |   WAPE |     MAE |   n_produits_fenetres |
|:-----------------|:---------------|-------:|--------:|----------------------:|
| AutoETS          | classe ABC = A | 0.2801 | 11.9583 |                   376 |
| LightGBM_Tweedie | classe ABC = A | 0.2964 | 12.6556 |                   376 |
| CrostonOptimized | classe ABC = A | 0.3063 | 13.0771 |                   376 |
| WindowAverage28  | classe ABC = A | 0.3074 | 13.1227 |                   376 |
| LightGBM_Hurdle  | classe ABC = A | 0.3143 | 13.4171 |                   376 |
| LightGBM_direct  | classe ABC = A | 0.3295 | 14.0679 |                   376 |
| LightGBM_Poisson | classe ABC = A | 0.3311 | 14.1366 |                   376 |
| TSB              | classe ABC = A | 0.3992 | 17.0448 |                   376 |
| AutoARIMA        | classe ABC = A | 0.4273 | 18.2419 |                   376 |
| SeasonalNaive7   | classe ABC = A | 0.4759 | 20.3191 |                   376 |
| Naive            | classe ABC = A | 1.0740 | 45.8537 |                   376 |

**Séries au profil intermittent :**

| modele           | segment               |   WAPE |     MAE |   n_produits_fenetres |
|:-----------------|:----------------------|-------:|--------:|----------------------:|
| AutoETS          | profil = intermittent | 0.2695 |  9.2342 |                   747 |
| CrostonOptimized | profil = intermittent | 0.3098 | 10.6158 |                   747 |
| WindowAverage28  | profil = intermittent | 0.3141 | 10.7638 |                   747 |
| LightGBM_Hurdle  | profil = intermittent | 0.3204 | 10.9769 |                   747 |
| LightGBM_Tweedie | profil = intermittent | 0.3324 | 11.3893 |                   747 |
| LightGBM_Poisson | profil = intermittent | 0.3641 | 12.4763 |                   747 |
| LightGBM_direct  | profil = intermittent | 0.3753 | 12.8605 |                   747 |
| TSB              | profil = intermittent | 0.4004 | 13.7202 |                   747 |
| AutoARIMA        | profil = intermittent | 0.4446 | 15.2334 |                   747 |
| SeasonalNaive7   | profil = intermittent | 0.4824 | 16.5288 |                   747 |
| Naive            | profil = intermittent | 1.1757 | 40.2851 |                   747 |

## 4. Classifieur hurdle — évaluation séparée (P(y>0)), jamais mélangée au classement ci-dessus

|   PR_AUC |   ROC_AUC |   Brier |   log_loss |   precision_at_threshold |   recall_at_threshold |   seuil |   fenetre |
|---------:|----------:|--------:|-----------:|-------------------------:|----------------------:|--------:|----------:|
|   0.5500 |    0.6048 |  0.2467 |     0.6898 |                   0.5810 |                0.3682 |  0.5000 |    1.0000 |
|   0.5752 |    0.6097 |  0.2470 |     0.6916 |                   0.5899 |                0.3833 |  0.5000 |    2.0000 |
|   0.6079 |    0.6308 |  0.2431 |     0.6822 |                   0.6207 |                0.4112 |  0.5000 |    3.0000 |
|   0.6097 |    0.6307 |  0.2401 |     0.6744 |                   0.6305 |                0.4262 |  0.5000 |    4.0000 |
|   0.5682 |    0.6068 |  0.2440 |     0.6822 |                   0.5666 |                0.4694 |  0.5000 |    5.0000 |
|   0.5884 |    0.6246 |  0.2410 |     0.6758 |                   0.6140 |                0.3491 |  0.5000 |    6.0000 |

Moyenne sur les 6 fenêtres : PR-AUC=0.583, ROC-AUC=0.618, Brier=0.244, log-loss=0.683, précision(seuil 0,5)=0.600, rappel(seuil 0,5)=0.401.

**Lecture honnête** : un ROC-AUC de 0,60-0,63 et un PR-AUC de 0,55-0,61 (pour une base positive d'environ 47 %) indiquent une discrimination **faible à modeste** entre jour vendu et jour non vendu — nettement au-dessus du hasard, mais loin d'un classifieur fiable. La composante `y_pred = P(y>0) × E(y|y>0)` du modèle hurdle hérite de cette incertitude ; sa WAPE globale (§1) doit être lue avec cette réserve, pas comme la preuve d'une segmentation zéro/positif résolue.

## 5. Cold-start — comparaison séparée (produits absents du train)

**Baselines (repli `ColdStartZero`, identique pour tous les modèles historiques, rapport 18 §3) :**

Voir `reports/18_backtest_rapport_final.md` §3 pour le détail (non recopié ici pour éviter toute divergence de source).

**Stratégies cold-start dédiées à LightGBM, testées sur les mêmes produits (par fenêtre, `reports/20_cold_start_lightgbm.csv`) :**

| modele                      |   fenetre |   n_lignes |   n_points |   volume_reel |   volume_prevu |    MAE |   RMSE |   WAPE |   sMAPE |   MAPE_pos |   biais |   biais_relatif |   taux_sous_prevision |   taux_sur_prevision |   cout_asymetrique_1_5x |   cout_asymetrique_2x |
|:----------------------------|----------:|-----------:|-----------:|--------------:|---------------:|-------:|-------:|-------:|--------:|-----------:|--------:|----------------:|----------------------:|---------------------:|------------------------:|----------------------:|
| ColdStartZero               |         1 |        304 |   304.0000 |      244.0000 |         0.0000 | 0.8026 | 1.6936 | 1.0000 |  0.6513 |     1.0000 | -0.8026 |         -1.0000 |                0.3257 |               0.0000 |                  1.2039 |                1.6053 |
| MoyenneCategorie            |         1 |        304 |   304.0000 |      244.0000 |       348.4902 | 1.2090 | 1.5056 | 1.5063 |  1.5414 |     0.4366 |  0.3437 |          0.4282 |                0.2105 |               0.7895 |                  1.4253 |                1.6417 |
| MoyenneCategorieJourSemaine |         1 |        304 |   304.0000 |      244.0000 |       349.0325 | 1.2196 | 1.5141 | 1.5195 |  1.5481 |     0.4592 |  0.3455 |          0.4305 |                0.2171 |               0.7829 |                  1.4381 |                1.6566 |
| ColdStartZero               |         2 |        186 |   186.0000 |      237.0000 |         0.0000 | 1.2742 | 2.2469 | 1.0000 |  0.9892 |     1.0000 | -1.2742 |         -1.0000 |                0.4946 |               0.0000 |                  1.9113 |                2.5484 |
| MoyenneCategorie            |         2 |        186 |   186.0000 |      237.0000 |       215.6932 | 1.3882 | 1.9092 | 1.0894 |  1.3383 |     0.4803 | -0.1146 |         -0.0899 |                0.3602 |               0.6398 |                  1.7638 |                2.1395 |
| MoyenneCategorieJourSemaine |         2 |        186 |   186.0000 |      237.0000 |       214.7582 | 1.3791 | 1.9051 | 1.0823 |  1.3392 |     0.4855 | -0.1196 |         -0.0938 |                0.3548 |               0.6452 |                  1.7538 |                2.1285 |
| ColdStartZero               |         3 |        112 |   112.0000 |      169.0000 |         0.0000 | 1.5089 | 2.7597 | 1.0000 |  1.0000 |     1.0000 | -1.5089 |         -1.0000 |                0.5000 |               0.0000 |                  2.2634 |                3.0179 |
| MoyenneCategorie            |         3 |        112 |   112.0000 |      169.0000 |       148.6354 | 1.6177 | 2.3128 | 1.0721 |  1.3373 |     0.5218 | -0.1818 |         -0.1205 |                0.3036 |               0.6964 |                  2.0676 |                2.5175 |
| MoyenneCategorieJourSemaine |         3 |        112 |   112.0000 |      169.0000 |       148.6648 | 1.6127 | 2.2969 | 1.0687 |  1.3452 |     0.5499 | -0.1816 |         -0.1203 |                0.3125 |               0.6875 |                  2.0612 |                2.5098 |
| ColdStartZero               |         4 |        134 |   134.0000 |      135.0000 |         0.0000 | 1.0075 | 1.8386 | 1.0000 |  0.9552 |     1.0000 | -1.0075 |         -1.0000 |                0.4776 |               0.0000 |                  1.5112 |                2.0149 |
| MoyenneCategorie            |         4 |        134 |   134.0000 |      135.0000 |       167.7662 | 1.1697 | 1.5305 | 1.1610 |  1.2861 |     0.4293 |  0.2445 |          0.2427 |                0.2761 |               0.7239 |                  1.4009 |                1.6322 |
| MoyenneCategorieJourSemaine |         4 |        134 |   134.0000 |      135.0000 |       168.7828 | 1.1698 | 1.5197 | 1.1612 |  1.2929 |     0.4437 |  0.2521 |          0.2502 |                0.2761 |               0.7239 |                  1.3993 |                1.6287 |
| ColdStartZero               |         5 |        139 |   139.0000 |      168.0000 |         0.0000 | 1.2086 | 2.2633 | 1.0000 |  0.8777 |     1.0000 | -1.2086 |         -1.0000 |                0.4388 |               0.0000 |                  1.8129 |                2.4173 |
| MoyenneCategorie            |         5 |        139 |   139.0000 |      168.0000 |       203.3618 | 1.4674 | 1.8948 | 1.2141 |  1.3766 |     0.4794 |  0.2544 |          0.2105 |                0.3022 |               0.6978 |                  1.7707 |                2.0739 |
| MoyenneCategorieJourSemaine |         5 |        139 |   139.0000 |      168.0000 |       203.7993 | 1.4457 | 1.8721 | 1.1962 |  1.3728 |     0.4798 |  0.2575 |          0.2131 |                0.3022 |               0.6978 |                  1.7428 |                2.0398 |

**WAPE poolée sur les 5 fenêtres concernées (pas une moyenne de WAPE par fenêtre) :**

| modele                      |   WAPE_pooled |   volume_reel_total |   n_lignes_total |   biais_moyen |
|:----------------------------|--------------:|--------------------:|-----------------:|--------------:|
| MoyenneCategorie            |        0.2249 |            953.0000 |         875.0000 |        0.1497 |
| MoyenneCategorieJourSemaine |        0.2279 |            953.0000 |         875.0000 |        0.1509 |
| ColdStartZero               |        1.0000 |            953.0000 |         875.0000 |       -1.0891 |

**Conclusion cold-start** : `ColdStartZero` (prévision nulle) obtient la WAPE poolée la plus basse dans les 5 fenêtres comportant des produits cold-start — les moyennes par catégorie (`MoyenneCategorie`, `MoyenneCategorieJourSemaine`) sur-prévoient systématiquement (biais positif) sans gain de WAPE. **`ColdStartZero` reste la stratégie recommandée pour les nouveaux produits**, y compris dans un pipeline LightGBM.

## 6. Recommandation finale

**Aucune variante LightGBM ne satisfait simultanément les 4 critères numériques du §1bis.** La meilleure variante LightGBM (LightGBM_Hurdle, WAPE=0.3082) n'apporte pas de gain net, sûr et stable par rapport à AutoETS (WAPE=0.2772) ni par rapport à WindowAverage28 (WAPE=0.3161, référence de robustesse). **Recommandation : conserver AutoETS comme modèle de référence (meilleure WAPE globale) et WindowAverage28 comme repli opérationnel robuste** — la complexité additionnelle de LightGBM n'est pas justifiée par les résultats de ce backtest.

**Détail des raisons, par critère :**

- **LightGBM_direct** : WAPE 0.3512 (> seuil 0.2910) ; stabilité 0.0379 (> médiane baselines 0.0308) ; WAPE classe A 0.3295 (> seuil 0.3081) ; biais normalisé +0.2396 (au-dessus de 0,10 en valeur absolue) ; gain vs WindowAverage28 : -11.09 %.
- **LightGBM_Poisson** : WAPE 0.3451 (> seuil 0.2910) ; stabilité 0.0278 (≤ médiane baselines 0.0308) ; WAPE classe A 0.3311 (> seuil 0.3081) ; biais normalisé +0.2472 (au-dessus de 0,10 en valeur absolue) ; gain vs WindowAverage28 : -9.16 %.
- **LightGBM_Tweedie** : WAPE 0.3123 (> seuil 0.2910) ; stabilité 0.0341 (> médiane baselines 0.0308) ; WAPE classe A 0.2964 (≤ seuil 0.3081) ; biais normalisé +0.1617 (au-dessus de 0,10 en valeur absolue) ; gain vs WindowAverage28 : +1.22 %.
- **LightGBM_Hurdle** : WAPE 0.3082 (> seuil 0.2910) ; stabilité 0.0321 (> médiane baselines 0.0308) ; WAPE classe A 0.3143 (> seuil 0.3081) ; biais normalisé +0.1255 (au-dessus de 0,10 en valeur absolue) ; gain vs WindowAverage28 : +2.50 %.

## 7. Ce qui n'a pas été fait (limites explicites)

- Pas d'optimisation d'hyperparamètres (Optuna) : les paramètres LightGBM sont fixes et raisonnables mais non ajustés — un gain reste possible sans changer la conclusion structurelle sur le biais et la couverture zéro/positif.
- Scénario B (stock connu à J+1 uniquement) non intégré à ce classement — analyse séparée, cf. docstring de `src/pipelines/backtest_lightgbm.py`.
- Scénario C (stock projeté sur l'horizon complet) non réalisé : aucune règle de projection validée n'existe à partir de la seule information disponible au cutoff.
- Aucune publication, aucun déploiement : ce rapport s'arrête au tableau comparatif et à la recommandation.