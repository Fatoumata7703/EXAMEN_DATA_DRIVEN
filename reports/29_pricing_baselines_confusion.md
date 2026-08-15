# 29 — Baselines pricing, confusion et support commun

_Généré le 2026-08-14T16:02:26.352999+00:00._

## Baselines (politiques de référence)

|        | unique_id   |   remise_aucune_remise |   remise_frequente_produit |   remise_frequente_categorie |   remise_meilleure_descriptive |   y_moyen_historique |   support |
|:-------|:------------|-----------------------:|---------------------------:|-----------------------------:|-------------------------------:|---------------------:|----------:|
| count  | 300         |                    300 |                        300 |                          300 |                      300       |           300        |   300     |
| unique | 300         |                    nan |                        nan |                          nan |                      nan       |           nan        |   nan     |
| top    | PRD000000   |                    nan |                        nan |                          nan |                      nan       |           nan        |   nan     |
| freq   | 1           |                    nan |                        nan |                          nan |                      nan       |           nan        |   nan     |
| mean   | nan         |                      0 |                          0 |                            0 |                        6.88333 |             1.52012  |   147.1   |
| std    | nan         |                      0 |                          0 |                            0 |                        8.17061 |             0.713088 |   160.433 |
| min    | nan         |                      0 |                          0 |                            0 |                        0       |             0.323077 |    20     |
| 25%    | nan         |                      0 |                          0 |                            0 |                        0       |             1.02078  |    28     |
| 50%    | nan         |                      0 |                          0 |                            0 |                        0       |             1.38237  |    46.5   |
| 75%    | nan         |                      0 |                          0 |                            0 |                       15       |             1.93593  |   228     |
| max    | nan         |                      0 |                          0 |                            0 |                       25       |             4.2      |   502     |

**Remarque honnête** : la baseline « remise la plus fréquente par produit » vaut **0 % pour les 300/300 produits** — attendu, puisque 86,8 % des jours sont hors promotion pour l'ensemble du portefeuille (`reports/26_audit_pricing.md` §4). Cette baseline est donc **strictement identique à « aucune remise »** dans ce dataset : conservée pour respecter la consigne, mais sans valeur discriminante propre.

## Support commun et exposition par niveau de remise

|   remise_pct |   produits_exposes |    jours |   ventes_totales |   n_categories |   mois_couverts |   support_commun_avec_hors_promo |   pct_support_commun |
|-------------:|-------------------:|---------:|-----------------:|---------------:|----------------:|---------------------------------:|---------------------:|
|        5.000 |            218.000 | 3801.000 |         4525.000 |          8.000 |          14.000 |                          218.000 |                1.000 |
|       10.000 |            207.000 | 3501.000 |         6240.000 |          8.000 |          16.000 |                          207.000 |                1.000 |
|       15.000 |            227.000 | 3573.000 |         5159.000 |          8.000 |          15.000 |                          227.000 |                1.000 |
|       20.000 |            132.000 | 2024.000 |         3178.000 |          5.000 |           8.000 |                          132.000 |                1.000 |
|       25.000 |            116.000 | 1405.000 |         3130.000 |          6.000 |          12.000 |                          116.000 |                1.000 |
|       30.000 |            111.000 | 1209.000 |         2038.000 |          4.000 |           6.000 |                          111.000 |                1.000 |
|       40.000 |              1.000 |   11.000 |           21.000 |          1.000 |           1.000 |                            1.000 |                1.000 |

## Remise × week-end

| weekend   |   mean |    count |
|:----------|-------:|---------:|
| False     |  14.32 | 11216.00 |
| True      |  13.77 |  4308.00 |

## Remise × mois

|   mois |   mean |   count |
|-------:|-------:|--------:|
|      1 |   8.71 |  750.00 |
|      2 |  17.65 |  835.00 |
|      3 |  13.24 | 2119.00 |
|      4 |  18.99 | 2214.00 |
|      5 |  10.30 | 2349.00 |
|      6 |  14.13 | 2645.00 |
|      7 |  13.32 | 1991.00 |
|      8 |  15.95 |  539.00 |
|      9 |  15.57 | 1140.00 |
|     10 |  21.42 |  264.00 |
|     11 |  15.00 |  320.00 |
|     12 |  10.20 |  358.00 |

## Remise × catégorie

| categorie                |   mean |   count |
|:-------------------------|-------:|--------:|
| Alimentation & Epicerie  |  12.47 | 1344.00 |
| Beaute & Soins           |  12.16 | 1372.00 |
| Bebe & Enfant            |  16.56 | 2498.00 |
| Electronique & High-Tech |   9.63 | 1900.00 |
| Maison & Cuisine         |   9.46 | 2469.00 |
| Mode & Vetements         |  20.42 | 1904.00 |
| Sport & Loisirs          |  14.84 | 1475.00 |
| Telephonie & Accessoires |  16.66 | 2562.00 |

## Campagnes réelles (relues directement depuis `dim_promotion`, lecture seule)

- Nombre de campagnes : **120** (portée : {'category': 63, 'product': 57})
- Durée médiane : **9 jours** — cohérent avec le rapport 11 (120 campagnes, durée médiane 9 j), reconfirmé ici en relecture directe de la source.

**Métrique complémentaire, à ne pas confondre avec le nombre de campagnes** : en reconstruisant les séquences consécutives de jours promo **par produit** (une campagne à portée catégorie touche plusieurs produits en même temps, donc plusieurs séquences), on obtient **1518** séquences produit-niveau, durée médiane **11 jours** — un nombre plus élevé par construction (fragmentation par produit), pas une divergence de données avec les 120 campagnes réelles.

## Remise × sélection des produits promus (niveau de demande historique hors-promo)

_Si les produits mis fortement en promotion étaient systématiquement les plus (ou moins) vendeurs hors promotion, ce serait un signal de sélection de campagne à contrôler._

|   remise_planifiee_pct |   demande_hors_promo_moyenne_des_produits_exposes |
|-----------------------:|--------------------------------------------------:|
|                  5.000 |                                             1.149 |
|                 10.000 |                                             1.426 |
|                 15.000 |                                             1.157 |
|                 20.000 |                                             1.250 |
|                 25.000 |                                             1.512 |
|                 30.000 |                                             1.079 |
|                 40.000 |                                             1.533 |

Demande hors-promo moyenne, ensemble du portefeuille : **1.286**

**Lecture** : si les moyennes par niveau ci-dessus s'écartent nettement de la moyenne globale, cela suggère que certains niveaux de remise sont appliqués préférentiellement à des produits déjà plus (ou moins) vendeurs — un biais de sélection à garder en tête dans l'interprétation de l'uplift (jamais un effet pur du taux de remise).
