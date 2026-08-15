# 33 — Comparaison des méthodes et rapport final Pricing V1 exploratoire

_Généré le 2026-08-14T16:06:36.102942+00:00._

> **Je valide le prototype comme Pricing V1 exploratoire, avec garde-fous, mais pas comme moteur de prix optimal prêt pour la production.**

## Règle de sélection (définie avant examen détaillé des résultats)

Parmi les méthodes dont le biais de quantité poolé (|biais_quantite|, moyenne sur les 3 fenêtres) est inférieur à **0.15** unité/jour (seuil documenté : au-delà, le biais dépasse ~10 % de la quantité moyenne du portefeuille, ~1,3 unité/jour), retenir celle de plus faible WAPE quantité. Sinon, retenir celle de plus faible biais absolu.

**Méthode retenue pour le simulateur exploratoire : `challenger_ml_lightgbm`** (jamais présentée comme « méthode gagnante » sans réserve). Justification :

- elle satisfait le seuil de biais (|biais_quantite| = 0.0100 < 0.15) ;
- elle respecte les garde-fous du simulateur (0 violation constatée en sortie) ;
- elle est exploitable pour comparer des scénarios entre eux, à méthode constante ;
- **mais sa précision quantité reste faible : WAPE_quantite = 1.0713 (107.1%)**. Un biais global quasi nul (`+0.0100`) ne veut pas dire « prévisions précises » — un modèle peut compenser des sous-prévisions et des sur-prévisions individuelles tout en ayant une WAPE élevée, ce qui est exactement le cas ici.

## 1. Résultats réels (validation temporelle, poolée sur 3 fenêtres)

| methode                        |   WAPE_quantite |   WAPE_CA |   WAPE_marge |   biais_quantite |   ecart_type_reco |   taux_non_supporte |   duree_fit_s |   duree_predict_s |   produits_couverts | interpretabilite                                                 |
|:-------------------------------|----------------:|----------:|-------------:|-----------------:|------------------:|--------------------:|--------------:|------------------:|--------------------:|:-----------------------------------------------------------------|
| panel_effets_fixes             |          0.9853 |    0.9715 |       0.9869 |          -0.4315 |            1.2960 |              0.3035 |        4.2351 |            1.2169 |                 288 | moyenne (coefficient unique, mais calcul économétrique standard) |
| challenger_ml_lightgbm         |          1.0713 |    1.0543 |       1.0751 |           0.0100 |            2.7076 |              0.3174 |        2.1736 |            0.1107 |                 288 | faible (boîte noire, aucune interprétation causale possible)     |
| descriptif_intra_produit       |          1.1118 |    1.1068 |       1.1288 |           0.1175 |            5.0300 |              0.2049 |        0.2679 |            0.1222 |                 288 | haute (moyennes calendaires directement lisibles)                |
| hierarchique_pooling_categorie |          1.1281 |    1.1232 |       1.1353 |           0.1708 |            3.8675 |              0.2974 |        0.6853 |            0.2220 |                 288 | moyenne (shrinkage explicite, formule simple)                    |

## 2. Méthode retenue pour le simulateur exploratoire

