# Rapport d'optimisation avancée

Branche isolée : `experiment/advanced-model-optimization`. La livraison validée sur `rebuild/final-enriched-dataset` reste inchangée.

## État des domaines

| Domaine | État | Décision provisoire |
|---|---|---|
| Forecasting | terminé | CrostonOptimized quotidien inchangé ; LightGBM direct candidat expérimental cumul 30 j |
| Pricing | à exécuter | aucune décision avancée |
| Recommandation | à exécuter | aucune décision avancée |

## Forecasting

Six backtests de 30 jours ont été exécutés avec validation temporelle stricte. Le LightGBM direct par horizon atteint WAPE jour 1,0870, WAPE7 0,4546, WAPE30 0,2583 et biais -0,0259. Il améliore le cumul 30 jours du LightGBM_Tweedie validé de 16,83 %, avec un IC95 % apparié de la différence WAPE [-0,06048 ; -0,04488]. Son gain quotidien de 0,69 % reste sous le seuil de 5 % : CrostonOptimized demeure la décision quotidienne.

Les intervalles conformes, calibrés seulement sur les fenêtres antérieures, couvrent 78,76 % au niveau 80 % et 95,32 % au niveau 95 % globalement ; les résultats ABC-A et intermittents sont comparables. Les challengers CatBoost, XGBoost, hurdle, quantile et ensemble expanding ne dépassent pas le direct sur le cumul 30 jours. La médiane quantile est rejetée pour sous-prévision massive.

Détails reproductibles : [forecasting_advanced.md](advanced/forecasting_advanced.md).

## Gouvernance

Aucun artefact validé n'est remplacé, aucune fusion dans `main`, aucun déploiement et aucune écriture Supabase. Les domaines pricing et recommandation feront l'objet de commits distincts avant la conclusion finale.
