# 37 — Recommandation V1 : résultats des baselines (arrêt avant le modèle hybride)

_Généré le 2026-08-14T20:34:38.059641+00:00. 5 modèles, 4 fenêtres (fenêtre 0 dédiée au cold-start réel, fenêtres 1-3 = validation temporelle stricte, train strictement antérieur au test, aucun split aléatoire), 3 combinaisons de politiques. Aucun modèle hybride construit — arrêt tel que demandé._

## 1. Classement des 5 modèles (politique par défaut : achats déjà faits exclus, stock filtré à J-1, moyenne sur les 4 fenêtres)

| modele                 |   recall_at_5 |   recall_at_10 |   precision_at_5 |   precision_at_10 |   ndcg_at_5 |   ndcg_at_10 |   map_at_10 |   user_coverage |   catalog_coverage |   diversity_at_10 |
|:-----------------------|--------------:|---------------:|-----------------:|------------------:|------------:|-------------:|------------:|----------------:|-------------------:|------------------:|
| popularite_globale     |        0.0403 |         0.0759 |           0.0183 |            0.0174 |      0.0300 |       0.0441 |      0.0235 |          1.0000 |             0.0542 |            0.3333 |
| popularite_recente     |        0.0375 |         0.0749 |           0.0172 |            0.0169 |      0.0288 |       0.0435 |      0.0233 |          1.0000 |             0.0517 |            0.3192 |
| collaboratif_item_item |        0.0315 |         0.0641 |           0.0149 |            0.0149 |      0.0245 |       0.0375 |      0.0199 |          1.0000 |             0.2983 |            0.3924 |
| popularite_categorie   |        0.0329 |         0.0576 |           0.0148 |            0.0132 |      0.0252 |       0.0351 |      0.0194 |          1.0000 |             0.3958 |            0.1096 |
| contenu_categorie_prix |        0.0222 |         0.0471 |           0.0106 |            0.0109 |      0.0170 |       0.0268 |      0.0138 |          1.0000 |             0.6867 |            0.1695 |

