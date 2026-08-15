# 31 — Analyse des marges négatives (679 lignes, 73 produits)

_Généré le 2026-08-14T16:04:34.561131+00:00. Aucune correction des données historiques — analyse uniquement._

- Lignes à marge négative : **679**, produits concernés : **73**
- Dont expliquées par le bruit de prix seul (la remise **planifiée** théorique aurait donné une marge ≥0, c'est le bruit ±2-4% du prix payé qui fait passer sous zéro) : **57** (8.4%)
- Dont dues à la remise planifiée elle-même (marge théorique déjà négative, indépendamment du bruit) : **622** (91.6%)

## Par niveau de remise

|   remise_planifiee_pct |   n_lignes |   n_produits |   profondeur_moyenne |   ca_concerne |   perte_totale |
|-----------------------:|-----------:|-------------:|---------------------:|--------------:|---------------:|
|                  10.00 |      16.00 |         3.00 |               -51.64 |     161086.00 |       -1136.00 |
|                  15.00 |      74.00 |        16.00 |              -347.05 |    4629499.00 |      -61453.00 |
|                  20.00 |      47.00 |        10.00 |             -1777.07 |   14488675.00 |     -240873.00 |
|                  25.00 |     426.00 |        50.00 |             -4243.57 |  126296389.00 |    -6264853.00 |
|                  30.00 |     108.00 |        18.00 |              -694.63 |    6166001.00 |     -196562.00 |
|                  40.00 |       8.00 |         1.00 |              -977.84 |     167247.00 |      -20220.00 |

## Par catégorie

| categorie                |   n_lignes |   n_produits |   perte_totale |
|:-------------------------|-----------:|-------------:|---------------:|
| Telephonie & Accessoires |     335.00 |        21.00 |    -6032952.00 |
| Alimentation & Epicerie  |     208.00 |        28.00 |     -393758.00 |
| Bebe & Enfant            |      92.00 |        13.00 |     -204534.00 |
| Electronique & High-Tech |      18.00 |         3.00 |     -139609.00 |
| Sport & Loisirs          |      20.00 |         4.00 |      -10307.00 |
| Maison & Cuisine         |       2.00 |         2.00 |       -1996.00 |
| Beaute & Soins           |       4.00 |         2.00 |       -1941.00 |

## Fréquence par produit (top 15)

| unique_id   |   n_lignes_marge_negative |
|:------------|--------------------------:|
| PRD000095   |                        37 |
| PRD000173   |                        35 |
| PRD000299   |                        34 |
| PRD000026   |                        30 |
| PRD000260   |                        29 |
| PRD000082   |                        25 |
| PRD000203   |                        23 |
| PRD000289   |                        19 |
| PRD000009   |                        18 |
| PRD000246   |                        17 |
| PRD000037   |                        17 |
| PRD000039   |                        13 |
| PRD000240   |                        13 |
| PRD000127   |                        12 |
| PRD000204   |                        11 |

## Campagnes réelles responsables (relu depuis `dim_promotion`, jointure date + portée/cible)

| promotion_id   | portee   | cible                    |   remise_pct |   n_lignes_marge_negative |   perte_totale |
|:---------------|:---------|:-------------------------|-------------:|--------------------------:|---------------:|
| PROMO0051      | category | Telephonie & Accessoires |           25 |                       127 |    -2463610.00 |
| PROMO0101      | category | Alimentation & Epicerie  |           25 |                       120 |     -352525.00 |
| PROMO0027      | category | Telephonie & Accessoires |           25 |                        93 |    -1908211.00 |
| PROMO0036      | category | Telephonie & Accessoires |           25 |                        70 |    -1422254.00 |
| PROMO0095      | category | Alimentation & Epicerie  |           15 |                        67 |      -36660.00 |
| PROMO0076      | category | Bebe & Enfant            |           30 |                        52 |     -106363.00 |
| PROMO0072      | category | Telephonie & Accessoires |           20 |                        45 |     -238877.00 |
| PROMO0062      | category | Bebe & Enfant            |           30 |                        32 |      -77951.00 |
| PROMO0108      | category | Sport & Loisirs          |           30 |                        16 |       -7720.00 |
| PROMO0083      | product  | P00240                   |           25 |                        11 |     -114816.00 |
| PROMO0033      | product  | P00193                   |           40 |                         8 |      -20220.00 |
| PROMO0102      | product  | P00300                   |           25 |                         7 |      -63728.00 |
| PROMO0112      | category | Alimentation & Epicerie  |           10 |                         6 |        -581.00 |
| PROMO0092      | category | Alimentation & Epicerie  |           10 |                         5 |        -324.00 |
| PROMO0075      | category | Alimentation & Epicerie  |           10 |                         5 |        -231.00 |
| PROMO0110      | product  | P00248                   |           25 |                         5 |       -3437.00 |
| PROMO0035      | category | Electronique & High-Tech |           15 |                         5 |      -14875.00 |
| PROMO0026      | category | Beaute & Soins           |           30 |                         4 |       -1941.00 |
| PROMO0017      | category | Sport & Loisirs          |           30 |                         4 |       -2587.00 |
| PROMO0001      | category | Electronique & High-Tech |           15 |                         2 |       -9918.00 |
| PROMO0050      | category | Maison & Cuisine         |           20 |                         2 |       -1996.00 |

## Lignes qui auraient été bloquées selon la marge minimale appliquée (au prix simulé théorique)

|                 |   n_lignes_bloquees_sur_679 |
|:----------------|----------------------------:|
| marge_min_0pct  |                         622 |
| marge_min_5pct  |                         679 |
| marge_min_10pct |                         679 |
| marge_min_15pct |                         679 |

**Lecture** : une marge minimale de 0 % bloque déjà la majorité des cas où la remise planifiée elle-même produirait une marge négative ; les paliers supérieurs (5/10/15 %) bloquent progressivement aussi des lignes à marge positive mais faible — c'est le compromis que le simulateur (rapport 32) doit arbitrer, testé à plusieurs niveaux plutôt que fixé arbitrairement.
