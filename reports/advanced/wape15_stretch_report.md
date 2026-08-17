# WAPE15 stretch goal — diagnostic et arrêt honnête

Branche : `experiment/wape15-stretch-goal`.

## Référence et diagnostic préalable

La référence verrouillée reste `LightGBM_direct_per_horizon`, WAPE cumulée 30 jours **0,25831**, au grain produit×fenêtre, sur les six fenêtres et les 300 produits. Le seuil 0,15 exige une baisse absolue de 0,10831 (41,94 % relative), sans réduction de population.

L'oracle historique raisonnable (moyenne de demande connue avant cutoff, projetée sur 30 jours) obtient WAPE 0,4061 / 0,4150 / 0,4121 / 0,4114 / 0,4146 / 0,3951. Il est donc très inférieur à la référence ; il confirme que le seuil 0,15 est extraordinairement ambitieux et non proche d'un simple gain de niveau moyen.

| Segment | WAPE moyenne | Contribution moyenne à l'erreur | Part de quantité |
|---|---:|---:|---:|
| ABC-A | 0,2155 | 25,1 % | 30,0 % |
| ABC-B/C | 0,2768 | 74,9 % | 70,0 % |
| Intermittents | 0,2462 | 94,0 % | 98,4 % |
| Nouveaux produits ≤28 j | 0,5386 | 10,5 % | 4,9 % |
| 10 plus difficiles | 0,5246 | 12,3 % | 6,2 % |
| 20 plus difficiles | 0,5064 | 21,2 % | 11,0 % |
| 50 plus difficiles | 0,4565 | 41,6 % | 23,7 % |

Les catégories et contributions détaillées par fenêtre sont dans `reports/advanced/wape15_diagnostic.json`. Les zéros et l'intermittence dominent l'erreur ; les nouveaux produits ont une WAPE élevée mais une faible masse. Les pics et l'erreur de niveau sont inclus dans les erreurs absolues ; aucune observation n'a été supprimée.

## Pilote direct sur la vraie cible métier

Le pilote fenêtres 1–2 a prédit directement `y_h = somme(y[J+1:J+h])`, avec modèles séparés h=7,14,30 et uniquement des features disponibles au cutoff. Le meilleur candidat à h=30 est `LightGBM_L1_cum`, moyenne WAPE 0,28446 (0,27570 puis 0,29323), contre 0,25831 pour la référence. `LightGBM_Tweedie_cum` atteint 0,29245 et `LightGBM_Poisson_cum` 0,30797.

Le gate de poursuite était une amélioration d'au moins 5 % sur la référence, soit WAPE ≤0,24540. Aucun modèle ne le franchit sur les fenêtres pilotes ; les six fenêtres, Optuna, hiérarchique, CatBoost, XGBoost, hurdle et ensemble n'ont donc pas été lancés inutilement.

## Contrôles méthodologiques

- Population, grain, fenêtres et définition WAPE inchangés.
- Aucun horizon futur dans les features ; promotions futures non utilisées dans le pilote.
- Vues/paniers et stock proviennent uniquement de l'historique ou du cutoff.
- Pas de tuning sur le test, pas de fallback silencieux, pas de NaN ou prédictions négatives.
- Les artefacts de référence sont inchangés.

## Conclusion

Le seuil WAPE ≤0,15 n'est pas atteint. Le meilleur score réellement obtenu dans le pilote est 0,27570 sur la fenêtre 1 et 0,29323 sur la fenêtre 2, soit un écart moyen de 0,02615 au-dessus de la référence et 0,13446 au-dessus de l'objectif. Le plancher empirique actuel est donc autour de 0,25–0,29 pour des modèles directs honnêtes ; atteindre 0,15 nécessiterait probablement davantage d'historique fiable, des signaux de demande exogènes réellement disponibles au cutoff, une meilleure couverture des ruptures/stock et une réduction structurelle de l'incertitude intermittente — pas un changement de métrique.
