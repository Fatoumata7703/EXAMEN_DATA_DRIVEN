# 24 — Entraînement final et livrable de prévisions

_Généré le 2026-08-14T11:40:17.255549+00:00._

- Modèle : **AutoETS + repli Naive** (identique au pipeline validé, rapport 23 §9).
- Historique d'entraînement : jusqu'au **2026-07-31** inclus, 300 séries.
- Replis Naive : 0/300 séries (0.00%).
- Durée d'entraînement + prévision : 54.7s.
- Horizons produits : 1 à 90 jours ; **seuls 1-30 jours sont couverts par le backtest** (H=30) — 31-90 jours marqués `horizon_valide_par_backtest=False` dans le livrable, réserve forte explicite (cf. `models/forecast_final/metadata.json`).
- Intervalles : conformes, calibrés sur les résidus poolés des 6 fenêtres de backtest, par bucket d'horizon.

**Livrable** : `reports\forecast_final\previsions_finales.parquet` (et .csv) — 27000 lignes, colonnes : product_id, date_prevision, date_cible, horizon, quantite_prevue, borne_basse_80, borne_haute_80, borne_basse_95, borne_haute_95, modele_demande, modele_effectif, fallback_applique, version, date_entrainement, horizon_valide_par_backtest

**Métadonnées modèle** : `models\forecast_final\metadata.json`

**Aucune publication Supabase, aucun déploiement — livrable strictement local.**