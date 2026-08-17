# E-commerce — Forecasting, Pricing et Recommandation

Livraison finale reconstruite à partir d'une extraction Supabase fraîche, contrôlée et strictement en lecture seule. Les données brutes et analytiques restent locales et sont exclues de Git. Aucun modèle n'est déployé et aucune décision n'est appliquée automatiquement.

## Résultats validés

| Domaine | Sélection finale | Validation temporelle | Résultat principal | Usage autorisé |
|---|---|---|---|---|
| Forecasting | `CrostonOptimized` | 3 fenêtres glissantes communes de 30 jours | WAPE quotidienne 1,0765; WAPE cumulée 30 j 0,3497 | Planification avec validation humaine |
| Pricing | `LightGBM_calibre` | 3 fenêtres temporelles | WAPE 0,4167; biais -0,0009 | Simulation observationnelle de remises |
| Recommandation | `hybride_achats_web` | 3 fenêtres temporelles, découverte et réapprovisionnement | NDCG@10 découverte 0,0372; couverture 18,67 % | Classement assisté, non automatisé |

Ces métriques mesurent des tâches différentes et ne doivent pas être comparées entre domaines. Les scores de recommandation restent faibles en absolu; le modèle hybride n'est retenu que pour son NDCG moyen légèrement supérieur et sa couverture plus large que la popularité globale.

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

- Forecasting : aucun pilotage automatique; les intervalles 80/95 % du modèle reconstruit doivent encore être calibrés avant usage opérationnel. Les modèles LightGBM restent des challengers utiles pour le cumul 30 jours.
- Pricing : prix jamais inférieur au coût, marge minimale configurable (5 % par défaut), remise limitée au support historique, validation humaine obligatoire. Le résultat est associatif, pas causal.
- Recommandation : achats confirmés comme cibles, signaux web antérieurs seulement, `purchase` web exclu des poids hybrides, aucune identité client fictive. Les performances sessionnelles sont quasi nulles et interdisent un usage séquentiel en production.

## Artefacts et rapports

- Audit des données : [`reports/final/01_data_audit.md`](reports/final/01_data_audit.md)
- Forecasting : [`reports/final/02_forecasting.md`](reports/final/02_forecasting.md), `models/forecasting/`
- Pricing : [`reports/final/03_pricing.md`](reports/final/03_pricing.md), `models/pricing/`
- Recommandation : [`reports/final/04_recommendation.md`](reports/final/04_recommendation.md), `models/recommendation/`
- Synthèse exécutive : [`reports/final/05_executive_summary.md`](reports/final/05_executive_summary.md)

Chaque répertoire de modèles contient des métadonnées et un manifeste SHA-256. Les anciens rapports V1 restent versionnés pour traçabilité, mais cette livraison finale dans `reports/final` et `models/{forecasting,pricing,recommendation}` constitue la référence courante.

## Statut de livraison

Branche : `rebuild/final-enriched-dataset`. Aucun merge vers `main`, aucun déploiement et aucune écriture dans Supabase ne font partie de cette livraison.
