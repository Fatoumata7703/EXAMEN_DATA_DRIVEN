# 10 — Test de signal (exploratoire)

_Sortie de `python scripts/test_signal.py`. Aucun modèle présenté ici n'est un livrable._

```
==============================================================================
TEST DE SIGNAL — FORECASTING (exploratoire, h=30, 6 fenêtres)
==============================================================================

  Baselines, moyennes sur les 6 fenêtres :

  modèle                        WAPE  ±écart     MAE    RMSE    MASE    biais
  Zero                        1.0000  0.0000  1.2389  2.2248   0.700  -1.2389
  Moyenne28j                  1.0876  0.0213  1.3469  1.8277   0.789   0.0114
  MoyenneProduit              1.1022  0.0334  1.3648  1.8045   0.797   0.1237
  MoyenneProduitJour          1.1108  0.0326  1.3754  1.8344   0.803   0.1203
  MoyenneProduitJour+Promo    1.1192  0.0304  1.3859  1.8361   0.809   0.1573
  MoyenneGlobale              1.1584  0.0254  1.4344  1.8521   0.881   0.1155
  SeasonalNaive7              1.3236  0.0121  1.6395  2.5097   0.959  -0.0048
  Naive                       1.3605  0.0444  1.6855  2.5604   0.992   0.0226

  Meilleure baseline : Zero (WAPE 1.0000)
  Stabilité entre fenêtres : écart-type WAPE = 0.0000 (0.0 % de la moyenne)

  --- Décomposition de la variance de y (sur tout l'historique) ---
    niveau produit               part de variance expliquée :  7.42%
    jour de semaine              part de variance expliquée :  0.55%
    mois                         part de variance expliquée :  0.99%
    promotion                    part de variance expliquée :  0.24%
    produit x jour de semaine    part de variance expliquée :  9.40%
    produit x mois               part de variance expliquée : 11.13%

  --- Effets moyens ---
    semaine 1.233 vs week-end 1.548 -> +25.5 %
    mois le plus fort 12 (1.972) vs plus faible 3 (1.217) -> facteur 1.62
    hors promo 1.286 vs promo 1.565 -> +21.7 %
    part de zéros : 50.77%

==============================================================================
TEST DE SIGNAL — PRICING
==============================================================================
  niveaux de remise par produit : médiane 4, min 1, max 7
  produits exposés à >= 2 niveaux : 288 / 300
  produits exposés à >= 3 niveaux : 263 / 300
  campagnes promotionnelles        : 120
  durée des campagnes (jours)      : médiane 9
  produit-jours en promotion       : 15,524 (13.2%)
  produit-jours hors promotion     : 102,239
  promotions concurrentes (>1)     : 426 produit-jours

  --- Support commun : ventes observées par niveau de remise ---
     remise  produit-jours  produits   y moyen
         0%      102,239.0       300     1.286
         5%        3,801.0       218     1.190
        10%        3,501.0       207     1.782
        15%        3,573.0       227     1.444
        20%        2,024.0       132     1.570
        25%        1,405.0       116     2.228
        30%        1,209.0       111     1.686
        40%           11.0         1     1.909

  --- Variation du prix payé ---
    produits dont le prix CATALOGUE varie : 0 / 300
    amplitude prix payé max/min : médiane 1.384, p95 1.486
    amplitude HORS promo (bruit seul) : médiane 1.0405

  --- Marges ---
    taux de marge : médiane 26.3%, p5 9.6%, p95 47.4%
    lignes à marge négative : 1,237 (1.45%)
    remise médiane sur ces lignes : 25 %
    produits concernés : 80 / 300
    par catégorie : {'Telephonie & Accessoires': 644, 'Alimentation & Epicerie': 387, 'Bebe & Enfant': 139}

  --- Élasticité exploratoire (intra-produit, variation promo uniquement) ---
    pente log-log intra-produit : -0.383  (n=57,977 produit-jours avec vente)
    ATTENTION : estimation naïve, sans contrôle du calendrier ni de la
    sélection des campagnes. Indicative du signal disponible, PAS un
    résultat publiable.
```
