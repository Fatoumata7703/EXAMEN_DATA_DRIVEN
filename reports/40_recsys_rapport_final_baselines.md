# 40 — Recommandation V1 : rapport final baselines (aucun modèle sélectionné ni archivé)

_Généré le 2026-08-14T20:43:48.343032+00:00. Sources : rapport 36 (éligibilité), rapport 37 (résultats), rapport 39 (vérifications approfondies), `reports/38_recsys_log.jsonl` (journal détaillé), `data/interim/recsys_checkpoints/` (checkpoints). Forecasting V1 et Pricing V1 non touchés. Aucune écriture Supabase, aucun déploiement._

## Table complète : par modèle et par fenêtre (politique par défaut)

|   fenetre | train_end   | test_start   | test_end   | modele                 |   n_clients_evaluables |   recall_at_5 |   recall_at_10 |   precision_at_5 |   precision_at_10 |   ndcg_at_5 |   ndcg_at_10 |   map_at_10 |   user_coverage |   catalog_coverage |   duree_s |   n_fallback |
|----------:|:------------|:-------------|:-----------|:-----------------------|-----------------------:|--------------:|---------------:|-----------------:|------------------:|------------:|-------------:|------------:|----------------:|-------------------:|----------:|-------------:|
|         0 | 2025-05-01  | 2025-05-02   | 2025-06-30 | popularite_recente     |                   3781 |        0.0545 |         0.1131 |           0.0201 |            0.0206 |      0.0392 |       0.0610 |      0.0346 |          1.0000 |             0.0433 |    0.8300 |            0 |
|         0 | 2025-05-01  | 2025-05-02   | 2025-06-30 | popularite_globale     |                   3781 |        0.0580 |         0.1098 |           0.0212 |            0.0202 |      0.0407 |       0.0599 |      0.0342 |          1.0000 |             0.0433 |    0.8400 |            0 |
|         0 | 2025-05-01  | 2025-05-02   | 2025-06-30 | popularite_categorie   |                   3781 |        0.0488 |         0.0850 |           0.0174 |            0.0151 |      0.0346 |       0.0478 |      0.0286 |          1.0000 |             0.3400 |    0.9800 |            0 |
|         0 | 2025-05-01  | 2025-05-02   | 2025-06-30 | contenu_categorie_prix |                   3781 |        0.0331 |         0.0711 |           0.0125 |            0.0131 |      0.0231 |       0.0373 |      0.0203 |          1.0000 |             0.5100 |    1.1900 |            0 |
|         0 | 2025-05-01  | 2025-05-02   | 2025-06-30 | collaboratif_item_item |                   3781 |        0.0302 |         0.0709 |           0.0113 |            0.0125 |      0.0219 |       0.0368 |      0.0204 |          1.0000 |             0.5100 |    1.1500 |          717 |
|         1 | 2026-02-01  | 2026-02-02   | 2026-04-02 | popularite_recente     |                   4396 |        0.0359 |         0.0670 |           0.0170 |            0.0159 |      0.0271 |       0.0395 |      0.0209 |          1.0000 |             0.0533 |    1.2100 |            0 |
|         1 | 2026-02-01  | 2026-02-02   | 2026-04-02 | popularite_globale     |                   4396 |        0.0358 |         0.0658 |           0.0167 |            0.0158 |      0.0269 |       0.0392 |      0.0208 |          1.0000 |             0.0567 |    1.2600 |            0 |
|         1 | 2026-02-01  | 2026-02-02   | 2026-04-02 | collaboratif_item_item |                   4396 |        0.0329 |         0.0611 |           0.0157 |            0.0147 |      0.0255 |       0.0371 |      0.0199 |          1.0000 |             0.3067 |    1.7700 |            0 |
|         1 | 2026-02-01  | 2026-02-02   | 2026-04-02 | popularite_categorie   |                   4396 |        0.0273 |         0.0476 |           0.0136 |            0.0120 |      0.0217 |       0.0301 |      0.0164 |          1.0000 |             0.4000 |    1.4300 |            0 |
|         1 | 2026-02-01  | 2026-02-02   | 2026-04-02 | contenu_categorie_prix |                   4396 |        0.0207 |         0.0435 |           0.0101 |            0.0103 |      0.0159 |       0.0249 |      0.0127 |          1.0000 |             0.7367 |    1.8600 |            0 |
|         2 | 2026-04-02  | 2026-04-03   | 2026-06-01 | popularite_globale     |                   4531 |        0.0363 |         0.0683 |           0.0185 |            0.0175 |      0.0275 |       0.0406 |      0.0206 |          1.0000 |             0.0567 |    1.3000 |            0 |
|         2 | 2026-04-02  | 2026-04-03   | 2026-06-01 | collaboratif_item_item |                   4531 |        0.0340 |         0.0682 |           0.0177 |            0.0177 |      0.0277 |       0.0417 |      0.0217 |          1.0000 |             0.2300 |    2.1100 |            0 |
|         2 | 2026-04-02  | 2026-04-03   | 2026-06-01 | popularite_recente     |                   4531 |        0.0303 |         0.0625 |           0.0164 |            0.0165 |      0.0250 |       0.0382 |      0.0193 |          1.0000 |             0.0500 |    1.2400 |            0 |
|         2 | 2026-04-02  | 2026-04-03   | 2026-06-01 | popularite_categorie   |                   4531 |        0.0293 |         0.0510 |           0.0150 |            0.0133 |      0.0231 |       0.0320 |      0.0167 |          1.0000 |             0.4167 |    1.5000 |            0 |
|         2 | 2026-04-02  | 2026-04-03   | 2026-06-01 | contenu_categorie_prix |                   4531 |        0.0181 |         0.0394 |           0.0102 |            0.0107 |      0.0148 |       0.0236 |      0.0114 |          1.0000 |             0.7800 |    1.9700 |            0 |
|         3 | 2026-06-01  | 2026-06-02   | 2026-07-31 | popularite_globale     |                   4538 |        0.0310 |         0.0596 |           0.0166 |            0.0159 |      0.0248 |       0.0366 |      0.0186 |          1.0000 |             0.0600 |    1.3500 |            0 |
|         3 | 2026-06-01  | 2026-06-02   | 2026-07-31 | popularite_recente     |                   4538 |        0.0295 |         0.0569 |           0.0152 |            0.0147 |      0.0238 |       0.0352 |      0.0185 |          1.0000 |             0.0600 |    1.3000 |            0 |
|         3 | 2026-06-01  | 2026-06-02   | 2026-07-31 | collaboratif_item_item |                   4538 |        0.0288 |         0.0562 |           0.0152 |            0.0148 |      0.0230 |       0.0343 |      0.0174 |          1.0000 |             0.1467 |    1.9900 |            0 |
|         3 | 2026-06-01  | 2026-06-02   | 2026-07-31 | popularite_categorie   |                   4538 |        0.0262 |         0.0469 |           0.0134 |            0.0126 |      0.0215 |       0.0303 |      0.0161 |          1.0000 |             0.4267 |    1.4800 |            0 |
|         3 | 2026-06-01  | 2026-06-02   | 2026-07-31 | contenu_categorie_prix |                   4538 |        0.0169 |         0.0342 |           0.0098 |            0.0095 |      0.0144 |       0.0215 |      0.0108 |          1.0000 |             0.7200 |    2.1100 |            0 |

