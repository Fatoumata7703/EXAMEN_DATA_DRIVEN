# 05 — Synthèse exécutive

## Décision

La reconstruction finale est exploitable comme socle analytique contrôlé, pas comme système de décision autonome. Les trois domaines ont été réévalués sur des découpages temporels communs, avec des données fraîches, des cibles confirmées et des garde-fous explicites.

| Domaine | Modèle retenu | Indicateur de sélection | Décision opérationnelle |
|---|---|---|---|
| Forecasting | `CrostonOptimized` | WAPE quotidienne moyenne 1,0765; 3 victoires sur 3 fenêtres | Utiliser pour la planification supervisée; challenger LightGBM Tweedie préférable sur le cumul 30 j (0,3006 contre 0,3497) |
| Pricing | `LightGBM_calibre` | WAPE 0,4167; biais -0,0009 | Utiliser seulement comme simulateur observationnel sous contrainte de coût et marge |
| Recommandation | `hybride_achats_web` | NDCG@10 découverte 0,0372; couverture 18,67 % | Tester sous contrôle humain; ne pas présenter comme performance forte |

## Qualité des données

L'extraction fraîche réconcilie exactement les volumes de référence, les clés, les statuts, les relations ventes/web et l'équation de stock. Les 49 872 commandes web correspondent aux commandes de vente. Les bots ont été retirés; les anonymes ont été conservés sans client artificiel. Les empreintes SHA-256 des cinq datasets sont publiées dans le rapport d'audit.

## Limites qui conditionnent l'usage

- La demande quotidienne est très bruitée et intermittente : une WAPE supérieure à 1 interdit de présenter les prévisions journalières comme précises.
- Les intervalles 80/95 % du forecasting reconstruit ne sont pas encore calibrés sur ses propres résidus; aucune borne non validée n'est livrée.
- Le prix catalogue ne varie pas intra-produit. L'effet des remises est observationnel et ne démontre aucune causalité.
- La recommandation apporte un gain NDCG limité face à la popularité. Le scénario sessionnel atteint seulement `2,36e-05` de NDCG@10 et n'est pas utilisable en production.
- LightFM et ALS/BPR natifs n'étaient pas disponibles; une SVD implicite légère a été évaluée sans justifier l'ajout d'un modèle profond.

## Garde-fous de mise en service

1. Conserver Supabase en lecture seule pour toute reproduction.
2. Exécuter les entraînements séquentiellement afin de préserver la mémoire de la machine.
3. Recalibrer et tester les intervalles de prévision avant toute décision fondée sur une borne.
4. Valider humainement chaque scénario de remise; ne jamais appliquer automatiquement un prix.
5. Soumettre la recommandation hybride à un test en ligne contrôlé avec métriques de conversion, exposition et diversité avant déploiement.

## Traçabilité

Les rapports détaillés `01` à `04`, les métadonnées et les manifestes SHA-256 sont la preuve de livraison. La branche de référence est `rebuild/final-enriched-dataset`; aucun merge vers `main`, déploiement ou write-back Supabase n'est autorisé dans ce périmètre.
