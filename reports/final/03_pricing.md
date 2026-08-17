# 03 — Pricing final

**Méthode prédictive retenue : `LightGBM_calibre`.**

| model                    |     wape |        std |         bias |
|:-------------------------|---------:|-----------:|-------------:|
| LightGBM_calibre         | 0.416685 | 0.00558173 | -0.000853313 |
| GLM_Tweedie              | 0.42069  | 0.0026146  | -0.00399473  |
| GLM_Poisson              | 0.422112 | 0.00377692 | -0.00117186  |
| panel_effets_fixes       | 0.422987 | 0.00330845 | -0.00185623  |
| hierarchique_categorie   | 0.562723 | 0.00554344 |  0.0332832   |
| descriptif_intra_produit | 0.566061 | 0.00805962 |  0.0372165   |

## Verdict métier

Le prix catalogue reste fixe pour les 300 produits. Il est interdit de présenter ce résultat comme un prix optimal continu ou un effet causal. Le livrable est un simulateur observationnel de promotions et marge.

Garde-fous : prix jamais sous coût, marge minimale 5%, remise limitée au support historique, validation humaine obligatoire, application automatique interdite.

Commande : `python -m src.pipelines.final_pricing`.
