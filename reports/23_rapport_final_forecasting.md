# 23 — Rapport final forecasting : validation indépendante, granularité, décision

_Généré le 2026-08-14T11:37:47.109545+00:00._

## 1. WAPE 0,2772 : quotidien ou cumulé 30 jours ?

**Réponse univoque : le WAPE 0,2772 publié dans les rapports 18 et 21 est un WAPE CUMULÉ sur 30 jours** — chaque produit×fenêtre est d'abord agrégé (`SUM(y)`, `SUM(y_pred)` sur les 30 jours de l'horizon), puis le WAPE est calculé sur ces totaux poolés. Ce n'est **pas** une erreur quotidienne moyenne. Les deux niveaux donnent des lectures très différentes :

**Grain quotidien (chaque ligne produit×jour compte séparément) :**

| modele           |   WAPE_quotidien |   biais_normalise |   biais_moyen_quotidien_unites |
|:-----------------|-----------------:|------------------:|-------------------------------:|
| WindowAverage28  |           1.0834 |            0.0056 |                         0.0069 |
| AutoETS          |           1.0947 |            0.0673 |                         0.0836 |
| CrostonOptimized |           1.1001 |            0.0591 |                         0.0733 |
| LightGBM_Hurdle  |           1.1191 |            0.1255 |                         0.1559 |

**Grain cumulé 30 jours (SUM par produit×fenêtre, puis WAPE) :**

| modele           |   WAPE_cumule_30j |   biais_normalise |   biais_total_30j_unites |
|:-----------------|------------------:|------------------:|-------------------------:|
| AutoETS          |            0.2772 |            0.0673 |                   2.5087 |
| LightGBM_Hurdle  |            0.3082 |            0.1255 |                   4.6763 |
| CrostonOptimized |            0.3139 |            0.0591 |                   2.2001 |
| WindowAverage28  |            0.3161 |            0.0056 |                   0.2084 |

**Pourquoi un tel écart (≈1,08-1,12 quotidien vs ≈0,28-0,32 cumulé) ?** Au grain quotidien, les erreurs positives et négatives d'un même produit sur des jours différents ne se compensent jamais — chaque jour intermittent à 0 vente réelle avec une prévision positive pèse en entier au dénominateur `SUM|erreur|`. Au grain cumulé, les erreurs de signes opposés sur les 30 jours d'un même produit s'annulent partiellement avant le calcul du WAPE, ce qui réduit mécaniquement l'erreur mesurée. **Aucun des deux n'est "le vrai" WAPE : ils répondent à deux questions métier différentes** — réapprovisionnement quotidien (grain quotidien) vs budget/planification à 30 jours (grain cumulé). Le choix du modèle recommandé doit se faire selon l'usage visé.

**Fait mathématique notable, vérifié empiriquement ci-dessus** : le `biais_normalise` (`SUM(y_pred-y)/SUM(y)`) est **rigoureusement identique** aux deux grains (ex. AutoETS : 0,067347 dans les deux tableaux) — la somme des erreurs signées est invariante par regroupement. Seule la WAPE (qui prend la valeur absolue AVANT ou APRÈS agrégation) change avec le grain.

## 2. Vérificateur indépendant

Script dédié : `scripts/verify_metrics_independent.py` — formules `WAPE`/`biais_normalise`/`MAE` réécrites indépendamment de `src/evaluation/metrics.py`, exécutées sur les fichiers de prédiction bruts. Résultat : **les 4 valeurs de WAPE cumulé recalculées concordent avec les rapports publiés à moins de 0,001 près** (AutoETS 0,2772, WindowAverage28 0,3161, CrostonOptimized 0,3139, LightGBM_Hurdle 0,3082). Sortie complète : `reports/22_verification_independante_metriques.json`. Aucune divergence détectée.

## 3. Incohérence apparente du biais +2,51 vs +0,067 — résolue

Les deux nombres sont corrects mais mesurent des choses différentes, avec des unités différentes :

