# 41 — Recommandation V1 : consolidation finale avant archivage

_Généré le 2026-08-14T21:30:11.805955+00:00. Verdict accepté : aucun modèle personnalisé retenu, aucun hybride construit. Ce document consolide la décision de baseline et réconcilie le plafond de Recall avant archivage._

## 1. Tableau complet par modèle et par fenêtre (politique par défaut)

|   fenetre | modele                 |   recall_at_5 |   recall_at_10 |   precision_at_5 |   precision_at_10 |   ndcg_at_5 |   ndcg_at_10 |   map_at_10 |   user_coverage |   catalog_coverage |   diversity_at_10 |
|----------:|:-----------------------|--------------:|---------------:|-----------------:|------------------:|------------:|-------------:|------------:|----------------:|-------------------:|------------------:|
|         0 | collaboratif_item_item |        0.0302 |         0.0709 |           0.0113 |            0.0125 |      0.0219 |       0.0368 |      0.0204 |          1.0000 |             0.5100 |            0.5167 |
|         1 | collaboratif_item_item |        0.0329 |         0.0611 |           0.0157 |            0.0147 |      0.0255 |       0.0371 |      0.0199 |          1.0000 |             0.3067 |            0.3625 |
|         2 | collaboratif_item_item |        0.0340 |         0.0682 |           0.0177 |            0.0177 |      0.0277 |       0.0417 |      0.0217 |          1.0000 |             0.2300 |            0.3492 |
|         3 | collaboratif_item_item |        0.0288 |         0.0562 |           0.0152 |            0.0148 |      0.0230 |       0.0343 |      0.0174 |          1.0000 |             0.1467 |            0.3411 |
|         0 | contenu_categorie_prix |        0.0331 |         0.0711 |           0.0125 |            0.0131 |      0.0231 |       0.0373 |      0.0203 |          1.0000 |             0.5100 |            0.1574 |
|         1 | contenu_categorie_prix |        0.0207 |         0.0435 |           0.0101 |            0.0103 |      0.0159 |       0.0249 |      0.0127 |          1.0000 |             0.7367 |            0.1692 |
|         2 | contenu_categorie_prix |        0.0181 |         0.0394 |           0.0102 |            0.0107 |      0.0148 |       0.0236 |      0.0114 |          1.0000 |             0.7800 |            0.1713 |
|         3 | contenu_categorie_prix |        0.0169 |         0.0342 |           0.0098 |            0.0095 |      0.0144 |       0.0215 |      0.0108 |          1.0000 |             0.7200 |            0.1799 |
|         0 | popularite_categorie   |        0.0488 |         0.0850 |           0.0174 |            0.0151 |      0.0346 |       0.0478 |      0.0286 |          1.0000 |             0.3400 |            0.1382 |
|         1 | popularite_categorie   |        0.0273 |         0.0476 |           0.0136 |            0.0120 |      0.0217 |       0.0301 |      0.0164 |          1.0000 |             0.4000 |            0.1000 |
|         2 | popularite_categorie   |        0.0293 |         0.0510 |           0.0150 |            0.0133 |      0.0231 |       0.0320 |      0.0167 |          1.0000 |             0.4167 |            0.1000 |
|         3 | popularite_categorie   |        0.0262 |         0.0469 |           0.0134 |            0.0126 |      0.0215 |       0.0303 |      0.0161 |          1.0000 |             0.4267 |            0.1000 |
|         0 | popularite_globale     |        0.0580 |         0.1098 |           0.0212 |            0.0202 |      0.0407 |       0.0599 |      0.0342 |          1.0000 |             0.0433 |            0.3177 |
|         1 | popularite_globale     |        0.0358 |         0.0658 |           0.0167 |            0.0158 |      0.0269 |       0.0392 |      0.0208 |          1.0000 |             0.0567 |            0.3545 |
|         2 | popularite_globale     |        0.0363 |         0.0683 |           0.0185 |            0.0175 |      0.0275 |       0.0406 |      0.0206 |          1.0000 |             0.0567 |            0.3551 |
|         3 | popularite_globale     |        0.0310 |         0.0596 |           0.0166 |            0.0159 |      0.0248 |       0.0366 |      0.0186 |          1.0000 |             0.0600 |            0.3059 |
|         0 | popularite_recente     |        0.0545 |         0.1131 |           0.0201 |            0.0206 |      0.0392 |       0.0610 |      0.0346 |          1.0000 |             0.0433 |            0.3001 |
|         1 | popularite_recente     |        0.0359 |         0.0670 |           0.0170 |            0.0159 |      0.0271 |       0.0395 |      0.0209 |          1.0000 |             0.0533 |            0.2916 |
|         2 | popularite_recente     |        0.0303 |         0.0625 |           0.0164 |            0.0165 |      0.0250 |       0.0382 |      0.0193 |          1.0000 |             0.0500 |            0.3857 |
|         3 | popularite_recente     |        0.0295 |         0.0569 |           0.0152 |            0.0147 |      0.0238 |       0.0352 |      0.0185 |          1.0000 |             0.0600 |            0.2996 |

