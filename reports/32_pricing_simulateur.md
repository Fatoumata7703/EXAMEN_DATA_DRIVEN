# 32 — Simulateur de remises (V1 exploratoire) — simulations, pas des recommandations automatiques

_Généré le 2026-08-14T16:05:06.671389+00:00. **Méthode retenue pour le simulateur exploratoire : `challenger_ml_lightgbm`** (voir rapport 33 pour la règle de sélection et sa justification). Toute sortie de ce simulateur est une **simulation de scénario**, pas une recommandation à appliquer automatiquement : `automatic_application_allowed=false`, `causal_effect_estimated=false`, `human_validation_required=true`, `off_policy_evaluation_validated=false` sur chaque ligne. Bande d'incertitude (`quantite_prevue_bande_incertitude_*`) : bande multiplicative ±WAPE poolée de la méthode (107.1%) — **ce n'est pas un intervalle de confiance statistique** (`scenario_uncertainty_band`, pas `confidence_interval`), simplification documentée au registre V2 (intervalle conforme par segment)._

- Simulations avec sortie exploitable : **2008**
- Statuts `insufficient_evidence` : **20**

## Distribution exacte des remises simulées (scénario marge, plancher 5 %)

|   suggested_discount_exploratory |   n_produits |
|---------------------------------:|-------------:|
|                                0 |          240 |
|                                5 |           29 |
|                               10 |           17 |
|                               15 |            2 |
|                               20 |            0 |
|                               25 |            0 |
|                               30 |            0 |
|                               40 |            0 |

_(la moyenne seule — 1.20 % — n'est pas informative seule ; distribution complète ci-dessus)_

## Par catégorie

| categorie                |   0.0 |   5.0 |   10.0 |   15.0 |
|:-------------------------|------:|------:|-------:|-------:|
| Alimentation & Epicerie  |    38 |     1 |      0 |      0 |
| Beaute & Soins           |    28 |     6 |      3 |      2 |
| Bebe & Enfant            |    32 |     5 |      1 |      0 |
| Electronique & High-Tech |    33 |     6 |      0 |      0 |
| Maison & Cuisine         |    26 |     2 |      4 |      0 |
| Mode & Vetements         |    20 |     5 |      9 |      0 |
| Sport & Loisirs          |    28 |     1 |      0 |      0 |
| Telephonie & Accessoires |    35 |     3 |      0 |      0 |

## Par niveau de confiance

| niveau_confiance   |   0.0 |   5.0 |   10.0 |   15.0 |
|:-------------------|------:|------:|-------:|-------:|
| faible             |    61 |     3 |      3 |      0 |
| moyenne            |   179 |    26 |     14 |      2 |

## Éligible individuel vs pooling catégorie

| groupe_eligibilite         |   0.0 |   5.0 |   10.0 |   15.0 |
|:---------------------------|------:|------:|-------:|-------:|
| eligible_individuel        |   179 |    23 |     14 |      2 |
| eligible_pooling_categorie |    61 |     6 |      3 |      0 |

## Vérification support

- Simulations avec remise >0 % non supportée directement par l'historique du produit (repli catégorie) : **14** — signalées via `support_historique=false` et un avertissement explicite sur chaque ligne concernée, jamais présentées comme équivalentes à une simulation directement supportée.
- Aucune remise simulée ne dépasse la grille observée (garde-fou vérifié par assertion dans le code, 0 dépassement possible par construction).

## Sensibilité à la marge minimale (objectif = marge)

|   marge_minimale |   n_simulations |   remise_moyenne |   marge_prevue_totale |   delta_marge_vs_actuel_moyen |
|-----------------:|----------------:|-----------------:|----------------------:|------------------------------:|
|             0.00 |          288.00 |             1.20 |            6800436.29 |                       -650.44 |
|             0.05 |          288.00 |             1.20 |            6800436.29 |                       -650.44 |
|             0.10 |          288.00 |             1.20 |            6800436.29 |                       -650.44 |
|             0.15 |          280.00 |             1.21 |            6790524.81 |                       -675.26 |

## Par objectif (marge minimale par défaut, 5 %)

| objectif               |      n |   remise_moyenne |   ca_prevu_total |   marge_prevue_totale |
|:-----------------------|-------:|-----------------:|-----------------:|----------------------:|
| chiffre_affaires       | 288.00 |            11.09 |      30773147.77 |            5012503.48 |
| compromis_marge_volume | 288.00 |             6.44 |      28740835.14 |            6134487.91 |
| ecoulement_stock       | 288.00 |            19.51 |      29879281.40 |            3423070.97 |
| marge                  | 288.00 |             1.20 |      27291577.98 |            6800436.29 |

## Niveau de confiance — règle documentée

`haute` exige : produit éligible individuellement **ET** remise simulée supportée par son propre historique **ET** recommandation stable entre les 3 fenêtres de validation **ET** WAPE_quantite(méthode) < 50%. Ce dernier plafond est **structurellement non atteint** dans cette V1 (WAPE_quantite = 107.1%) — **aucune ligne ne peut donc être `haute` tant que la précision du modèle ne s'améliore pas**, quel que soit le support ou la stabilité observés. `moyenne` et `faible` restent différenciés par le support et l'éligibilité.

| niveau_confiance   |   n |
|:-------------------|----:|
| moyenne            | 221 |
| faible             |  67 |

## Produits non éligibles — aucune fausse simulation

**12** produits n'ont reçu aucune ligne de simulation (statut `insufficient_evidence` systématique, raison exacte dans la colonne `raison_eligibilite` du fichier `reports/pricing_final/simulateur_sorties.csv`).
