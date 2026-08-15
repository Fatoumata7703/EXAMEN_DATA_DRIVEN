# 26 — Audit pricing (descriptif, remises, marges, faisabilité)

_Généré le 2026-08-14T12:37:51.933284+00:00. Source : `data/processed/table_pricing.parquet` (117,763 lignes, 300 produits), stock joint depuis `table_analytique.parquet` (`stock_disponible_lag1` — décalé d'un jour, jamais contemporain). Audit uniquement, aucun modèle entraîné, aucune publication Supabase, aucun déploiement._

## 0. Colonnes vérifiées

| Colonne demandée | Présente | Source |
|---|---|---|
| prix catalogue | ✅ | `prix_catalogue_xof` |
| prix payé | ✅ | `prix_unitaire_paye_xof` |
| coût | ✅ | `cout_unitaire_xof` |
| quantité | ✅ | `quantite_vendue` |
| chiffre d'affaires | ✅ | `chiffre_affaires_net_xof` |
| remise planifiée | ✅ | `remise_planifiee_pct` |
| remise appliquée/estimée | ✅ | `remise_appliquee_pct` |
| promotion | ✅ | `en_promotion` |
| catégorie | ✅ | `categorie` |
| marque | ✅ | `marque` |
| stock | ✅ | `stock_disponible_lag1` |
| calendrier | ✅ | `ds` |
| marge unitaire | ✅ | `marge_unitaire_xof` |
| marge totale | ✅ | `marge_totale_xof` |
| taux de marge | ✅ | `taux_marge` |

**`popularity_score`** : n'existe pas dans ce dataset (déjà écarté au rapport 11 comme paramètre latent du générateur, jamais utilisé même s'il était présent).

## 1. Prix catalogue — variation par produit (vérifié table analytique + versions SCD brutes)

**Chiffres exacts, recalculés en direct depuis la source (lecture seule) :**

- Produits avec un seul prix catalogue historique (table analytique, toute la période) : **300 / 300**
- Produits avec au moins deux prix catalogue distincts (table analytique) : **0 / 300**
- Lignes brutes dans `dim_produit` (relecture directe, hors table analytique) : **300** pour **300** `produit_key` distincts.
- Produits avec plus d'une version SCD (`valid_from`/`valid_to`/`is_current`) enregistrée : **0 / 300**.
- Nombre de versions SCD portant un changement de prix par rapport à la version précédente du même produit : **0**.
- Nombre total de changements de prix catalogue hors promotion (toute source confondue) : **0**.

