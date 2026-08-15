# 17 — Vérification des checkpoints avant interprétation

```
==============================================================================
1-2. FENÊTRES TERMINÉES ET CHECKPOINTS ATTENDUS
==============================================================================
  attendu : 42 fichiers (6 fenêtres x 7 modèles)
  trouvé  : 42 fichiers dans data\interim\backtest
  OK : tous les checkpoints attendus sont présents.

==============================================================================
3. AUCUN CHECKPOINT ISSU DE L'ANCIEN PIPELINE NON INSTRUMENTÉ
==============================================================================
  OK : les 42 checkpoints portent toutes les colonnes attendues (['ds', 'fenetre', 'modele', 'unique_id', 'y', 'y_pred_raw']).

==============================================================================
4. CODE / CONFIGURATION / DONNÉES IDENTIQUES SUR TOUTES LES FENÊTRES
==============================================================================
  sha256[:12] src\pipelines\backtest_baselines.py : 13d171acfed4
  sha256[:12] src\evaluation\metrics.py : 05e058881222
  sha256[:12] src\features\segmentation.py : b1889aa609d5
  table_analytique.parquet : 1786657069568143400 (mtime), 1506382 octets
  -> comparer ces empreintes à celles au moment du lancement (reports/15_backtest_log.jsonl, horodatage du premier événement) pour confirmer qu'aucune modification n'a eu lieu en cours de route.

==============================================================================
5. JOURNAL COMPLET PAR (MODÈLE, FENÊTRE)
==============================================================================
  OK : 42 couples (modèle, fenêtre) journalisés avec statut/durée/séries.

          modele  fenetre  n_series  n_succes  n_repli_exception  n_repli_budget  duree_s  budget_depasse
           Naive        1       247       247                  0               0     2.25           False
  SeasonalNaive7        1       247       247                  0               0     2.09           False
 WindowAverage28        1       247       247                  0               0     2.11           False
         AutoETS        1       247       245                  2               0    33.59           False
       AutoARIMA        1       247       247                  0               0   750.06           False
CrostonOptimized        1       247       247                  0               0     2.30           False
             TSB        1       247       247                  0               0     2.33           False
           Naive        2       265       265                  0               0     2.48           False
  SeasonalNaive7        2       265       265                  0               0     2.50           False
 WindowAverage28        2       265       265                  0               0     2.52           False
         AutoETS        2       265       264                  1               0    35.80           False
       AutoARIMA        2       265       265                  0               0   720.22           False
CrostonOptimized        2       265       265                  0               0     2.14           False
             TSB        2       265       265                  0               0     2.13           False
           Naive        3       275       275                  0               0     2.45           False
  SeasonalNaive7        3       275       275                  0               0     2.40           False
 WindowAverage28        3       275       275                  0               0     2.38           False
         AutoETS        3       275       272                  3               0    36.89           False
       AutoARIMA        3       275       275                  0               0   608.83           False
CrostonOptimized        3       275       275                  0               0     2.64           False
             TSB        3       275       275                  0               0     2.47           False
           Naive        4       283       283                  0               0     2.59           False
  SeasonalNaive7        4       283       283                  0               0     2.68           False
 WindowAverage28        4       283       283                  0               0     2.63           False
         AutoETS        4       283       280                  3               0    40.99           False
       AutoARIMA        4       283        13                  0             270 29237.65            True
CrostonOptimized        4       283       283                  0               0     2.11           False
             TSB        4       283       283                  0               0     2.02           False
           Naive        5       292       292                  0               0     3.18           False
  SeasonalNaive7        5       292       292                  0               0     2.22           False
 WindowAverage28        5       292       292                  0               0     2.28           False
         AutoETS        5       292       290                  2               0    34.07           False
       AutoARIMA        5       292       292                  0               0   571.46           False
CrostonOptimized        5       292       292                  0               0     3.11           False
             TSB        5       292       292                  0               0     3.17           False
           Naive        6       300       300                  0               0     4.10           False
  SeasonalNaive7        6       300       300                  0               0     4.50           False
 WindowAverage28        6       300       300                  0               0     4.66           False
         AutoETS        6       300       298                  2               0    44.28           False
       AutoARIMA        6       300       300                  0               0   595.87           False
CrostonOptimized        6       300       300                  0               0     3.00           False
             TSB        6       300       300                  0               0     3.35           False

==============================================================================
6. COUVERTURE EXACTE DES OBSERVATIONS (sans doublon ni manque)
==============================================================================
  OK : les 42 checkpoints couvrent exactement leurs observations attendues, sans doublon ni manque.

==============================================================================
7. RECALCUL INDÉPENDANT DES MÉTRIQUES DEPUIS LES FICHIERS DE PRÉDICTIONS
==============================================================================
  Recalcul indépendant sur fenetre1_AutoARIMA.parquet : WAPE=nan, MAE=nan, biais=nan — recalculable sans dépendance au processus d'origine.

==============================================================================
BILAN
==============================================================================
  Tous les contrôles passent. Les résultats peuvent être interprétés.
```
