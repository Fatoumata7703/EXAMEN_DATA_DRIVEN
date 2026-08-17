# 10 — Pricing au niveau campagne

Statut : audit et baselines bornées, sans push ni écriture Supabase.

- Campagnes réelles indépendantes : **120** ; épisodes produit×campagne : **2406** ; épisodes sans chevauchement : **2003** ; épisodes en chevauchement : **403**.
- Produit×semaine : **23700** lignes ; produit×jour historique secondaire : WAPE **0,4164**.
- Les features sont calculées strictement avant le début de campagne ; la période post-campagne est descriptive uniquement.
- Une campagne réelle ne traverse jamais train/test : les fenêtres sont définies par campagne entière.

## Métriques produit×campagne et produit×semaine

| grain            |   window | model                       |    n |   wape_volume_campagne |   forecast_bias |   actual_total |   pred_total |
|:-----------------|---------:|:----------------------------|-----:|-----------------------:|----------------:|---------------:|-------------:|
| produit×campagne |        1 | baseline_historique_produit |  801 |                 1.7267 |          0.9357 |      5702.0000 |   11037.6071 |
| produit×campagne |        1 | moyenne_comparable          |  801 |                 1.3979 |          0.9357 |      5702.0000 |   11037.6071 |
| produit×campagne |        1 | glm_poisson                 |  801 |                 1.7267 |          0.9357 |      5702.0000 |   11037.6071 |
| produit×campagne |        2 | baseline_historique_produit |  569 |                 1.2341 |          0.5602 |      5612.0000 |    8755.6429 |
| produit×campagne |        2 | moyenne_comparable          |  569 |                 0.6433 |         -0.3687 |      5612.0000 |    3542.9167 |
| produit×campagne |        2 | glm_poisson                 |  569 |                 1.2341 |          0.5602 |      5612.0000 |    8755.6429 |
| produit×campagne |        3 | baseline_historique_produit |  633 |                 0.9849 |          0.2659 |      8127.0000 |   10287.8929 |
| produit×campagne |        3 | moyenne_comparable          |  633 |                 0.6343 |         -0.3756 |      8127.0000 |    5074.1476 |
| produit×campagne |        3 | glm_poisson                 |  633 |                 0.9849 |          0.2659 |      8127.0000 |   10287.8929 |
| produit×semaine  |        1 | moving_average_4_weeks      | 8100 |                 0.5253 |         -0.0871 |     32494.0000 |   29665.0833 |
| produit×semaine  |        2 | moving_average_4_weeks      | 7800 |                 0.4625 |         -0.0315 |     55019.0000 |   53283.7500 |
| produit×semaine  |        3 | moving_average_4_weeks      | 7800 |                 0.4997 |         -0.0005 |     59521.0000 |   59491.2500 |

WAPE campagne macro (moyenne des fenêtres, baseline historique) : **1.3152**. WAPE campagne micro poolée (erreurs pondérées par volume réel) : **1.2744**. Ces agrégations sont distinctes.

Le seuil utile <0,30 n'est pas atteint. Les 120 campagnes indépendantes et les chevauchements rendent une optimisation ML plus ambitieuse prématurée ; GLM/pooling restent prioritaires. LightGBM Tweedie/Poisson/L1, CatBoost, hurdle, hiérarchique et ensemble contraint sont explicitement **non lancés** (gate de suffisance des campagnes indépendantes non franchi), sans présenter leur absence comme un résultat favorable.

## Support et garde-fous

- Les 7 niveaux de remise observés sont publiés dans les métadonnées ; la remise à 40 % n'est recommandable que si son support est suffisant.
- Les produits sans support individuel sont affectés au pooling catégorie ; sinon `insufficient_evidence`.
- Aucun effet causal, aucune élasticité continue, aucune extrapolation et aucune application automatique ne sont autorisés.

## Artifacts

Datasets : `pricing_product_campaign.parquet`, `pricing_product_week.parquet`, `pricing_product_day_reference.parquet`. Métriques et SHA-256 : `models/campaign_level_pricing/`.