**Conclusion sans ambiguïté : 0/300 produits ont changé de prix catalogue ; le prix catalogue est fixe pour 300/300 produits.** Vérifié à la fois sur la table analytique aplatie (546 jours × 300 produits) et sur les versions SCD brutes de `dim_produit` (300 ligne(s) pour 300 produits, soit exactement 1 version par produit, `valid_to` NULL et `is_current=True` partout — aucune version n'a jamais été close ni remplacée). Ce n'est pas une lacune de collecte : la table `dim_produit` ne contient tout simplement aucune deuxième version pour aucun produit.

## 2. Amplitude du prix payé

- Amplitude (max/min) du prix payé, toutes lignes vendues : médiane **1.3781**
- Amplitude **hors promotion uniquement** (bruit résiduel) : médiane **1.0402** — au-dessus de le seuil de bruit non exploitable (~2.0-4 % déjà caractérisé au rapport 11).
- Corrélation prix payé × quantité, **hors promotion seulement** : **+0.0239** — quasi nulle, cohérente avec un bruit sans signal de prix exploitable hors promotion.

**Ce bruit hors-promotion n'est jamais traité comme une variation tarifaire exploitable dans les sections suivantes**, conformément à la consigne.

## 3. Niveaux de remise et exposition produit

**Niveaux de remise planifiée observés (jours en promotion) :**

|   remise_planifiee_pct |   n_lignes |
|-----------------------:|-----------:|
|                      5 |       3801 |
|                     10 |       3501 |
|                     15 |       3573 |
|                     20 |       2024 |
|                     25 |       1405 |
|                     30 |       1209 |
|                     40 |         11 |

- Produits exposés à ≥1 niveau de remise réel (>0 %) : **288 / 300**
- Produits exposés à ≥2 niveaux de remise réels distincts : **263 / 300**
- Médiane du nombre de niveaux de remise par produit exposé : **4**

**Réconciliation avec le rapport 11** : le rapport 11 annonçait « 288/300 exposés à ≥2 niveaux » et « 263/300 exposés à ≥3 niveaux ». Recalcul indépendant ici : **288/300 correspond en réalité à ≥1 niveau de remise réel** (le rapport 11 comptait 0 %/hors-promo comme un « niveau » parmi d'autres) et **263/300 correspond à ≥2 niveaux réels** — mêmes données, même résultat, **terminologie différente**, pas une divergence de données. Ce rapport utilise désormais exclusivement le compte de niveaux de remise réels (>0 %), sans compter 0 % comme un niveau, pour éviter toute ambiguïté future.

## 4. Jours promo / hors promo — support commun par niveau de remise

- Jours en promotion : **15,524** (13.18%)
- Jours hors promotion : **102,239** (86.82%)

|                |   produit_jours |   n_produits |   y_moyen |
|:---------------|----------------:|-------------:|----------:|
| 0 (hors promo) |      102239.000 |      300.000 |     1.286 |
| 5.0            |        3801.000 |      218.000 |     1.190 |
| 10.0           |        3501.000 |      207.000 |     1.782 |
| 15.0           |        3573.000 |      227.000 |     1.444 |
| 20.0           |        2024.000 |      132.000 |     1.570 |
| 25.0           |        1405.000 |      116.000 |     2.228 |
| 30.0           |        1209.000 |      111.000 |     1.686 |
| 40.0           |          11.000 |        1.000 |     1.909 |

**Niveaux à support insuffisant (<50 produit-jours), à exclure de toute estimation d'effet** : [40.0].

## 5. Promotions concurrentes

- Produit-jours avec ≥1 promotion concurrente signalée : **15,524**

## 6. Marges négatives et prix sous le coût

- Lignes vendues à marge unitaire négative : **679** (1.17% des jours avec vente), sur **73** produits distincts.
- Lignes où le prix payé est strictement inférieur au coût unitaire : **679** (doit être égal au nombre de lignes à marge négative — identité arithmétique, vérifié : OK).
- Remise appliquée médiane sur ces lignes à marge négative : **25.0 %**

**Taux de marge (toutes lignes avec coût connu) :**

|       |   taux_marge |
|:------|-------------:|
| count |   57977.0000 |
| mean  |       0.2737 |
| std   |       0.1167 |
| min   |      -0.2158 |
| 5%    |       0.1042 |
| 50%   |       0.2715 |
| 95%   |       0.4733 |
| max   |       0.5485 |

**Interprétation** : une marge négative ponctuelle sur une ligne fortement remisée est arithmétique, pas une anomalie de données (déjà établi au rapport 11) — mais reste une contrainte dure pour tout simulateur de remise (§ garde-fous : ne jamais recommander un prix sous le coût).

## 7. Relation remise ↔ volume / chiffre d'affaires / marge (association observationnelle)

|   remise_arrondie |   quantite_moyenne |   ca_moyen |   marge_moyenne |
|------------------:|-------------------:|-----------:|----------------:|
|              5.00 |               1.19 |  115972.20 |        24794.46 |
|             10.00 |               1.78 |  165834.12 |        25236.78 |
|             15.00 |               1.44 |   86692.63 |        11878.64 |
|             20.00 |               1.57 |   93424.82 |        11492.17 |
|             25.00 |               2.23 |  180311.39 |         2969.14 |
|             30.00 |               1.69 |   34540.60 |         3717.60 |
|             40.00 |               1.91 |   15204.27 |        -1838.18 |

**Ces relations sont des moyennes observées par niveau de remise planifiée, jamais un effet causal isolé** — aucun contrôle de sélection de campagne, de calendrier ou de rupture n'est appliqué à ce stade descriptif (cf. §9 pour un contrôle calendrier/catégorie plus poussé, toujours étiqueté association).

## 8. Contrôle du stock (rupture veille, jamais contemporaine)

- Taux de rupture (veille) sur les jours en promotion : **0.0000%**
- Taux de rupture (veille) sur les jours hors promotion : **0.0000%**

Cohérent avec le constat déjà établi (rapport 13) : aucune rupture significative détectable en fin de journée sur cette livraison — le contrôle stock ne change donc pas matériellement les relations remise↔volume ci-dessus, mais reste appliqué par principe (une rupture intrajournalière reste possible et non mesurable).

## 9. Influence du calendrier et de la catégorie

**Remise planifiée moyenne par catégorie (jours en promotion) :**

| categorie                |   remise_moyenne_pct |
|:-------------------------|---------------------:|
| Alimentation & Epicerie  |                12.47 |
| Beaute & Soins           |                12.16 |
| Bebe & Enfant            |                16.56 |
| Electronique & High-Tech |                 9.63 |
| Maison & Cuisine         |                 9.46 |
| Mode & Vetements         |                20.42 |
| Sport & Loisirs          |                14.84 |
| Telephonie & Accessoires |                16.66 |

**Répartition des ventes par mois (contrôle de saisonnalité déjà quantifié au rapport 11 : amplitude déc./mars ≈1,62) — non recalculée ici pour éviter la duplication, cf. rapport 11 §1.**

## 10. Validation temporelle (split avant/après le milieu de la période)

- Période 1 (`2025-02-01` à `2025-10-31`) : corrélation prix×quantité hors promo = **+0.0043**
- Période 2 (`2025-10-31` à `2026-07-31`) : corrélation prix×quantité hors promo = **+0.0351**

Constat stable dans le temps (les deux sont proches de zéro) — pas de dérive suggérant un artefact propre à une sous-période.