**Agrégat global (moyenne des 4 fenêtres), trié par NDCG@10 :**

| modele                 |   recall_at_5 |   recall_at_10 |   precision_at_5 |   precision_at_10 |   ndcg_at_5 |   ndcg_at_10 |   map_at_10 |   user_coverage |   catalog_coverage |   diversity_at_10 |
|:-----------------------|--------------:|---------------:|-----------------:|------------------:|------------:|-------------:|------------:|----------------:|-------------------:|------------------:|
| popularite_globale     |        0.0403 |         0.0759 |           0.0183 |            0.0174 |      0.0300 |       0.0441 |      0.0235 |          1.0000 |             0.0542 |            0.3333 |
| popularite_recente     |        0.0375 |         0.0749 |           0.0172 |            0.0169 |      0.0288 |       0.0435 |      0.0233 |          1.0000 |             0.0517 |            0.3192 |
| collaboratif_item_item |        0.0315 |         0.0641 |           0.0149 |            0.0149 |      0.0245 |       0.0375 |      0.0199 |          1.0000 |             0.2983 |            0.3924 |
| popularite_categorie   |        0.0329 |         0.0576 |           0.0148 |            0.0132 |      0.0252 |       0.0351 |      0.0194 |          1.0000 |             0.3958 |            0.1096 |
| contenu_categorie_prix |        0.0222 |         0.0471 |           0.0106 |            0.0109 |      0.0170 |       0.0268 |      0.0138 |          1.0000 |             0.6867 |            0.1695 |

## 2. Sélection objective de la baseline principale

Règle fixée avant lecture des résultats détaillés : priorité à NDCG@10 (puis Recall@10) moyen, puis stabilité inter-fenêtres, puis couverture catalogue, puis biais envers les produits déjà populaires.

| critere                                                                    |   popularite_globale |   popularite_recente | gagnant                 |
|:---------------------------------------------------------------------------|---------------------:|---------------------:|:------------------------|
| NDCG@10 moyen (priorité 1)                                                 |               0.0441 |               0.0435 | globale                 |
| Recall@10 moyen (priorité 1 bis)                                           |               0.0759 |               0.0749 | globale                 |
| Écart-type NDCG@10 (stabilité, plus bas = mieux)                           |               0.0107 |               0.0118 | globale                 |
| Écart-type Recall@10 (stabilité)                                           |               0.0229 |               0.0258 | globale                 |
| Couverture catalogue moyenne                                               |               0.0542 |               0.0517 | globale                 |
| Popularité moyenne des recommandations (biais, plus bas = moins concentré) |               0.9091 |               0.7220 | récente (moins biaisée) |

**Constat** : l'écart sur le critère prioritaire (NDCG@10 moyen) est de 1.5% relatif seulement — **aucune des deux méthodes ne domine clairement**. `popularite_globale` gagne néanmoins 4 des 5 premiers critères (NDCG@10, Recall@10, stabilité×2, couverture), tandis que `popularite_recente` est nettement moins concentrée sur les produits déjà populaires (popularité moyenne des recommandations 0.72 contre 0.91 pour `popularite_globale`, soit -21% relatif) — un vrai avantage pour la diversité perçue, mais qui ne suffit pas à renverser la règle fixée à l'avance (le biais est le dernier critère, pas le premier).

### Décision (règle appliquée mécaniquement, aucune méthode ne dominant clairement)

- **Principale : `popularite_globale`** (meilleure métrique prioritaire moyenne).
- **Secours : `popularite_recente`**.
- **Cold-start : `popularite_globale`** (imposé, indépendamment du résultat ci-dessus).
- **Personnalisation : désactivée** (aucun modèle personnalisé ne bat clairement les baselines, cf. rapport 40).

## 3. Réconciliation exacte du plafond de Recall — une raison par cible exclue

|   fenetre |   n_cibles_totales |   deja_achete_exclu_volontairement |   stock_j1_reellement_nul |   produit_non_encore_disponible |   produit_absent_table_produit |   autre |   n_cibles_exclues_total |
|----------:|-------------------:|-----------------------------------:|--------------------------:|--------------------------------:|-------------------------------:|--------:|-------------------------:|
|         0 |               6999 |                                 85 |                         0 |                             641 |                              0 |       0 |                      726 |
|         1 |              10521 |                                476 |                         0 |                             521 |                              0 |       0 |                      997 |
|         2 |              11926 |                                566 |                         0 |                             384 |                              0 |       0 |                      950 |
|         3 |              11922 |                                687 |                         0 |                             268 |                              0 |       0 |                      955 |

