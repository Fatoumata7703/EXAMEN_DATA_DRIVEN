# Rapport d'optimisation avancée

Branche isolée : `experiment/advanced-model-optimization`. La livraison validée sur `rebuild/final-enriched-dataset` reste inchangée.

## État des domaines

| Domaine | État | Décision provisoire |
|---|---|---|
| Forecasting | terminé | CrostonOptimized quotidien inchangé ; LightGBM direct candidat expérimental cumul 30 j |
| Pricing | terminé | aucun challenger promu ; simulateur observationnel uniquement |
| Recommandation | à exécuter | aucune décision avancée |

## Forecasting

Six backtests de 30 jours ont été exécutés avec validation temporelle stricte. Le LightGBM direct par horizon atteint WAPE jour 1,0870, WAPE7 0,4546, WAPE30 0,2583 et biais -0,0259. Il améliore le cumul 30 jours du LightGBM_Tweedie validé de 16,83 %, avec un IC95 % apparié de la différence WAPE [-0,06048 ; -0,04488]. Son gain quotidien de 0,69 % reste sous le seuil de 5 % : CrostonOptimized demeure la décision quotidienne.

Les intervalles conformes, calibrés seulement sur les fenêtres antérieures, couvrent 78,76 % au niveau 80 % et 95,32 % au niveau 95 % globalement ; les résultats ABC-A et intermittents sont comparables. Les challengers CatBoost, XGBoost, hurdle, quantile et ensemble expanding ne dépassent pas le direct sur le cumul 30 jours. La médiane quantile est rejetée pour sous-prévision massive.

Détails reproductibles : [forecasting_advanced.md](advanced/forecasting_advanced.md).

## Pricing

La cible reste la quantité confirmée au grain produit × jour × remise, évaluée sur toutes les lignes de trois tests de 60 jours. L'expérience exclut les proxies contemporains `n_lignes`, prix payé, CA/marge réalisés et achat web. CatBoost enrichi est le meilleur challenger honnête (WAPE 0,5569, biais +0,0206), mais ne franchit pas 0,38 et ne bat la baseline aucune remise que sur deux fenêtres sur trois. Aucun modèle n'est promu.

La référence LightGBM_calibre (WAPE 0,4164) reste figée mais utilisait `n_lignes`, corrélé à 0,708 avec la quantité et indisponible avant les ventes : elle n'est pas une preuve qu'une prédiction décisionnelle à 0,4164 soit réalisable. Le support commun n'a filtré aucune ligne. L'AIPW est publié comme sensibilité observationnelle uniquement. Le simulateur respecte coût et marge minimale sur 300 produits, mais recommande 0 % partout ; application automatique et interprétation causale restent interdites.

Détails reproductibles : [pricing_advanced.md](advanced/pricing_advanced.md).

## Gouvernance

Aucun artefact validé n'est remplacé, aucune fusion dans `main`, aucun déploiement et aucune écriture Supabase. Les domaines pricing et recommandation feront l'objet de commits distincts avant la conclusion finale.
