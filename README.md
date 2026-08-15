# Projet Data-Driven — Forecasting, Pricing, Recommandation

Trois phases indépendantes, chacune figée en V1 et documentée séparément. **Aucune des trois n'a été
déployée. Aucune n'a écrit dans Supabase.** Ce document est le point d'entrée unique : commandes de
reproduction, résultats, limites, usages autorisés — pour les trois.

Source de données : schéma en étoile Supabase (`dim_produit`, `dim_client`, `dim_date`, `dim_promotion`,
`fact_ventes`, `fact_evenements_web`, `fact_stock`), accès strictement en lecture seule tout au long du
projet (voir `src/data/connection.py`, garde-fous `assert_read_only`).

---

## Vue d'ensemble

| Phase | Statut | Modèle retenu | Métrique clé | Métadonnées |
|---|---|---|---|---|
| Forecasting | V1 (figée) | AutoETS + repli Naive | WAPE cumulée 30j = 0,2772 | [`models/forecast_final/metadata.json`](models/forecast_final/metadata.json) |
| Pricing | V1 exploratoire (figée) | LightGBM (simulateur uniquement) | WAPE quantité = 1,07 (107 %) | [`reports/pricing_final/metadata.json`](reports/pricing_final/metadata.json) |
| Recommandation | V1 baseline (figée) | Popularité globale (+ récente en secours) | NDCG@10 moyen = 0,044 | [`reports/recsys_final/metadata.json`](reports/recsys_final/metadata.json) |

**Aucune des trois V1 n'est un système causal, personnalisé ou optimisé au sens fort du terme.** Chacune
documente honnêtement pourquoi, et ce qu'il faudrait pour aller plus loin (registres V2 dédiés).

---

## Données — aucune donnée réelle n'est incluse dans ce dépôt

Ce dépôt contient **uniquement du code, des rapports et des artefacts agrégés/produit-niveau**. Aucune
extraction brute de `fact_ventes`, `fact_evenements_web`, `fact_stock` ni `dim_client` n'est publiée
(voir `.gitignore` : `data/raw/`, `data/interim/`, `data/processed/` sont exclus). Le seul fichier
proche du grain client (`reports/recsys_final/recommandations_sortie.csv`, ~135 Mo, une ligne par
client×produit recommandé) est également exclu, pour sa taille et sa granularité. Pour reproduire les
résultats, une connexion à votre propre projet Supabase (lecture seule) est nécessaire — voir
« Configuration » ci-dessous.

---

## Architecture du projet

```
src/
  config/         Configuration centrale, lecture des identifiants (.env), aucun secret en dur
  data/           Connexion Supabase/PostgreSQL en LECTURE SEULE, garde-fous (assert_read_only)
  features/       Calendrier, segmentation ABC/XYZ, features stock
  pricing/        Éligibilité, baselines, méthodes d'uplift, prédicteurs (phase Pricing)
  recsys/         Chargement des données, modèles de recommandation, métriques (phase Recommandation)
  evaluation/     Métriques de prévision (WAPE, MASE, RMSSE, biais...)
  pipelines/      Un module par étape de pipeline (backtest, entraînement final, simulateur,
                  finalisation/archivage) — point d'entrée de toutes les commandes ci-dessous
  utils/          Logging structuré (JSONL)
scripts/          Scripts d'audit et de validation ponctuels (schéma, cohérence, stock...)
tests/            156 tests (intégrité des données, anti-fuite temporelle, non-régression, garde-fous)
reports/          Tous les rapports générés (numérotés dans l'ordre de production), + sous-dossiers
                  *_final/ contenant les artefacts figés de chaque V1 (métadonnées, manifestes,
                  résultats agrégés)
models/           Métadonnées du modèle forecasting (les modèles eux-mêmes sont sans état — refit à
                  chaque appel, rien à sérialiser)
config/config.yaml Configuration du pipeline (mapping de schéma, hyperparamètres, chemins)
```

## Installation

```bash
python -m venv .venv
# Windows : .venv\Scripts\activate    macOS/Linux : source .venv/bin/activate
pip install -r requirements.txt
```

Python ≥3.11 recommandé (testé sous 3.13). Voir `requirements.txt` pour la liste complète des
dépendances (accès données, calcul, modélisation, qualité/tests).

## Configuration

1. Copier `.env.example` vers `.env`.
2. Renseigner **uniquement** vos propres identifiants Supabase (connexion PostgreSQL directe *ou* clé
   API REST — voir les deux options commentées dans `.env.example`). Utiliser de préférence un rôle en
   lecture seule.
3. `.env` est exclu de Git (`.gitignore`) — ne jamais le committer.
4. Vérifier la connexion :

```bash
python scripts/check_connection.py
```

---

## 1. Forecasting — prévision de la quantité vendue

### Modèle et usage validé