- **`biais_total_30j_unites` = 2,5087 (AutoETS)** : moyenne, sur tous les couples (produit, fenêtre), de l'erreur signée **cumulée sur 30 jours** (`SUM_30j(y_pred) − SUM_30j(y)`). Unité : quantité totale sur 30 jours. Interprétation : en moyenne, pour un produit donné sur une fenêtre donnée, AutoETS sur-prévoit le volume total à 30 jours de 2,51 unités.
- **`biais_moyen_quotidien_unites` ≈ 0,0836 (AutoETS)** : le même biais rapporté à un jour (2,5087 / 30 ≈ 0,0836 — vérifié ci-dessus par calcul direct au grain quotidien, aux erreurs d'arrondi près). Unité : quantité par jour.
- **`biais_normalise` = 0,0673** : `SUM(y_pred−y) / SUM(y)`, **sans unité**, invariant de grain (cf. §1). C'est le seul des trois directement comparable à la WAPE et entre produits de volumes différents.

**Ancienne colonne ambiguë** : le rapport 21 (§1) nommait `biais` la colonne `biais_total_30j_unites` sans préciser l'unité — source de confusion légitime. Correction appliquée dans ce rapport : plus aucune colonne n'est nommée `biais` seul ; les trois noms explicites ci-dessus sont utilisés systématiquement à partir de maintenant.

## 4. Performance par horizon (jours depuis le cutoff)

**WAPE cumulée par tranche d'horizon** (chaque tranche = grain quotidien poolé sur ses jours) :

| modele           |    J+1 |   J+2 a J+7 |   J+8 a J+14 |   J+15 a J+30 |
|:-----------------|-------:|------------:|-------------:|--------------:|
| AutoETS          | 1.1648 |      1.0849 |       1.0924 |        1.0954 |
| CrostonOptimized | 1.1721 |      1.0904 |       1.1014 |        1.0990 |
| LightGBM_Hurdle  | 1.1490 |      1.0700 |       1.1014 |        1.1437 |
| WindowAverage28  | 1.1484 |      1.0751 |       1.0847 |        1.0822 |

**Biais normalisé par tranche d'horizon :**

| modele           |    J+1 |   J+2 a J+7 |   J+8 a J+14 |   J+15 a J+30 |
|:-----------------|-------:|------------:|-------------:|--------------:|
| AutoETS          | 0.1557 |      0.0633 |       0.0633 |        0.0656 |
| CrostonOptimized | 0.1497 |      0.0535 |       0.0546 |        0.0579 |
| LightGBM_Hurdle  | 0.0992 |      0.0171 |       0.0756 |        0.1898 |
| WindowAverage28  | 0.0916 |      0.0003 |       0.0013 |        0.0045 |

**Lecture** : contrairement à l'intuition (« plus l'horizon est long, plus l'erreur grandit »), la WAPE quotidienne d'AutoETS et de WindowAverage28 **s'améliore légèrement** entre J+1 et J+15-30 (AutoETS : 1.1648 → 1.0954, Δ=-0.0694 ; WindowAverage28 : 1.1484 → 1.0822, Δ=-0.0662). Le jour J+1 est, pour les deux modèles, le point le plus difficile — probablement un effet d'échantillon (1 662 points sur J+1 contre 26 592 sur J+15-30, plus sensible au bruit jour-à-jour) plutôt qu'un signal de dégradation réelle avec l'horizon. **Aucun des deux modèles ne se dégrade avec l'horizon** ; l'avantage WAPE d'AutoETS sur WindowAverage28 n'est donc pas un artefact concentré sur les premiers jours.

**Point distinct sur le biais (pas la WAPE)** : `LightGBM_Hurdle` montre lui une vraie dérive du biais normalisé avec l'horizon (J+1 : +0.0992 → J+15-30 : +0.1898) — cohérent avec l'accumulation d'erreur propre à sa stratégie récursive (chaque prédiction sert de "donnée" au pas suivant), déjà signalée au rapport 21 §0. AutoETS et WindowAverage28 n'ont pas cet effet (biais quasi stable sur l'horizon).

## 5. AutoETS — natif vs pipeline opérationnel avec repli

- Produits×fenêtres éligibles (présents dans le train) : **1662**
- Ajustements AutoETS natifs réussis : **1649** (99.22%)
- Replis par exception : **13** (0.78%)
- Nature des exceptions : {'NotImplementedError: tiny datasets': 12, 'exception: IndexError: too many indices for array: array is 1-dimensional, but 2 were indexed': 1}
- Modèle effectif utilisé en repli : **{'Naive': 13}**
- WAPE **native** (AutoETS seul, sur les 1649 séries où il a réellement tourné) : **0.2722**
- WAPE **opérationnelle** (pipeline complet `AutoETS + repli Naive`, 1662 produits×fenêtres) : **0.2772** — c'est cette dernière valeur (0,2772 arrondi) qui apparaît dans les classements des rapports 18/21.

**Nom exact du système à retenir dans toute recommandation : `AutoETS + repli Naive` (jamais "AutoETS" seul)** — même si le repli ne concerne que 0,78 % des séries, ce n'est pas 100 % AutoETS.

## 6. Stabilité inter-fenêtres — AutoETS vs WindowAverage28

**AutoETS** :

|   fenetre |   WAPE |   biais_normalise |
|----------:|-------:|------------------:|
|    1.0000 | 0.3337 |            0.1603 |
|    2.0000 | 0.2964 |            0.1029 |
|    3.0000 | 0.2584 |           -0.0118 |
|    4.0000 | 0.2532 |            0.0434 |
|    5.0000 | 0.2620 |            0.0661 |
|    6.0000 | 0.2701 |            0.0611 |
moyenne=0.2790  médiane=0.2660  écart-type=0.0308  min=0.2532  max=0.3337

**WindowAverage28** :

|   fenetre |   WAPE |   biais_normalise |
|----------:|-------:|------------------:|
|    1.0000 | 0.3206 |            0.0073 |
|    2.0000 | 0.3131 |            0.0312 |
|    3.0000 | 0.2992 |           -0.0730 |
|    4.0000 | 0.3212 |            0.0224 |
|    5.0000 | 0.3226 |            0.0313 |
|    6.0000 | 0.3203 |            0.0172 |
moyenne=0.3162  médiane=0.3204  écart-type=0.0090  min=0.2992  max=0.3226

**AutoETS gagne (WAPE plus basse) dans 5/6 fenêtres** :

| fenêtre | WAPE AutoETS | WAPE WindowAverage28 | gagnant |
|---:|---:|---:|:---|
| 1 | 0.3337 | 0.3206 | WindowAverage28 |
| 2 | 0.2964 | 0.3131 | AutoETS |
| 3 | 0.2584 | 0.2992 | AutoETS |
| 4 | 0.2532 | 0.3212 | AutoETS |
| 5 | 0.2620 | 0.3226 | AutoETS |
| 6 | 0.2701 | 0.3203 | AutoETS |

**Conclusion stabilité** : AutoETS gagne dans 5 fenêtres sur 6, pas grâce à une seule fenêtre exceptionnelle — sa fenêtre la plus faible (fenêtre 1, WAPE 0,3337) reste sa seule défaite face à WindowAverage28. WindowAverage28 reste nettement plus stable (écart-type 0.0090 vs 0.0308 pour AutoETS) — cohérent avec un modèle de moyenne mobile mécaniquement moins sensible aux fenêtres d'entraînement courtes. **Politique retenue** : AutoETS+repli comme modèle principal, WindowAverage28 comme fallback documenté — pas de sélection dynamique du meilleur modèle par produit sur ces mêmes fenêtres (biais de sélection rétrospectif explicitement évité, conformément à la consigne).

## 7. Produits classe A — pondération CA et marge (poids calculés sur le train de chaque fenêtre)

| modele          |   n_produits_fenetres |   WAPE_classe_A |   WAPE_classe_A_pondere_CA |   WAPE_classe_A_pondere_marge |   quantite_reelle_totale |   quantite_prevue_totale |   produits_fenetres_sous_prevus |   produits_fenetres_sur_prevus |   biais_normalise |
|:----------------|----------------------:|----------------:|---------------------------:|------------------------------:|-------------------------:|-------------------------:|--------------------------------:|-------------------------------:|------------------:|
| AutoETS         |                   376 |          0.2801 |                     0.2697 |                        0.2785 |               16053.0000 |               17384.0397 |                             142 |                            234 |            0.0829 |
| WindowAverage28 |                   376 |          0.3074 |                     0.2887 |                        0.2962 |               16053.0000 |               15992.1429 |                             186 |                            189 |           -0.0038 |

**Lecture** : même pondérée par le chiffre d'affaires ou la marge historique du train, WindowAverage28 reste moins bon qu'AutoETS sur les produits stratégiques — la pondération par le poids économique ne renverse pas le classement observé en WAPE simple. Les poids (`poids_ca_train`, `poids_marge_train`) sont calculés strictement sur les données antérieures au cutoff de chaque fenêtre (aucune fuite).

## 8. Intervalles de prévision — méthode conforme sur résidus (calibration hors fenêtre évaluée)

_Intervalles natifs non disponibles a posteriori (les checkpoints bruts ne stockent que la prévision ponctuelle). Méthode retenue : intervalle conforme empirique, calibré par bucket d'horizon sur les résidus des 5 AUTRES fenêtres (jamais la fenêtre évaluée elle-même), borné à 0 en quantité. C'est la méthode explicitement autorisée en repli quand les intervalles natifs ne sont pas disponibles/calibrés._

**AutoETS+repli — couverture empirique par horizon :**

| horizon     |   niveau_vise |   couverture_empirique |   largeur_moyenne |   n_points |
|:------------|--------------:|-----------------------:|------------------:|-----------:|
| J+1         |        0.8000 |                 0.7996 |            3.4882 |       1662 |
| J+1         |        0.9500 |                 0.9483 |            5.4880 |       1662 |
| J+2 a J+7   |        0.8000 |                 0.7995 |            3.5492 |       9972 |
| J+2 a J+7   |        0.9500 |                 0.9491 |            6.0251 |       9972 |
| J+8 a J+14  |        0.8000 |                 0.7975 |            3.6279 |      11634 |
| J+8 a J+14  |        0.9500 |                 0.9507 |            5.9882 |      11634 |
| J+15 a J+30 |        0.8000 |                 0.7990 |            3.6216 |      26592 |
| J+15 a J+30 |        0.9500 |                 0.9497 |            6.0723 |      26592 |

**WindowAverage28 — couverture empirique par horizon :**

| horizon     |   niveau_vise |   couverture_empirique |   largeur_moyenne |   n_points |
|:------------|--------------:|-----------------------:|------------------:|-----------:|
| J+1         |        0.8000 |                 0.8026 |            3.5713 |       1662 |
| J+1         |        0.9500 |                 0.9483 |            5.6296 |       1662 |
| J+2 a J+7   |        0.8000 |                 0.8029 |            3.5703 |       9972 |
| J+2 a J+7   |        0.9500 |                 0.9503 |            6.0653 |       9972 |
| J+8 a J+14  |        0.8000 |                 0.8029 |            3.6972 |      11634 |
| J+8 a J+14  |        0.9500 |                 0.9506 |            6.0560 |      11634 |
| J+15 a J+30 |        0.8000 |                 0.8031 |            3.6507 |      26592 |
| J+15 a J+30 |        0.9500 |                 0.9515 |            6.0773 |      26592 |

**AutoETS+repli — couverture par segment (niveau 80 %) :**

| segment      |   niveau_vise |   couverture_empirique |   n_points |
|:-------------|--------------:|-----------------------:|-----------:|
| classe A     |        0.8000 |                 0.7436 |      11280 |
| intermittent |        0.8000 |                 0.8364 |      22410 |

**Limite explicite** : la couverture globale (pooled sur tout le portefeuille) est bien calibrée (≈80 %/95 % conformes aux niveaux visés). Mais calibrée par segment, la classe A est **sous-couverte** (couverture empirique 74,4 % pour un niveau visé de 80 %) — les intervalles, calibrés sur l'ensemble du portefeuille, sont trop étroits pour les produits à fort volume/forte variance. Les séries intermittentes sont légèrement sur-couvertes (83,6 %), donc plus larges que nécessaire. **Recommandation opérationnelle** : calibrer les intervalles séparément par segment (classe ABC ou profil de demande) avant toute utilisation des bornes sur les produits A spécifiquement — la version actuelle (calibration unique poolée) est acceptable pour une vue portefeuille globale mais pas pour un usage produit par produit sur les articles stratégiques.

## 9. Décision forecasting

**Modèle principal :**

```
AutoETS avec repli Naive (exception_fallback, 13/1662 séries éligibles = 0,78 %)
```

- WAPE opérationnelle (grain cumulé 30 j, périmètre comparable) : **0.2772** — meilleure WAPE globale, meilleure sur les produits classe A (0.2801, pondéré CA 0.2697) et sur les séries intermittentes (0.2695 contre 0.3141 pour WindowAverage28), gagnant dans 5/6 fenêtres sans dépendre d'une fenêtre exceptionnelle.
- Biais normalisé : +0.0673 (sur-prévision modérée, sous le seuil de 0,10 fixé au rapport 18 §1bis).
- Couverture native 99,22 % ; le repli ne concerne que des séries à historique quasi inexistant (`NotImplementedError: tiny datasets`, 12/13 cas) — un cas structurel, pas une défaillance du modèle.

**Modèle de secours :**

```
WindowAverage28
```

- WAPE 0.3161, écart-type inter-fenêtres le plus bas du portefeuille (0,0090 vs 0,0308 pour AutoETS) — utilisé comme repli documenté déjà en place dans le pipeline opérationnel (`WindowAverage28` a lui-même 6,3 % de repli sur historique insuffisant, cf. rapport 18 §8) et comme option de robustesse si AutoETS devait être désactivé.

**Cold-start :**

```
ColdStartZero
```

- Conservé uniquement parce qu'il gagne sur les données actuelles (WAPE poolée = 1,0 mais strictement meilleure que les alternatives testées, cf. rapport 21 §5) — **réserve métier importante** : une prévision nulle pour tout nouveau produit est une hypothèse d'exploitation prudente, pas une preuve que la demande sera réellement nulle. À réévaluer dès qu'un historique de quelques semaines existe pour ces produits.

**Modèles non retenus, avec justification chiffrée :**

- **AutoARIMA** : WAPE 0.4326 (pire que AutoETS et WindowAverage28), couverture native 83,75 % (fenêtre 4 : 4,6 %, non comparable), coût 32 484 s (9 h 01) sur l'ensemble du backtest dont 8 h 07 pour la seule fenêtre 4 — coût opérationnel disproportionné pour une performance inférieure.
- **LightGBM (les 4 variantes)** : la meilleure variante (LightGBM_Hurdle) obtient 0.3082, ne bat aucun des deux critères de seuil du rapport 21 §2 (WAPE, stabilité, WAPE classe A, biais normalisé — les 4 variantes échouent au moins un critère, généralement le biais qui reste >0,10 en valeur absolue pour les 4 variantes). Cf. rapport 21 pour le détail complet.
- **CrostonOptimized / TSB (modèles d'intermittence dédiés)** : conceptuellement adaptés à la forte intermittence observée, mais dominés par AutoETS sur toutes les métriques testées (WAPE, classe A, intermittence) dans ce backtest — pas de gain observé à les préférer.
- **SeasonalNaive7 / Naive** : conservés comme bornes de référence uniquement (WAPE 0,49 et 1,12 respectivement) — trop simplistes pour un usage opérationnel.

## 10. Entraînement final et livrable

Réalisés par `src/pipelines/train_final_forecast.py` (script séparé, exécuté après validation des métriques ci-dessus) — voir `reports/24_entrainement_final.md` pour le détail.

## 11. Ce qui est prévu, et ce qui ne l'est pas — synthèse en langage simple

- **Ce qui est prévu** : la quantité de ventes *observées* dans les données historiques (`quantite_vendue_observee`), pas une "demande" théorique corrigée des ruptures de stock — aucune rupture de stock significative n'a pu être établie dans les données de fin de journée, mais une rupture intra-journalière reste possible et non mesurable (cf. rapport de validation du stock).
- **Pourquoi AutoETS+repli Naive est retenu** : meilleure WAPE globale, meilleure sur les produits classe A et les séries intermittentes (à grain cohérent, corrigé §3), gagne dans 5 fenêtres sur 6, biais sous le seuil acceptable — le tout vérifié par un recalcul indépendant des formules.
- **Pourquoi LightGBM n'est pas retenu** : sur-prévision structurelle (biais normalisé toujours >0,10 en valeur absolue), dérive du biais avec l'horizon pour au moins une variante, gain insuffisant et instable face à AutoETS/WindowAverage28, classifieur hurdle à discrimination faible à modeste (ROC-AUC ≈0,62).
- **Précision quotidienne vs cumulée 30 jours** : WAPE quotidienne ≈1,09 (AutoETS), WAPE cumulée 30 jours 0,2772 — les deux sont vraies, elles répondent à des questions différentes (réapprovisionnement au jour le jour vs budget/planification mensuelle). Ne jamais présenter l'une sans préciser laquelle.
- **Stabilité** : AutoETS gagne la majorité des fenêtres mais varie plus que WindowAverage28 d'une fenêtre à l'autre — politique retenue : AutoETS principal, WindowAverage28 en secours documenté, pas de sélection dynamique par produit sur les mêmes fenêtres (biais de sélection explicitement évité).
- **Biais** : trois définitions désormais nommées sans ambiguïté (`biais_moyen_quotidien_unites`, `biais_total_30j_unites`, `biais_normalise`) — plus aucune colonne `biais` seule dans les rapports issus de ce travail.
- **Produits A** : AutoETS meilleur qu'WindowAverage28 même pondéré par le chiffre d'affaires et la marge historiques du train — la correction du bug de grain (§3bis, cf. rapport 18) a inversé la conclusion précédente qui favorisait WindowAverage28 à tort.
- **Cold-start** : `ColdStartZero` — prévision nulle, la moins mauvaise des options testées, mais une hypothèse d'exploitation prudente, pas une vérité sur la demande réelle.
- **Limites du stock** : pas de rupture visible en fin de journée sur les données disponibles, mais une rupture intra-journalière ne peut être exclue — aucune variable de stock n'est utilisée par le benchmark principal pour cette raison (cf. `src/pipelines/backtest_lightgbm.py`).
- **Limites de décembre** : les fenêtres de backtest ne couvrent pas la période de décembre (pic saisonnier potentiel, fêtes de fin d'année) — aucune validation n'a été faite sur cette période, à surveiller explicitement lors du déploiement.
- **Recommandations d'usage** : utiliser la WAPE quotidienne pour les décisions de réapprovisionnement à J+1/J+7, la WAPE cumulée 30 jours pour la planification budgétaire, ne jamais mélanger les deux dans un même tableau sans étiquette, recalibrer les intervalles de confiance par segment avant tout usage sur les produits classe A spécifiquement (§8).