**`challenger_ml_lightgbm`** — voir §Règle de sélection. Violations de garde-fous en sortie du simulateur : **0** (par construction : toute ligne `simulation_status=ok` respecte déjà la contrainte de marge minimale, les lignes qui l'auraient violée sont explicitement marquées `insufficient_evidence`, jamais une fausse simulation silencieuse).

## Conclusion officielle

- Le prix catalogue est fixe pour 300/300 produits.
- Aucune élasticité hors promotion n'est identifiable.
- Les effets des promotions sont observationnels et non causaux.
- Le modèle challenger_ml_lightgbm possède un biais global faible (+0.0100), mais une WAPE quantité élevée de 107.1%.
- Ses estimations individuelles sont donc incertaines.
- Les sorties sont des simulations de remises, pas des prix optimaux garantis.
- Aucune recommandation ne doit être appliquée automatiquement (`automatic_application_allowed=false` sur chaque ligne du simulateur).

## 3. Ce qu'on peut affirmer

- Le prix catalogue est fixe pour 300/300 produits (vérifié table analytique + versions SCD brutes, rapport 26 §1) — aucun prix optimal continu hors promotion n'est calculable, quelle que soit la méthode.
- 218/300 produits ont un historique individuel suffisant pour une estimation directe, 70/300 nécessitent un pooling catégorie, 12/300 n'ont aucune promotion observée (rapport 28).
- Le calendrier promotionnel est fiable à 100 % (rappel/précision, audit initial) — aucune incertitude sur QUAND une promotion a eu lieu, seulement sur QUEL EFFET elle a eu.
- 679 lignes à marge négative sur 73 produits, dont la majorité proviennent de la remise planifiée elle-même (pas seulement du bruit de prix) — un garde-fou de marge minimale reste nécessaire, testé à 4 niveaux (rapport 31).
- **Résultat le plus utile de ce prototype** : avec les données actuelles, les promotions historiques ne semblent généralement pas générer assez de volume supplémentaire pour compenser la réduction de marge — le simulateur, contraint par la marge minimale, recommande donc souvent aucune remise (remise moyenne simulée : 1,2 % sur le scénario marge, cf. rapport 32). C'est un résultat observationnel, pas une preuve causale, mais il est cohérent sur toutes les méthodes testées et sur les 3 fenêtres de validation.

## 4. Ce qui reste seulement observationnel

- **Tout uplift mesuré (les 4 méthodes) reste une association, jamais un effet causal prouvé** — l'affectation des campagnes n'est pas randomisée et son mécanisme n'est pas documenté.
- La méthode retenue (`challenger_ml_lightgbm`) est **la moins interprétable** : elle peut avoir la meilleure précision prédictive relative sans qu'on puisse en tirer un « effet remise » unique.
- Le panel à effets fixes fournit LE SEUL coefficient directement interprétable comme « association par point de remise », mais avec un biais de prédiction plus fort (sous-prévision systématique) — à ne pas utiliser pour dimensionner une simulation sans corriger ce biais.
- **La comparaison aux politiques simples (rapport 34) est elle-même observationnelle pour 4 des 5 politiques comparées** — seule la politique historique est réellement observée ; `off_policy_evaluation_validated=false` pour toutes les simulations.

## 5. Recommandations sûres

- 288 simulations de remise, scénario marge, marge minimale 5% — toutes respectent structurellement coût, marge minimale et grille observée (aucune extrapolation). **Aucune ne doit être appliquée automatiquement.**
- Les niveaux de confiance `moyenne` (le plafond atteignable dans cette V1, cf. rapport 32) restent les seules simulations à présenter en premier pour une revue humaine — jamais `haute`, structurellement indisponible tant que WAPE_quantite ≥ 50 %.
- Les 12 produits `insufficient_evidence` ne doivent recevoir AUCUNE simulation exploitée par ce système — statu quo ou décision manuelle uniquement.

## 6. Limites

- 3 fenêtres de validation temporelle (vs 6 côté forecasting) — simplification documentée pour un coût de calcul raisonnable en V1.
- Bande d'incertitude de scénario simplifiée (`scenario_uncertainty_band`, ±WAPE poolée), **pas un intervalle de confiance statistique**, pas un intervalle conforme calibré par segment comme en forecasting — inscrit au registre V2.
- Confusion catégorie×niveau de remise non totalement débiaisée (le panel FE contrôle catégorie×mois mais la sélection des campagnes elle-même reste non vérifiable).
- Rupture de stock intrajournalière non mesurable (même limite que le forecasting).
- Aucun A/B test prix disponible pour trancher la question causale.
- `off_policy_evaluation_validated=false` : la validation temporelle mesure la capacité à prévoir des quantités pour des remises historiquement observées — elle ne prouve pas que la politique simulée aurait produit la marge indiquée si elle avait été réellement appliquée.

**Aucune publication Supabase, aucun déploiement. Arrêt avant toute intégration applicative.**