`AutoETS` (statsforecast) avec repli `Naive` sur exception (0,78 % des séries). **Usage validé : cumul
7/14/30 jours par produit.** La précision quotidienne (WAPE ≈109 %) n'est **pas fiable** — c'est un
objectif de V2, pas un défaut caché.

### Résultats clés

- WAPE cumulée 30 jours : **0,2772** (périmètre comparable, hors cold-start).
- WAPE quotidienne (grain produit×jour) : **≈1,09** — à ne jamais confondre avec la WAPE cumulée
  (rapport 23 §1, vérifié indépendamment, rapport 22).
- Couverture native AutoETS : 99,22 % (13/1662 séries en repli `Naive`, historique trop court).
- Intervalles conformes 80 %/95 % par bucket d'horizon (J+1 / J+2-7 / J+8-14 / J+15-30) — bien calibrés
  globalement, **sous-couverts sur la classe A** (74,4 % au lieu de 80 %, limite documentée).
- Horizon 90 jours : **expérimental**, hors plage validée par le backtest (H=30).

### Limites

- Fiabilité quotidienne insuffisante pour un réapprovisionnement jour par jour.
- Aucune validation sur une période de décembre (absente des fenêtres de backtest).
- Aucune rupture de stock intrajournalière mesurable (stock jamais <21 unités en fin de journée observée).

### Usages autorisés

✅ Planification et budget à 7/14/30 jours, cumulés par produit.
❌ Décision de réapprovisionnement quotidien automatisée sans revue humaine.
❌ Prévisions à 90 jours présentées comme fiables.

### Reproduction

```bash
python -m src.pipelines.backtest_baselines
python -m src.pipelines.backtest_postprocess
python -m src.pipelines.backtest_lightgbm
python -m src.pipelines.backtest_report_final
python -m src.pipelines.backtest_report_lightgbm
python -m src.pipelines.backtest_report_forecasting_final
python -m src.pipelines.train_final_forecast
python -m src.pipelines.finalize_forecast_v1
python -m src.pipelines.freeze_v1_manifest
```

### Artefacts

- Prévisions : `reports/forecast_final/previsions_finales.parquet` / `.csv`
- Métadonnées : `models/forecast_final/metadata.json`
- Manifeste SHA-256 : `reports/forecast_final/v1_manifest.json`
- Registre V2 : `reports/forecast_final/forecasting_v2_objectives.md`
- Rapports détaillés : `reports/15_*.md` à `reports/25_*.md`

---

## 2. Pricing — analyse promotions, marges, simulation de remises

### Positionnement (à respecter strictement)

**Aide à la décision exploratoire, jamais un moteur de prix optimal.** `causal: false`,
`optimal_price_claim_allowed: false`, `automatic_application_allowed: false`,
`human_validation_required: true`.

### Pourquoi pas de prix optimal

Le prix catalogue est **fixe pour 300/300 produits** (vérifié sur la table analytique ET sur les
versions SCD brutes de `dim_produit` en relecture directe) — structurel, pas une lacune de collecte.
Seule la grille de remise (5-30 %) offre une variation exploitable, et uniquement en intra-produit.

### Résultats clés

- Méthode retenue pour le simulateur exploratoire : `challenger_ml_lightgbm` — biais quasi nul
  (+0,0100) **mais WAPE quantité élevée (1,0713, soit 107,1 %)** : les estimations individuelles
  restent incertaines malgré un biais global faible (ce sont deux choses différentes).
- 218/300 produits éligibles à une estimation individuelle, 70/300 en pooling catégorie, 12/300 non
  éligibles (aucune promotion observée).
- 679 lignes historiques à marge négative (73 produits), dont 91,6 % dues à la remise elle-même (pas au
  bruit de prix) — un garde-fou de marge minimale reste nécessaire.
- Simulateur : 288 simulations de remise (scénario marge, plancher 5 %), remise moyenne recommandée
  **1,2 %** — les promotions historiques ne génèrent généralement pas assez de volume additionnel pour
  compenser la perte de marge. Résultat observationnel, cohérent sur toutes les méthodes testées.
- `off_policy_evaluation_validated: false` — la comparaison aux politiques simples ne prouve aucun gain
  de marge réel (seule la politique historique est réellement observée).

### Limites

- Tout uplift mesuré reste une **association**, jamais un effet causal (sélection de campagne non
  randomisée).
- Bande d'incertitude simplifiée (±WAPE poolée), pas un intervalle conforme calibré par segment.
- Aucun A/B test prix disponible.

### Usages autorisés

✅ Analyse descriptive des promotions/marges (objectif A) — sans réserve.
✅ Simulation de scénarios de remise sous contrainte de marge, **avec validation humaine systématique**.
❌ Application automatique d'une remise simulée.
❌ Toute affirmation d'un « prix optimal » ou d'un effet causal des promotions.

### Reproduction

```bash
python -m src.pipelines.pricing_audit
python -m src.pipelines.pricing_prototype
python -m src.pipelines.pricing_finalize
```

