# 35 — Statut de clôture final : Forecasting V1 + Pricing V1 exploratoire

_Généré le 2026-08-14._

## Verdict final

| Composant | Statut |
|---|---|
| Forecasting cumulé 30 jours | Validé pour une V1 |
| Forecasting quotidien | À améliorer en V2 |
| Analyse promotions/marges | Validée |
| Simulateur de remises | Validé comme outil exploratoire |
| Recommandations automatiques | Non validées |
| Prix optimal causal | Impossible avec les données actuelles |

## Forecasting V1 — sauvegardé

- Modèle : `AutoETS avec repli Naive` — WAPE cumulée 30j = 0,2772, WAPE quotidienne ≈109 % (objectif V2).
- Modèle : `models/forecast_final/metadata.json` (`model_version: forecasting_v1`)
- Prévisions : `reports/forecast_final/previsions_finales.parquet` / `.csv`
- Snapshot de métriques : `reports/forecast_final/v1_metrics_snapshot.json`
- Manifeste SHA-256 : `reports/forecast_final/v1_manifest.json`
- Vérifications finales : `reports/forecast_final/v1_final_checks.json` — tous les contrôles passent
- Registre V2 : `reports/forecast_final/forecasting_v2_objectives.md`
- Rapports : `reports/15_*.md` à `reports/25_*.md`

## Pricing V1 exploratoire — sauvegardé

**Je valide le prototype comme Pricing V1 exploratoire, avec garde-fous, mais pas comme moteur de prix
optimal prêt pour la production.**

- Modèle retenu pour le simulateur exploratoire : `challenger_ml_lightgbm` — biais quantité +0,0100
  (quasi nul), **WAPE quantité 1,0713 (107,1 %) : estimations individuelles incertaines**.
- Métadonnées : `reports/pricing_final/metadata.json` (`pricing_version: pricing_v1_exploratory`,
  `causal: false`, `optimal_price_claim_allowed: false`, `automatic_application_allowed: false`,
  `human_validation_required: true`, `off_policy_evaluation_validated: false`)
- Dataset pricing : `data/processed/table_pricing.parquet`
- Sorties du simulateur : `reports/pricing_final/simulateur_sorties.csv` (2008 simulations exploitables,
  20 `insufficient_evidence`)
- Comparaison des méthodes : `reports/pricing_final/comparaison_methodes.csv`
- Comparaison aux politiques simples (avec avertissement méthodologique) :
  `reports/pricing_final/comparaison_politiques.csv`
- Population éligible : `reports/pricing_final/eligibilite_produits.csv` (218 individuel / 70 pooling
  catégorie / 12 non éligibles)
- Manifeste SHA-256 : `reports/pricing_final/manifest.json`
- Vérifications finales : `reports/pricing_final/final_checks.json` — tous les contrôles passent, y
  compris **0 simulation `haute confiance`** (structurellement indisponible tant que WAPE_quantite ≥ 50 %)
- Registre V2 : `reports/pricing_final/pricing_v2_objectives.md`
- Rapports : `reports/26_*.md` à `reports/34_*.md`

## Tests

148/148 tests passent (forecasting + pricing confondus, dernière exécution lors de l'archivage pricing).
Deux échecs transitoires rencontrés pendant la session (contention mémoire du bac à sable, déjà documentée
dans ce projet) — confirmés non reproductibles par ré-exécution isolée à chaque fois.

## Limites conservées

**Forecasting** : WAPE quotidienne élevée (~109 %), horizon 90j expérimental, intervalles sous-couverts
sur la classe A, aucune validation sur décembre.

**Pricing** : WAPE quantité élevée (107,1 %) pour la méthode retenue, aucune élasticité hors promotion
identifiable (prix catalogue fixe, structurel), effets de promotion observationnels non causaux,
`off_policy_evaluation_validated=false` (la comparaison aux politiques simples ne prouve aucun gain de
marge réel), bande d'incertitude simplifiée (pas un intervalle conforme par segment).

## Objectifs V2 (résumé, détail dans les registres dédiés)

- **Forecasting** : recalibration des intervalles par segment, hurdle mieux calibré, historique plus
  long, optimisation produits A, prévision directe par horizon, monitoring de dérive.
- **Pricing** : tests A/B de remises, groupe témoin, collecte de vrais changements de prix catalogue,
  historique plus long, propension de mise en promotion, double ML/modèle causal, validation hors
  politique, intervalles conformes par segment, modèle de demande mieux calibré, suivi du stock
  intrajournalier, monitoring des recommandations.

## Ce qui n'a pas été fait

- **Aucune écriture Supabase.**
- **Aucun déploiement.**
- Aucune intégration dans une application.

---

**Les deux phases (forecasting et pricing) sont closes pour cette version. Arrêt avant toute intégration
applicative, comme convenu.**
