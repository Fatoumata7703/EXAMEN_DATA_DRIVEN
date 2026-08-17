# Forecast Bias — audit final

Convention : `Forecast Bias = Σ(pred − actual) / Σ(actual)`. Les biais positifs indiquent une sur-prévision, les négatifs une sous-prévision. Toutes les mesures sont calculées sur les mêmes observations que la WAPE, sans retrait de produits difficiles.

## Modèles six fenêtres — grain produit×fenêtre

| Modèle | Horizon | Réel | Prévu | Erreur signée | Bias | WAPE | Mean Error | Forecast/Actual | Sur | Sous |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Direct | 1 j | 1 925,0 | 1 897,9 | -27,1 | -0,01408 | 1,07555 | -0,0151 | 0,98592 | 68,28 % | 31,72 % |
| Direct | 7 j | 13 878,0 | 13 530,5 | -347,5 | -0,02504 | 0,45411 | -0,1931 | 0,97496 | 57,00 % | 43,00 % |
| Direct | 14 j | 27 699,0 | 26 974,9 | -724,1 | -0,02614 | 0,34901 | -0,4023 | 0,97386 | 54,44 % | 45,56 % |
| Direct | 30 j | 59 521,0 | 57 977,8 | -1 543,2 | **-0,02593** | 0,25743 | -0,8574 | 0,97407 | 54,22 % | 45,78 % |
| LightGBM Tweedie | 30 j | 59 521,0 | 58 066,0 | -1 455,0 | -0,02445 | 0,31010 | -0,8083 | 0,97555 | 55,06 % | 44,94 % |
| CrostonOptimized | 30 j | 59 521,0 | 55 882,5 | -3 638,5 | -0,06113 | 0,36838 | -2,0214 | 0,93887 | 44,50 % | 50,67 % |
| MovingAverage28 | 30 j | 59 521,0 | 58 037,1 | -1 483,9 | -0,02493 | 0,32312 | -0,8244 | 0,97507 | 47,00 % | 48,00 % |

Le biais direct 30 jours est une sous-prévision globale d'environ **2,59 %**, dans l'objectif ±3 %. Le ratio Forecast/Actual vérifie `1 + Forecast Bias` à l'arrondi près. Un biais faible ne signifie pas une bonne précision : les taux de sur/sous-prévision et la WAPE montrent les compensations produit×fenêtre.

Pour le direct, les biais globaux pondérés sont -0,01408 (quotidien), -0,02504 (7 j), -0,02614 (14 j) et -0,02593 (30 j). Les modèles cumulés sont jugés selon les seuils : direct et Tweedie sont dans ±0,03 à 30 jours, Croston dépasse 0,05 et nécessite calibration ; MovingAverage28 reste dans ±0,03.

## Challengers cumulatifs — pilote F1–F2

| Modèle | Réel | Prévu | Erreur signée | Bias | WAPE | Forecast/Actual | Sur | Sous |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| CatBoost cumulatif | 18 118,0 | 18 695,3 | +577,3 | +0,03186 | 0,29169 | 1,03186 | 60,50 % | 39,50 % |
| Hurdle cumulatif | 18 118,0 | 19 076,1 | +958,1 | +0,05288 | 0,29562 | 1,05288 | 63,50 % | 36,50 % |
| Hiérarchique | 18 118,0 | 14 564,9 | -3 553,1 | -0,19611 | 0,38969 | 0,80389 | 33,67 % | 56,33 % |
| Ensemble contraint | 18 118,0 | 17 580,7 | -537,3 | -0,02966 | 0,29770 | 0,97034 | 56,33 % | 43,67 % |

## Segments

Pour le direct 30 jours, les biais par fenêtre ABC-A sont `+0,0300 / -0,1077 / -0,0676 / -0,0483 / -0,0672 / +0,0366`; intermittents `+0,0361 / -0,0373 / -0,0513 / -0,0547 / -0,0328 / +0,0463`; produits récents ≤28 jours `-0,3167 / -0,0438 / -0,0955 / -0,3877 / -0,3458 / +0,2691`. Les catégories détaillées, ABC-B/C et séries non intermittentes sont dans `forecast_bias_audit.json`. Ces dispersions illustrent pourquoi le biais global ne doit jamais être interprété seul.

## Calibration multiplicative

Le facteur est appris uniquement sur les fenêtres antérieures puis évalué hors échantillon. Pour le direct, la WAPE s'améliore aux fenêtres 3 et 4 (0,24895→0,24788 ; 0,25868→0,25764), mais se dégrade aux fenêtres 2, 5 et 6 ; la stabilité et la non-dégradation globale ne sont donc pas démontrées. Aucune calibration multiplicative n'est appliquée définitivement. Le même constat est plus défavorable pour LightGBM Tweedie (une seule fenêtre sans dégradation).

Artefact détaillé : `reports/advanced/forecast_bias_audit.json`.
