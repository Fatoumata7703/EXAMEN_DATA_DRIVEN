# 02 — Forecasting final

**Modèle retenu : `CrostonOptimized`** (robustesse multi-fenêtres).

| model            |    wape |       std |   wins |       bias |   wape30 |
|:-----------------|--------:|----------:|-------:|-----------:|---------:|
| CrostonOptimized | 1.07648 | 0.0220781 |      3 | -0.0756496 | 0.349654 |
| MovingAverage28  | 1.08829 | 0.0179321 |      0 | -0.0221842 | 0.310189 |
| LightGBM_Tweedie | 1.09341 | 0.0217574 |      0 | -0.020288  | 0.300575 |
| Hurdle_LightGBM  | 1.09559 | 0.0219268 |      0 | -0.0139218 | 0.301855 |
| LightGBM_Poisson | 1.10606 | 0.0237088 |      0 |  0.0144793 | 0.3046   |
| TSB              | 1.11357 | 0.0227926 |      0 | -0.0103702 | 0.410258 |
| AutoETS          | 1.2001  | 0.0471622 |      0 |  0.0529071 | 0.586084 |
| Naive            | 1.2956  | 0.0781593 |      0 | -0.0843838 | 1.03947  |
| SeasonalNaive7   | 1.33351 | 0.0387168 |      0 | -0.0124423 | 0.480311 |

Validation glissante: 3 fenêtres communes de 30 jours; cible = quantité confirmée produit-jour.

Intervalles 80/95 % : calibration conforme à produire sur les résidus du modèle retenu avant usage opérationnel; aucun intervalle non calibré n’est présenté comme valide.

Cold-start/historique insuffisant : repli explicite Seasonal Naive puis moyenne globale; aucun NaN silencieux.

Commande: `python -m src.pipelines.final_forecasting`.