### Artefacts

- Sorties du simulateur : `reports/pricing_final/simulateur_sorties.csv`
- Métadonnées : `reports/pricing_final/metadata.json`
- Manifeste SHA-256 : `reports/pricing_final/manifest.json`
- Registre V2 : `reports/pricing_final/pricing_v2_objectives.md`
- Rapports détaillés : `reports/26_*.md` à `reports/34_*.md`

---

## 3. Recommandation — liste de popularité (personnalisation non validée)

### Positionnement (à respecter strictement)

**Une liste de popularité générique, jamais un moteur de recommandation personnalisé.**
`personalization_validated: false`, `hybrid_model_authorized: false`, `web_signal_enabled: false`.
Les mêmes produits sont recommandés à tous les clients d'un même segment de repli — ce n'est pas un
système qui apprend des préférences individuelles.

### Modèle retenu et règle de sélection

`popularite_globale` en principal, `popularite_recente` en secours, `popularite_globale` imposée en
cold-start. Sélection par règle fixée à l'avance (NDCG@10 moyen → Recall@10 moyen → stabilité →
couverture → biais) : l'écart entre les deux n'était que de **1,5 % relatif** — aucune des deux ne
domine clairement.

### Résultats clés — performances modestes, assumées comme telles

- **NDCG@10 moyen = 0,044, Recall@10 moyen = 0,076** (échelle 0-1) — des scores faibles en absolu.
- **Couverture catalogue moyenne ≈5,4 %** — la quasi-totalité des 300 produits n'est jamais
  recommandée ; une popularité globale concentre mécaniquement l'exposition sur une poignée d'articles.
- Aucun modèle personnalisé (filtrage collaboratif, contenu, popularité par catégorie) ne bat clairement
  la popularité récente sur plusieurs fenêtres — d'où la personnalisation désactivée.
- Plafond structurel de Recall : 89,6-92,0 % seulement des cibles réelles étaient présentes dans
  l'ensemble de candidats (politique par défaut) — décomposé et réconcilié exactement (rachats exclus +
  produits pas encore suivis en stock), **jamais de vraie rupture de stock** dans ces exclusions (le
  stock ne descend jamais sous 21 unités, reconfirmé).
- Signal web (`view`/`add_to_cart`) testé en repli cold-start : **dégrade** le Recall plutôt que de
  l'améliorer (trop peu d'événements par client) — désactivé (`web_signal_enabled: false`).

### Limites

- `vente_id` = une ligne de vente, jamais une commande — aucune règle « achetés ensemble ».
- `order_id`, `session_id` métier, `event_timestamp` absents — aucune recommandation séquentielle.
- Cold-start réel non observable aux fenêtres tardives (tous les clients ont déjà acheté) — mesuré sur
  une fenêtre dédiée en début de période.

### Usages autorisés

✅ Liste générique de popularité (accueil, page catégorie) — `automatic_recommendation_allowed: true`
**uniquement pour cet usage générique**.
❌ Toute liste présentée comme personnalisée par client.
❌ Utilisation dans une campagne commerciale sans validation humaine (`human_validation_required: true`
dans ce cas précis).

### Reproduction

```bash
python -m src.pipelines.recsys_prototype
python -m src.pipelines.recsys_verification
python -m src.pipelines.recsys_reconciliation
python -m src.pipelines.recsys_consolidation
python -m src.pipelines.recsys_finalize
```

### Artefacts

- Sorties : `reports/recsys_final/recommandations_sortie.csv`
- Métadonnées : `reports/recsys_final/metadata.json`
- Manifeste SHA-256 : `reports/recsys_final/manifest.json`
- Registre V2 : `reports/recsys_final/recommendation_v2_objectives.md`
- Rapports détaillés : `reports/36_*.md` à `reports/41_*.md`

---

## Garde-fous transverses aux trois phases

- **Accès données** : lecture seule stricte (`assert_read_only`, timeouts de transaction, aucune
  écriture jamais tentée).
- **Aucun secret en dur** : identifiants exclusivement via `.env` (non versionné), masqués dans tous
  les logs/rapports.
- **Aucune donnée future** : chaque phase applique une validation temporelle stricte (train
  strictement antérieur au test), avec assertions actives dans le code, pas seulement des contrôles a
  posteriori.
- **Aucune fabrication de résultat** : chaque rapport documente explicitement ses hypothèses, ses
  limites, et distingue systématiquement association et causalité.
- **Aucun déploiement, aucune écriture Supabase** — à aucune étape des trois phases.

## Tests

```bash
python -m pytest -q
```

156 tests couvrant les trois phases (intégrité des données, anti-fuite temporelle, non-régression des
bugs corrigés en cours de projet, équivalence de calcul, garde-fous de simulation).

## Dépendances

Voir `requirements.txt`. Environnement Python géré localement (pas de `venv` imposé par ce dépôt).
