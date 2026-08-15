# 30 — Validation temporelle multi-fenêtres (pricing)

_Généré le 2026-08-14T16:04:31.352453+00:00. 3 fenêtres (simplification documentée vs les 6 fenêtres du forecasting, pour un coût de calcul raisonnable en V1 — cf. registre d'amélioration), test = 60 jours, train strictement antérieur au test, aucun hyperparamètre choisi sur le test._

## Fenêtres

|   index | train_end           | test_start          | test_end            |
|--------:|:--------------------|:--------------------|:--------------------|
|       1 | 2026-02-01 00:00:00 | 2026-02-02 00:00:00 | 2026-04-02 00:00:00 |
|       2 | 2026-04-02 00:00:00 | 2026-04-03 00:00:00 | 2026-06-01 00:00:00 |
|       3 | 2026-06-01 00:00:00 | 2026-06-02 00:00:00 | 2026-07-31 00:00:00 |

## Précision par méthode et fenêtre (prédiction de quantité / CA / marge)

|   fenetre | methode                        |   n_test |   WAPE_quantite |   WAPE_CA |   WAPE_marge |   biais_quantite |   duree_fit_s |   duree_predict_s |
|----------:|:-------------------------------|---------:|----------------:|----------:|-------------:|-----------------:|--------------:|------------------:|
|         1 | descriptif_intra_produit       |    15850 |          1.1520 |    1.1801 |       1.1977 |           0.1972 |        0.2345 |            0.1174 |
|         1 | panel_effets_fixes             |    15850 |          1.0020 |    0.9976 |       1.0115 |          -0.3938 |        6.2204 |            1.1598 |
|         1 | hierarchique_pooling_categorie |    15850 |          1.1750 |    1.2130 |       1.2092 |           0.2509 |        0.5902 |            0.2214 |
|         1 | challenger_ml_lightgbm         |    15850 |          1.0949 |    1.1008 |       1.1187 |           0.0361 |        4.0628 |            0.1029 |
|         2 | descriptif_intra_produit       |    16986 |          1.0804 |    1.0651 |       1.0973 |           0.0638 |        0.2615 |            0.1294 |
|         2 | panel_effets_fixes             |    16986 |          0.9696 |    0.9509 |       0.9729 |          -0.4527 |        3.0426 |            1.1442 |
|         2 | hierarchique_pooling_categorie |    16986 |          1.0969 |    1.0789 |       1.1040 |           0.1424 |        0.7156 |            0.2097 |
|         2 | challenger_ml_lightgbm         |    16986 |          1.0462 |    1.0229 |       1.0519 |          -0.0196 |        1.1338 |            0.1097 |
|         3 | descriptif_intra_produit       |    17899 |          1.1029 |    1.0752 |       1.0915 |           0.0915 |        0.3078 |            0.1199 |
|         3 | panel_effets_fixes             |    17899 |          0.9842 |    0.9660 |       0.9764 |          -0.4481 |        3.4424 |            1.3469 |
|         3 | hierarchique_pooling_categorie |    17899 |          1.1125 |    1.0776 |       1.0928 |           0.1191 |        0.7501 |            0.2349 |
|         3 | challenger_ml_lightgbm         |    17899 |          1.0728 |    1.0391 |       1.0547 |           0.0135 |        1.3243 |            0.1197 |

## Précision moyenne par méthode (poolée sur les 3 fenêtres)

| methode                        |   WAPE_quantite |   WAPE_CA |   WAPE_marge |   biais_quantite |   duree_fit_s |   duree_predict_s |
|:-------------------------------|----------------:|----------:|-------------:|-----------------:|--------------:|------------------:|
| panel_effets_fixes             |          0.9853 |    0.9715 |       0.9869 |          -0.4315 |        4.2351 |            1.2169 |
| challenger_ml_lightgbm         |          1.0713 |    1.0543 |       1.0751 |           0.0100 |        2.1736 |            0.1107 |
| descriptif_intra_produit       |          1.1118 |    1.1068 |       1.1288 |           0.1175 |        0.2679 |            0.1222 |
| hierarchique_pooling_categorie |          1.1281 |    1.1232 |       1.1353 |           0.1708 |        0.6853 |            0.2220 |

## Stabilité de la remise recommandée (produits éligibles individuel, entre les 3 fenêtres)

| methode                        |   ecart_type_moyen |   pct_produits_reco_stable |
|:-------------------------------|-------------------:|---------------------------:|
| challenger_ml_lightgbm         |             1.1152 |                     0.6651 |
| descriptif_intra_produit       |             1.1290 |                     0.7339 |
| hierarchique_pooling_categorie |             0.7549 |                     0.7890 |
| panel_effets_fixes             |             0.2148 |                     0.9312 |

## Taux de recommandations non supportées par l'historique du produit (train de la fenêtre)

| methode                        |   taux_non_supporte |
|:-------------------------------|--------------------:|
| challenger_ml_lightgbm         |              0.3174 |
| descriptif_intra_produit       |              0.2049 |
| hierarchique_pooling_categorie |              0.2974 |
| panel_effets_fixes             |              0.3035 |

**Lecture** : une remise recommandée « non supportée » signifie que la méthode recommande un niveau jamais observé pour CE produit dans le train de la fenêtre (mais observé pour d'autres produits, donc dans la grille) — pas une extrapolation hors grille (déjà interdite par construction), mais un signal de confiance plus faible à traiter dans le simulateur.
