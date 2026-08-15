# 25 — Clôture Forecasting V1

_Généré le 2026-08-14._

## Statut

**V1 sauvegardée et figée.** Forecasting considéré comme clos pour cette version.

## Emplacements

| Élément | Chemin |
|---|---|
| Modèle (config + métadonnées, modèles statsforecast sans état à réentraîner) | `models/forecast_final/metadata.json` |
| Prévisions (livrable) | `reports/forecast_final/previsions_finales.parquet` / `.csv` |
| Snapshot de métriques figé (quotidien, cumulé 7/14/30j, par fenêtre, fallbacks, cold-start, intervalles) | `reports/forecast_final/v1_metrics_snapshot.json` |
| Manifeste SHA-256 | `reports/forecast_final/v1_manifest.json` |
| Vérifications finales | `reports/forecast_final/v1_final_checks.json` |
| Registre d'objectifs V2 | `reports/forecast_final/forecasting_v2_objectives.md` |
| Rapports d'analyse (17 rapports, 15 à 24) | `reports/15_*.md` à `reports/24_*.md` |

## Tests

**148/148 tests passent** (re-vérifié lors de l'archivage, `reports/forecast_final/v1_metrics_snapshot.json` → `tests`), incluant les preuves anti-fuite multi-horizon obligatoires
(`tests/test_lightgbm_recursive_no_leakage.py`, `tests/test_statsforecast_no_peeking.py`).

Vérifications finales spécifiques à l'archivage (`v1_final_checks.json`) : reproductibilité sur
échantillon, absence de NaN/Inf/négatifs, cohérence des horizons 1-90, bornes ordonnées, métadonnées
complètes, absence de secrets — **tous les contrôles passent**.

## Limites conservées (non résolues en V1, actées comme telles)

- WAPE quotidien ≈109 % — fiabilité quotidienne non garantie (`daily_forecast_reliable: false` dans les
  métadonnées). Usage principal validé : cumul 7/14/30 jours.
- Horizon 90 jours : expérimental, hors plage validée par le backtest (H=30), intervalles extrapolés
  depuis le bucket J+15-30 — réserve forte explicite.
- Intervalles sous-couverts sur la classe A (couverture empirique 74,4 % pour un niveau visé de 80 %,
  cf. rapport 23 §8) — recalibration par segment inscrite comme priorité haute au registre V2 (#14).
- Aucune rupture de stock intrajournalière mesurable — le stock n'est pas utilisé comme feature dans le
  benchmark principal.
- Aucune validation empirique sur une période de décembre (aucune fenêtre de backtest ne la couvre).
- Cold-start (`ColdStartZero`) reste une hypothèse d'exploitation prudente, pas une preuve de demande
  nulle.

## Commandes de réexécution

```bash
# Backtest complet (baselines + LightGBM + rapports comparatifs)
python -m src.pipelines.backtest_baselines
python -m src.pipelines.backtest_postprocess
python -m src.pipelines.backtest_lightgbm
python -m src.pipelines.backtest_report_final
python -m src.pipelines.backtest_report_lightgbm
python -m src.pipelines.backtest_report_forecasting_final

# Entraînement final + prévisions (une seule commande : modèles sans état, refit à chaque appel)
python -m src.pipelines.train_final_forecast

# Archivage / snapshot de métriques (idempotent, ne modifie aucun rapport existant)
python -m src.pipelines.finalize_forecast_v1
python -m src.pipelines.freeze_v1_manifest

# Suite de tests complète
python -m pytest -q
```

## Ce qui n'a pas été fait (rappel, cf. rapport 21 §7 et 23 §11)

- Aucune publication Supabase, aucun déploiement.
- Pas d'optimisation d'hyperparamètres (Optuna) sur LightGBM.
- Scénarios stock B/C non intégrés au benchmark principal.

---

**La phase forecasting est close pour la V1. La phase suivante (pricing) est traitée séparément, sans
réutilisation automatique des choix de modélisation du forecasting.**
