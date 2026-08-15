# 34 — Comparaison aux politiques simples (avec garde-fou méthodologique)

_Généré le 2026-08-14T16:06:36.048610+00:00._

## ⚠️ Avertissement méthodologique — à lire avant le tableau

**Seule la politique « historique » est réellement observée** (ce qui s'est vraiment passé sur chaque fenêtre de test). Les quatre autres politiques (`aucune_remise`, `remise_frequente_produit`, `meilleure_remise_descriptive`, `simulateur_lightgbm_marge`) sont des **scénarios contrefactuels** : leurs quantité/CA/marge sont des **sorties du modèle `challenger_ml`**, entraîné sur le train de chaque fenêtre puis appliqué à un niveau de remise qui n'a PAS été réellement pratiqué sur ces dates. **Ce tableau ne démontre aucun gain de marge réel** — `off_policy_evaluation_validated=false`. Une vraie évaluation de politique nécessiterait des promotions randomisées, un groupe témoin, ou une expérimentation prospective (cf. registre V2).

## Comparaison, par politique (moyenne sur les 3 fenêtres)

|                                                                       |   quantite_moyenne_fenetre |   ca_moyen_fenetre |   marge_moyenne_fenetre |   taux_marge_negative_moyen |   violations_garde_fous_total |   stabilite_ecart_type_marge |
|:----------------------------------------------------------------------|---------------------------:|-------------------:|------------------------:|----------------------------:|------------------------------:|-----------------------------:|
| ('aucune_remise', 'simule_contrefactuel_non_applique')                |                   20150.12 |      1575578927.96 |            404419547.26 |                        0.00 |                          0.00 |                  13452589.36 |
| ('historique', 'observe_reel')                                        |                   20652.33 |      1560222058.33 |            370233762.33 |                        0.00 |                          0.00 |                  32881658.97 |
| ('meilleure_remise_descriptive', 'simule_contrefactuel_non_applique') |                   25694.19 |      1744719267.89 |            280642140.39 |                        0.03 |                       6000.00 |                   4656106.44 |
| ('remise_frequente_produit', 'simule_contrefactuel_non_applique')     |                   20152.82 |      1575569516.70 |            404292086.22 |                        0.00 |                          0.00 |                  13385475.21 |
| ('simulateur_lightgbm_marge', 'simule_contrefactuel_non_applique')    |                   21750.94 |      1646852992.19 |            411063344.65 |                        0.00 |                          0.00 |                  13751418.17 |

## Détail par fenêtre

|   fenetre | politique                    | type                              |   quantite_totale |   ca_total_xof |   marge_totale_xof |   taux_marge_negative |   violations_garde_fous |   n_lignes |
|----------:|:-----------------------------|:----------------------------------|------------------:|---------------:|-------------------:|----------------------:|------------------------:|-----------:|
|         1 | historique                   | observe_reel                      |          19147.00 |  1400588214.00 |       340427811.00 |                  0.01 |                  nan    |      15850 |
|         1 | aucune_remise                | simule_contrefactuel_non_applique |          19244.18 |  1502569368.55 |       389468084.09 |                  0.00 |                    0.00 |      15850 |
|         1 | remise_frequente_produit     | simule_contrefactuel_non_applique |          19244.18 |  1502569368.55 |       389468084.09 |                  0.00 |                    0.00 |      15850 |
|         1 | meilleure_remise_descriptive | simule_contrefactuel_non_applique |          23527.81 |  1613732054.11 |       278586905.99 |                  0.02 |                 1680.00 |      15850 |
|         1 | simulateur_lightgbm_marge    | simule_contrefactuel_non_applique |          20767.14 |  1578772752.15 |       397241451.79 |                  0.00 |                    0.00 |      15850 |
|         2 | historique                   | observe_reel                      |          21789.00 |  1633320320.00 |       364767461.00 |                  0.01 |                  nan    |      16878 |
|         2 | aucune_remise                | simule_contrefactuel_non_applique |          20405.87 |  1592441074.92 |       408246652.77 |                  0.00 |                    0.00 |      16878 |
|         2 | remise_frequente_produit     | simule_contrefactuel_non_applique |          20409.28 |  1592392890.39 |       407914936.03 |                  0.00 |                    0.00 |      16878 |
|         2 | meilleure_remise_descriptive | simule_contrefactuel_non_applique |          25741.24 |  1764740043.32 |       285972237.78 |                  0.03 |                 2040.00 |      16878 |
|         2 | simulateur_lightgbm_marge    | simule_contrefactuel_non_applique |          21823.02 |  1651006554.39 |       411205394.57 |                  0.00 |                    0.00 |      16878 |
|         3 | historique                   | observe_reel                      |          21021.00 |  1646757641.00 |       405506015.00 |                  0.00 |                  nan    |      17255 |
|         3 | aucune_remise                | simule_contrefactuel_non_applique |          20800.33 |  1631726340.41 |       415543904.93 |                  0.00 |                    0.00 |      17255 |
|         3 | remise_frequente_produit     | simule_contrefactuel_non_applique |          20805.00 |  1631746291.16 |       415493238.53 |                  0.00 |                    0.00 |      17255 |
|         3 | meilleure_remise_descriptive | simule_contrefactuel_non_applique |          27813.53 |  1855685706.26 |       277367277.39 |                  0.04 |                 2280.00 |      17255 |
|         3 | simulateur_lightgbm_marge    | simule_contrefactuel_non_applique |          22662.66 |  1710779670.02 |       424743187.59 |                  0.00 |                    0.00 |      17255 |

**Lecture** : `remise_frequente_produit` produit un résultat identique à `aucune_remise` (la remise la plus fréquente est 0 % pour la totalité du portefeuille, cf. rapport 29). `meilleure_remise_descriptive` peut présenter des violations de garde-fous (`violations_garde_fous > 0`) car cette politique est purement descriptive/rétrospective, non filtrée par une contrainte de marge minimale — contrairement à `simulateur_lightgbm_marge` qui respecte le plancher par construction (0 violation attendue).
