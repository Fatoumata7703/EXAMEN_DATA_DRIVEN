# WAPE15 stretch goal — diagnostic et arrêt honnête

Branche : `experiment/wape15-stretch-goal`.

## Référence et diagnostic préalable

La référence verrouillée reste `LightGBM_direct_per_horizon`, WAPE cumulée 30 jours **0,25831**, au grain produit×fenêtre, sur les six fenêtres et les 300 produits. Le seuil 0,15 exige une baisse absolue de 0,10831 (41,94 % relative), sans réduction de population.

La **baseline historique forte sans information future** (moyenne de demande connue avant cutoff, projetée sur 30 jours) obtient WAPE 0,4061 / 0,4150 / 0,4121 / 0,4114 / 0,4146 / 0,3951. Elle est donc très inférieure à la référence ; elle situe le diagnostic, sans constituer une limite théorique.

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

Le pilote fenêtres 1–2 a prédit directement `y_h = somme(y[J+1:J+h])`, avec modèles séparés h=7,14,30 et uniquement des features disponibles au cutoff. Pour le gate, la référence LightGBM direct calculée sur **les mêmes fenêtres F1–F2** est **0,27835**. Les moyennes WAPE30 des quatre familles sont : CatBoost **0,29168**, hurdle **0,29563**, hiérarchique **0,38967**, ensemble **0,29769**.

Le gate de poursuite est une amélioration d'au moins 5 % sur cette référence F1–F2, soit **WAPE ≤0,26443**. Aucun candidat ne le franchit ; aucune exécution six fenêtres ni Optuna n'est donc justifiée.

## Pilote borné des quatre familles distinctes

Chaque famille a été évaluée séparément sur les fenêtres 1–2, au même grain et avec la même population. L'ensemble utilise des poids égaux prédéfinis en fenêtre 1, puis des poids inverse-erreur appris uniquement sur la fenêtre 1 pour la fenêtre 2.

| Candidat | F1 WAPE30 | F2 WAPE30 | Moyenne F1–F2 | Gate pilote |
|---|---:|---:|---:|---|
| CatBoost direct `y_30d` | 0,28877 | 0,29459 | **0,29168** | non |
| Hurdle cumulatif 30 j | 0,29764 | 0,29362 | **0,29563** | non |
| Hiérarchique catégorie→produit | 0,38572 | 0,39362 | **0,38967** | non |
| Ensemble contraint OOS | 0,29384 | 0,30153 | **0,29769** | non |

Le gate est propre à chaque famille : moyenne ≤0,24540 (ou amélioration ≥5 %). Aucun candidat ne le franchit ; aucune famille n'est rejetée au seul motif de l'échec d'une autre. CatBoost est disponible sans installation supplémentaire et ne justifie toutefois pas une poursuite. Le hurdle et l'allocation hiérarchique sont restés non négatifs, sans NaN ni fallback silencieux.

## Contrôles méthodologiques

- Population, grain, fenêtres et définition WAPE inchangés.
- Aucun horizon futur dans les features ; promotions futures non utilisées dans le pilote.
- Vues/paniers et stock proviennent uniquement de l'historique ou du cutoff.
- Pas de tuning sur le test, pas de fallback silencieux, pas de NaN ou prédictions négatives.
- Les artefacts de référence sont inchangés.

## Conclusion

Le seuil WAPE ≤0,15 est **non atteint et peu plausible avec les méthodes et données évaluées**. Le meilleur score réellement obtenu dans le pilote est 0,27570 sur la fenêtre 1 et 0,29323 sur la fenêtre 2, soit un écart moyen de 0,02615 au-dessus de la référence et 0,13446 au-dessus de l'objectif. La plage 0,25–0,29 est une plage empirique observée, pas une limite mathématique prouvée.

Les données qui pourraient permettre une amélioration substantielle sont : historique plus long, date de lancement commercial réelle, demande perdue, disponibilité intrajournalière, campagnes futures connues au cutoff, signaux externes et davantage d'interactions clients.