**Rappel du plafond structurel (rapport 39 §5)** : sous cette politique, 89,6 %-92,0 % seulement des cibles réelles étaient présentes dans l'ensemble de candidats — aucun Recall@K ne peut donc dépasser ~0,90-0,92 par construction, indépendamment de la qualité du modèle.

## Contrôles de non-fuite — résumé

| Contrôle | Résultat |
|---|---|
| Assertions train ≤ cutoff exécutées à chaque fenêtre×politique×modèle (60 combinaisons) | 0 échec |
| Erreurs client (capturées, non fatales) | 0 (`n_erreurs` = 0 sur les 60 lignes du journal) |
| Déterminisme (2 exécutions indépendantes de la fenêtre 1, politique par défaut) | Identique (`pd.testing.assert_frame_equal` sans écart) |
| Doublons dans un Top-K | 0 |
| Scores NaN/Inf | 0 |
| Taille exacte du Top-K (10 attendu) | min=max=10 sur 86 230 groupes |
| Rangs consécutifs sans trou | 100 % des groupes valides |
| `web_purchase` utilisé comme feature contemporaine | Jamais (exclu par construction, `ContentBased` ne lit que `view`/`add_to_cart`) |
| Régression du profil catégoriel (bug `groupby().apply()`) | Test dédié, exemple calculé à la main, 5/5 tests passent (`tests/test_recsys_content_model.py`) |

## Un modèle personnalisé bat-il clairement la popularité récente sur plusieurs fenêtres ?

Nombre de fenêtres (sur 4) où chaque modèle dépasse `popularite_recente` en Recall@10 :

| modele                 |   n_fenetres_ou_superieur_a_popularite_recente |
|:-----------------------|-----------------------------------------------:|
| collaboratif_item_item |                                              1 |
| contenu_categorie_prix |                                              0 |
| popularite_categorie   |                                              0 |
| popularite_globale     |                                              2 |

**Verdict honnête : aucun modèle personnalisé (filtrage collaboratif, contenu, popularité par catégorie) ne bat clairement `popularite_recente` sur plusieurs fenêtres.** Le filtrage collaboratif s'en approche ponctuellement (fenêtre 2 seulement) sans jamais dominer de façon répétée. **La baseline simple (`popularite_globale` ou `popularite_recente`, quasi interchangeables ici) reste donc, honnêtement, la référence V1** — conformément à la consigne de ne pas retenir un modèle personnalisé faute de gain réel et répété.

**Ce que cela signifie concrètement** : la personnalisation (savoir qui achète quoi individuellement) n'apporte pas encore de gain mesurable sur ce catalogue de 300 produits avec cette profondeur d'historique — un résultat cohérent avec le forecasting (WAPE quotidienne élevée) et le pricing (WAPE quantité élevée) : le signal individuel/fin reste difficile à exploiter sur ce jeu de données, à toutes les phases du projet.

## Ce qui n'a pas été fait (arrêt volontaire, comme demandé)

- **Aucun modèle hybride construit.**
- **Aucun modèle sélectionné ni archivé comme V1 définitive.**
- Forecasting V1 et Pricing V1 non modifiés.
- Aucune publication Supabase, aucun déploiement.

**Ce rapport s'arrête ici pour validation, avant tout entraînement supplémentaire ou archivage.**