**Lecture honnête** : les baselines de popularité (globale et récente) dominent en recall/precision/NDCG/MAP dans ce contexte — un résultat courant et à ne pas sous-estimer : avec une matrice dense (94,5 % sparsité, médiane 16 produits/client) et 300 produits seulement, le signal de popularité pure est déjà fort. Le contenu-based et le filtrage catégoriel sacrifient de la précision pour une bien meilleure couverture catalogue (jusqu'à 73,7 % contre 5-6 % pour la popularité pure) — un compromis explicite, pas un échec.

## 2. Détail par fenêtre

| modele                 |   fenetre |   recall_at_5 |   recall_at_10 |   precision_at_5 |   precision_at_10 |   ndcg_at_5 |   ndcg_at_10 |   map_at_10 |   user_coverage |   catalog_coverage |   diversity_at_10 |
|:-----------------------|----------:|--------------:|---------------:|-----------------:|------------------:|------------:|-------------:|------------:|----------------:|-------------------:|------------------:|
| popularite_recente     |         0 |        0.0545 |         0.1131 |           0.0201 |            0.0206 |      0.0392 |       0.0610 |      0.0346 |          1.0000 |             0.0433 |            0.3001 |
| popularite_globale     |         0 |        0.0580 |         0.1098 |           0.0212 |            0.0202 |      0.0407 |       0.0599 |      0.0342 |          1.0000 |             0.0433 |            0.3177 |
| popularite_categorie   |         0 |        0.0488 |         0.0850 |           0.0174 |            0.0151 |      0.0346 |       0.0478 |      0.0286 |          1.0000 |             0.3400 |            0.1382 |
| contenu_categorie_prix |         0 |        0.0331 |         0.0711 |           0.0125 |            0.0131 |      0.0231 |       0.0373 |      0.0203 |          1.0000 |             0.5100 |            0.1574 |
| collaboratif_item_item |         0 |        0.0302 |         0.0709 |           0.0113 |            0.0125 |      0.0219 |       0.0368 |      0.0204 |          1.0000 |             0.5100 |            0.5167 |
| popularite_recente     |         1 |        0.0359 |         0.0670 |           0.0170 |            0.0159 |      0.0271 |       0.0395 |      0.0209 |          1.0000 |             0.0533 |            0.2916 |
| popularite_globale     |         1 |        0.0358 |         0.0658 |           0.0167 |            0.0158 |      0.0269 |       0.0392 |      0.0208 |          1.0000 |             0.0567 |            0.3545 |
| collaboratif_item_item |         1 |        0.0329 |         0.0611 |           0.0157 |            0.0147 |      0.0255 |       0.0371 |      0.0199 |          1.0000 |             0.3067 |            0.3625 |
| popularite_categorie   |         1 |        0.0273 |         0.0476 |           0.0136 |            0.0120 |      0.0217 |       0.0301 |      0.0164 |          1.0000 |             0.4000 |            0.1000 |
| contenu_categorie_prix |         1 |        0.0207 |         0.0435 |           0.0101 |            0.0103 |      0.0159 |       0.0249 |      0.0127 |          1.0000 |             0.7367 |            0.1692 |
| collaboratif_item_item |         2 |        0.0340 |         0.0682 |           0.0177 |            0.0177 |      0.0277 |       0.0417 |      0.0217 |          1.0000 |             0.2300 |            0.3492 |
| popularite_globale     |         2 |        0.0363 |         0.0683 |           0.0185 |            0.0175 |      0.0275 |       0.0406 |      0.0206 |          1.0000 |             0.0567 |            0.3551 |
| popularite_recente     |         2 |        0.0303 |         0.0625 |           0.0164 |            0.0165 |      0.0250 |       0.0382 |      0.0193 |          1.0000 |             0.0500 |            0.3857 |
| popularite_categorie   |         2 |        0.0293 |         0.0510 |           0.0150 |            0.0133 |      0.0231 |       0.0320 |      0.0167 |          1.0000 |             0.4167 |            0.1000 |
| contenu_categorie_prix |         2 |        0.0181 |         0.0394 |           0.0102 |            0.0107 |      0.0148 |       0.0236 |      0.0114 |          1.0000 |             0.7800 |            0.1713 |
| popularite_globale     |         3 |        0.0310 |         0.0596 |           0.0166 |            0.0159 |      0.0248 |       0.0366 |      0.0186 |          1.0000 |             0.0600 |            0.3059 |
| popularite_recente     |         3 |        0.0295 |         0.0569 |           0.0152 |            0.0147 |      0.0238 |       0.0352 |      0.0185 |          1.0000 |             0.0600 |            0.2996 |
| collaboratif_item_item |         3 |        0.0288 |         0.0562 |           0.0152 |            0.0148 |      0.0230 |       0.0343 |      0.0174 |          1.0000 |             0.1467 |            0.3411 |
| popularite_categorie   |         3 |        0.0262 |         0.0469 |           0.0134 |            0.0126 |      0.0215 |       0.0303 |      0.0161 |          1.0000 |             0.4267 |            0.1000 |
| contenu_categorie_prix |         3 |        0.0169 |         0.0342 |           0.0098 |            0.0095 |      0.0144 |       0.0215 |      0.0108 |          1.0000 |             0.7200 |            0.1799 |

## 3. Comparaison des politiques explicites

### a) Inclure vs exclure les produits déjà achetés

|                                                                 |   recall_at_10 |   precision_at_10 |   ndcg_at_10 |   catalog_coverage |
|:----------------------------------------------------------------|---------------:|------------------:|-------------:|-------------------:|
| ('defaut_exclut_achats_stock_filtre', 'collaboratif_item_item') |         0.0641 |            0.0149 |       0.0375 |             0.2983 |
| ('defaut_exclut_achats_stock_filtre', 'contenu_categorie_prix') |         0.0471 |            0.0109 |       0.0268 |             0.6867 |
| ('defaut_exclut_achats_stock_filtre', 'popularite_categorie')   |         0.0576 |            0.0132 |       0.0351 |             0.3958 |
| ('defaut_exclut_achats_stock_filtre', 'popularite_globale')     |         0.0759 |            0.0174 |       0.0441 |             0.0542 |
| ('defaut_exclut_achats_stock_filtre', 'popularite_recente')     |         0.0749 |            0.0169 |       0.0435 |             0.0517 |
| ('inclut_produits_deja_achetes', 'collaboratif_item_item')      |         0.0646 |            0.0150 |       0.0378 |             0.2975 |
| ('inclut_produits_deja_achetes', 'contenu_categorie_prix')      |         0.0472 |            0.0108 |       0.0270 |             0.6842 |
| ('inclut_produits_deja_achetes', 'popularite_categorie')        |         0.0589 |            0.0135 |       0.0357 |             0.2667 |
| ('inclut_produits_deja_achetes', 'popularite_globale')          |         0.0766 |            0.0174 |       0.0443 |             0.0333 |
| ('inclut_produits_deja_achetes', 'popularite_recente')          |         0.0755 |            0.0169 |       0.0437 |             0.0333 |

### b) Filtrer vs ne pas filtrer par stock connu à J-1

|                                                                 |   recall_at_10 |   precision_at_10 |   ndcg_at_10 |   catalog_coverage |
|:----------------------------------------------------------------|---------------:|------------------:|-------------:|-------------------:|
| ('defaut_exclut_achats_stock_filtre', 'collaboratif_item_item') |         0.0641 |            0.0149 |       0.0375 |             0.2983 |
| ('defaut_exclut_achats_stock_filtre', 'contenu_categorie_prix') |         0.0471 |            0.0109 |       0.0268 |             0.6867 |
| ('defaut_exclut_achats_stock_filtre', 'popularite_categorie')   |         0.0576 |            0.0132 |       0.0351 |             0.3958 |
| ('defaut_exclut_achats_stock_filtre', 'popularite_globale')     |         0.0759 |            0.0174 |       0.0441 |             0.0542 |
| ('defaut_exclut_achats_stock_filtre', 'popularite_recente')     |         0.0749 |            0.0169 |       0.0435 |             0.0517 |
| ('sans_filtre_stock', 'collaboratif_item_item')                 |         0.0641 |            0.0149 |       0.0375 |             0.3000 |
| ('sans_filtre_stock', 'contenu_categorie_prix')                 |         0.0471 |            0.0109 |       0.0268 |             0.6867 |
| ('sans_filtre_stock', 'popularite_categorie')                   |         0.0576 |            0.0132 |       0.0351 |             0.3958 |
| ('sans_filtre_stock', 'popularite_globale')                     |         0.0759 |            0.0174 |       0.0441 |             0.0542 |
| ('sans_filtre_stock', 'popularite_recente')                     |         0.0749 |            0.0169 |       0.0435 |             0.0517 |

## 4. Résultats par segment

### Cold-start réel (fenêtre 0 dédiée, coupure 2025-05-01, clients sans aucun achat antérieur)

| modele                 |   recall_at_5 |   recall_at_10 |   ndcg_at_10 |   map_at_10 |
|:-----------------------|--------------:|---------------:|-------------:|------------:|
| collaboratif_item_item |        0.0416 |         0.0846 |       0.0454 |      0.0248 |
| contenu_categorie_prix |        0.0416 |         0.0846 |       0.0454 |      0.0248 |
| popularite_categorie   |        0.0559 |         0.1110 |       0.0603 |      0.0344 |
| popularite_globale     |        0.0559 |         0.1110 |       0.0603 |      0.0344 |
| popularite_recente     |        0.0532 |         0.1153 |       0.0625 |      0.0354 |

### Actifs vs peu actifs (fenêtres 1-3, seuil = médiane du nombre d'achats train par fenêtre)

|                                         |   recall_at_5 |   recall_at_10 |   ndcg_at_10 |   map_at_10 |
|:----------------------------------------|--------------:|---------------:|-------------:|------------:|
| ('collaboratif_item_item', 'actif')     |        0.0328 |         0.0641 |       0.0395 |      0.0207 |
| ('collaboratif_item_item', 'peu_actif') |        0.0309 |         0.0594 |       0.0357 |      0.0185 |
| ('contenu_categorie_prix', 'actif')     |        0.0185 |         0.0384 |       0.0229 |      0.0115 |
| ('contenu_categorie_prix', 'peu_actif') |        0.0187 |         0.0398 |       0.0239 |      0.0119 |
| ('popularite_categorie', 'actif')       |        0.0286 |         0.0495 |       0.0314 |      0.0167 |
| ('popularite_categorie', 'peu_actif')   |        0.0263 |         0.0471 |       0.0300 |      0.0160 |
| ('popularite_globale', 'actif')         |        0.0365 |         0.0666 |       0.0403 |      0.0208 |
| ('popularite_globale', 'peu_actif')     |        0.0319 |         0.0619 |       0.0372 |      0.0191 |
| ('popularite_recente', 'actif')         |        0.0312 |         0.0605 |       0.0365 |      0.0187 |
| ('popularite_recente', 'peu_actif')     |        0.0327 |         0.0640 |       0.0390 |      0.0207 |

## 5. Schéma de sortie

Colonnes : `client_id, recommended_product_id, rank, score, model_used, fallback_reason, recommendation_date, already_purchased, eligible_at_recommendation_date, window, requested_model, exclude_purchased_policy, filter_stock_policy, policy_combo`

**Lignes matérialisées (politique par défaut uniquement — achats déjà faits exclus, stock filtré) : 862,300.** Les 2 autres politiques comparées au §3 (`inclut_produits_deja_achetes`, `sans_filtre_stock`) ont bien été **entièrement évaluées** — leurs métriques agrégées (Recall/Precision/NDCG/MAP/couverture) ci-dessus sont réelles, calculées sur les recommandations complètes générées pour ces politiques — mais leurs sorties ligne-à-ligne (`client_id`, `recommended_product_id`, ...) n'ont pas été conservées sur disque, pour limiter la mémoire (chaque politique complète pèse ~860 000 lignes). Si le détail ligne-à-ligne d'une de ces 2 politiques est nécessaire, relancer `run_window_evaluation(..., keep_output_rows=True)` pour la politique voulue.

## 6. Ce qui n'a pas été construit (arrêt volontaire)

- **Aucun modèle hybride** : la consigne est de ne le construire que s'il bat réellement les baselines, ce qui suppose de d'abord les avoir. C'est fait ici — le hybride reste à faire dans un tour suivant.
- **Aucune règle « achetés ensemble »** (`order_id` absent).
- **Aucune recommandation séquentielle** (`session_id`/`event_timestamp` absents).
- Aucune publication Supabase, aucun déploiement.