**⚠️ Rappel impératif** : l'audit stock antérieur avait établi que le niveau de stock ne descend **jamais** sous 21 unités dans cette livraison — reconfirmé ici (`min=21` sur 117 763 enregistrements, 0 valeur ≤0). **`stock_j1_reellement_nul` vaut donc 0 sur les 4 fenêtres : aucune exclusion n'est due à une rupture réelle.** La quasi-totalité des exclusions liées au stock (641→521→384→268 selon la fenêtre) vient d'une **absence d'enregistrement de stock avant le cutoff** (produit pas encore suivi/lancé), catégorisée séparément sous `produit_non_encore_disponible` — **jamais appelée « rupture »**. Les exclusions pour rachat volontaire (`deja_achete_exclu_volontairement`) croissent avec l'historique accumulé (85→687), logique. `produit_absent_table_produit` et `autre` valent 0 partout — traçabilité complète, aucune exclusion inexpliquée.

**Exemples anonymisés** (identifiants produits synthétiques, aucune donnée personnelle) :

|   fenetre | produit   | raison                        |
|----------:|:----------|:------------------------------|
|         0 | PRD000187 | produit_non_encore_disponible |
|         0 | PRD000204 | produit_non_encore_disponible |
|         0 | PRD000278 | produit_non_encore_disponible |
|         0 | PRD000213 | produit_non_encore_disponible |
|         0 | PRD000236 | produit_non_encore_disponible |
|         0 | PRD000148 | produit_non_encore_disponible |
|         0 | PRD000236 | produit_non_encore_disponible |
|         0 | PRD000278 | produit_non_encore_disponible |

## 4. Métriques end-to-end (toutes cibles) vs ranking sur cibles éligibles seules

**Ne jamais mélanger ces deux périmètres** — présentés ici strictement séparés, pour la baseline retenue :

|   fenetre | perimetre                       |   recall_at_10 |   ndcg_at_10 |   map_at_10 |   taux_cibles_eligibles |
|----------:|:--------------------------------|---------------:|-------------:|------------:|------------------------:|
|         0 | end_to_end_toutes_cibles        |         0.1098 |       0.0599 |      0.0342 |                  0.8963 |
|         0 | ranking_cibles_eligibles_seules |         0.1241 |       0.0667 |      0.0391 |                  0.8963 |
|         1 | end_to_end_toutes_cibles        |         0.0658 |       0.0392 |      0.0208 |                  0.9052 |
|         1 | ranking_cibles_eligibles_seules |         0.0737 |       0.0427 |      0.0232 |                  0.9052 |
|         2 | end_to_end_toutes_cibles        |         0.0683 |       0.0406 |      0.0206 |                  0.9203 |
|         2 | ranking_cibles_eligibles_seules |         0.0744 |       0.0433 |      0.0223 |                  0.9203 |
|         3 | end_to_end_toutes_cibles        |         0.0596 |       0.0366 |      0.0186 |                  0.9199 |
|         3 | ranking_cibles_eligibles_seules |         0.0658 |       0.0393 |      0.0203 |                  0.9199 |

**Lecture** : les métriques « cibles éligibles seules » sont mécaniquement plus hautes (le plafond structurel du §3 est retiré du calcul) — c'est la mesure de la qualité pure du classement, indépendante de la couverture des candidats. Les métriques « end-to-end » (rapports 37/40) restent la référence pour évaluer le système complet tel qu'il serait réellement utilisé.

## 5. Scénarios de réachat — découverte vs réapprovisionnement

|   fenetre |   n_cibles_totales |   n_cibles_qui_sont_des_rachats |   pct_cibles_rachats |
|----------:|-------------------:|--------------------------------:|---------------------:|
|    0.0000 |          6999.0000 |                         85.0000 |               0.0121 |
|    1.0000 |         10521.0000 |                        476.0000 |               0.0452 |
|    2.0000 |         11926.0000 |                        566.0000 |               0.0475 |
|    3.0000 |         11922.0000 |                        687.0000 |               0.0576 |

**Comparaison des deux politiques** (déjà mesurée au rapport 37 §3a, rappelée ici) : `inclut_produits_deja_achetes` (scénario réapprovisionnement) obtient une couverture de cibles de 95,1 % à 97,8 % contre 89,6 %-92,0 % pour `defaut_exclut_achats_stock_filtre` (scénario découverte) — confirmé : **l'exclusion systématique des rachats pénalise mécaniquement le Recall**, de façon croissante dans le temps (1,2 % des cibles à la fenêtre 0, jusqu'à 5,8 % à la fenêtre 3, sont des rachats). **Choix métier à trancher explicitement selon l'usage** : scénario découverte (exclusion) pour une recommandation d'exploration du catalogue, scénario réapprovisionnement (autorisation) pour des produits de consommation courante rachetés naturellement — ce projet ne tranche pas ce choix à la place du métier, il documente l'impact mesuré de chaque option.
