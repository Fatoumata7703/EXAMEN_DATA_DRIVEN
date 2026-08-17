# E-commerce — Forecasting, Pricing et Recommandation

Livraison finale reconstruite à partir d'une extraction Supabase fraîche, contrôlée et strictement en lecture seule. Les données brutes et analytiques restent locales et sont exclues de Git. Aucun modèle n'est déployé et aucune décision n'est appliquée automatiquement.

## Résultats validés

| Domaine | Sélection finale | Validation temporelle | Résultat principal | Usage autorisé |
|---|---|---|---|---|
| Forecasting quotidien | `CrostonOptimized` | 6 fenêtres non chevauchantes de 30 jours | WAPE 1,0945; 4 victoires sur 6 | Prévision quotidienne supervisée |
| Forecasting cumulé 30 j | `LightGBM_Tweedie` | mêmes 6 fenêtres | WAPE cumulée 0,3106 | Planification agrégée supervisée |
| Pricing | `LightGBM_calibre` | 3 fenêtres temporelles, calibration antérieure séparée | WAPE 0,4164; biais -0,0035 | Simulation observationnelle de remises |
| Recommandation | baseline `popularite_globale`; hybride `challenger_exploratoire` | 3 fenêtres, bootstrap client-fenêtre | ΔNDCG hybride +0,00095, IC95 % contenant zéro | Baseline contrôlée; hybride en expérimentation seulement |

Ces métriques mesurent des tâches différentes et ne doivent pas être comparées entre domaines. Aucun modèle forecasting n'est déclaré vainqueur global. Le gain de l'hybride de recommandation n'est pas statistiquement établi.

## Données finales

L'audit a réconcilié 84 319 lignes de vente, 49 872 commandes, 657 392 événements web uniques et 117 763 observations de stock. Les cinq datasets reconstruits sont :

- `product_daily_forecasting` : 163 800 lignes;
- `product_day_discount_pricing` : 55 586 lignes;
- `order_baskets` : 80 130 lignes, commandes confirmées uniquement;
- `session_sequences` : 622 440 événements humains;
- `client_product_interactions` : 622 440 interactions.

Les bots sont exclus, les visiteurs anonymes restent anonymes, les achats web sont rattachés aux commandes réelles et ne sont jamais additionnés aux ventes. Les prix catalogue sont fixes pour les 300 produits : le pricing ne peut donc pas être présenté comme causal ni comme un optimum continu.

## Reproduction

Prérequis : Python 3.11+ et un `.env` local configuré avec un accès Supabase en lecture seule.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Extraction locale fraîche puis construction/audit
python -m src.pipelines.extract
python -m src.pipelines.final_build_datasets

# Entraînements séquentiels — ne pas les lancer en parallèle
python -m src.pipelines.final_forecasting
python -m src.pipelines.final_pricing
python -m src.pipelines.final_recommendation

# Validation
python -m pytest -q
```

Le fichier `.env` est exclu par `.gitignore`. Ne jamais l'afficher, le journaliser ou le committer. Les répertoires `data/raw`, `data/cache`, `data/processed`, `checkpoints` et `logs` ne sont pas versionnés.

## Garde-fous métier

- Forecasting : aucun pilotage automatique; intervalles conformes 80/95 % calibrés uniquement sur des résidus antérieurs. Croston sert le quotidien, LightGBM Tweedie le cumul 30 jours.
- Pricing : prix jamais inférieur au coût, marge minimale configurable (5 % par défaut), remise limitée au support historique, validation humaine obligatoire. Le résultat est associatif, pas causal.
- Recommandation : popularité globale comme baseline officielle; hybride exploratoire uniquement. Le système panier reste séparé. Le scénario sessionnel est déclaré non utilisable.

## Artefacts et rapports

- Audit des données : [`reports/final/01_data_audit.md`](reports/final/01_data_audit.md)
- Forecasting : [`reports/final/02_forecasting.md`](reports/final/02_forecasting.md), `models/forecasting/`
- Pricing : [`reports/final/03_pricing.md`](reports/final/03_pricing.md), `models/pricing/`
- Recommandation : [`reports/final/04_recommendation.md`](reports/final/04_recommendation.md), `models/recommendation/`
- Synthèse exécutive : [`reports/final/05_executive_summary.md`](reports/final/05_executive_summary.md)
- Addendum méthodologique : [`reports/final/06_methodology_addendum.md`](reports/final/06_methodology_addendum.md)
- Matrice des contrôles actifs : [`reports/final/07_active_test_matrix.md`](reports/final/07_active_test_matrix.md)

Chaque répertoire de modèles contient des métadonnées et un manifeste SHA-256. Les anciens rapports V1 restent versionnés pour traçabilité, mais cette livraison finale dans `reports/final` et `models/{forecasting,pricing,recommendation}` constitue la référence courante.

## Statut de livraison

Branche : `rebuild/final-enriched-dataset`. Aucun merge vers `main`, aucun déploiement et aucune écriture dans Supabase ne font partie de cette livraison.
