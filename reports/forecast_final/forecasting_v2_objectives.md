# Registre d'objectifs — Forecasting V2

_Créé le 2026-08-14. Ce document n'est pas un engagement de calendrier : c'est un registre de pistes
d'amélioration, évaluées honnêtement, à réviser à chaque nouvelle livraison de données. Aucune de ces
pistes n'est mise en œuvre dans la V1 ; ce document sert de point de départ pour la V2._

## Objectif prioritaire

> **Réduire significativement le WAPE quotidien produit × jour, actuellement proche de 109 %, tout en
> conservant ou améliorant la performance cumulée à 30 jours (WAPE 0,2772).**

Le WAPE quotidien élevé n'est pas un artefact de calcul (vérifié indépendamment, cf.
`reports/23_rapport_final_forecasting.md` §1-2) : il reflète la difficulté réelle de prévoir la vente
d'un produit sur un jour précis dans un contexte de forte intermittence (>50 % de jours à vente nulle).
Aucune piste ci-dessous ne garantit un gain — chacune est une hypothèse à tester, pas une promesse.

## Pistes d'amélioration

Pour chaque piste : donnée nécessaire, gain attendu, complexité, priorité, risque de fuite, condition de
validation avant adoption.

### 1. Historique plus long, plusieurs cycles annuels
- **Donnée nécessaire** : au moins 24-36 mois d'historique continu (actuellement ~18 mois, un seul cycle
  annuel partiel).
- **Gain attendu** : moyen-élevé — permettrait de valider la saisonnalité annuelle réelle (actuellement
  supposée via `season_length=7`, jamais testée sur un cycle complet) et de backtester sur plusieurs
  décembre (cf. limite explicite du rapport 23 §11).
- **Complexité** : nulle côté modélisation, dépend uniquement de la disponibilité des données côté
  Supabase.
- **Priorité** : haute — condition préalable à plusieurs autres pistes (ci-dessous).
- **Risque de fuite** : aucun en soi.
- **Condition de validation** : re-belltest complet avec fenêtres couvrant au moins un décembre entier
  avant de modifier la recommandation de modèle.

### 2. Vraie date de lancement produit
- **Donnée nécessaire** : `date_lancement` fiable en base (actuellement `date_debut_validite`, dont la
  sémantique exacte — début de validité SCD2 vs date de lancement réelle — n'a jamais pu être confirmée
  empiriquement, cf. audit initial).
- **Gain attendu** : moyen — améliorerait `age_produit_jours`, actuellement approximatif, et la stratégie
  cold-start.
- **Complexité** : faible si la donnée existe côté source, sinon bloquant.
- **Priorité** : moyenne.
- **Risque de fuite** : faible, à condition que la date soit connue au moment de la prévision (elle
  l'est par construction pour un produit déjà lancé).
- **Condition de validation** : confirmer la sémantique auprès du métier avant tout usage — ne jamais
  redevenir une hypothèse non vérifiée comme lors de l'audit initial.

### 3. Données de commande avec `order_id`
- **Donnée nécessaire** : granularité commande (actuellement seulement produit × jour agrégé).
- **Gain attendu** : élevé pour la compréhension du panier et de la co-occurrence produit, faible à
  direct pour le WAPE quotidien seul.
- **Complexité** : élevée — refonte du grain d'agrégation, nouvelle table de faits.
- **Priorité** : basse pour le forecasting V2, potentiellement haute pour un futur module panier/cross-sell.
- **Risque de fuite** : nul si la reconstruction respecte le même principe de cutoff déjà en place.
- **Condition de validation** : audit de qualité dédié (même rigueur que l'audit initial) avant tout usage.

### 4. Informations précises sur les ruptures intrajournalières
- **Donnée nécessaire** : timestamp de rupture de stock (pas seulement le stock de fin de journée déjà
  disponible).
- **Gain attendu** : élevé — la censure de la demande par le stock est actuellement invérifiable
  intra-jour (cf. `reports/13_validation_stock.md` : « aucune rupture visible en fin de journée, mais
  une rupture intrajournalière ne peut être exclue »). C'est une source de biais potentielle non
  quantifiée à ce jour.
- **Complexité** : élevée, dépend de la source (souvent absente des systèmes de caisse standards).
- **Priorité** : haute si disponible — lève une incertitude structurelle actuelle.
- **Risque de fuite** : **élevé si mal maîtrisé** — toute variable de stock doit rester strictement
  antérieure au cutoff pour chaque jour prédit (cf. les 3 scénarios stock déjà documentés dans
  `src/pipelines/backtest_lightgbm.py`, scénario C jamais réalisé faute de règle de projection validée).
- **Condition de validation** : reproduire les tests de perturbation anti-fuite déjà en place
  (`tests/test_lightgbm_recursive_no_leakage.py`) avant tout usage en feature.

### 5. Timestamps et sessions web
- **Donnée nécessaire** : `fact_evenements_web` à la granularité session/timestamp (actuellement agrégé
  par jour : `web_add_to_cart`, `web_purchase`, `web_view`).
- **Gain attendu** : moyen — signal avancé d'intérêt produit, mais déjà partiellement capté par les
  agrégats journaliers actuels.
- **Complexité** : moyenne.
- **Priorité** : moyenne.
- **Risque de fuite** : élevé si les événements web du jour prédit lui-même sont utilisés comme feature
  contemporaine (`web_total` actuel n'est jamais utilisé pour J+2..J+30, seulement en variable connue
  du jour observé pour du diagnostic — à re-vérifier explicitement si réintégré).
- **Condition de validation** : même principe de test de perturbation qu'au point 4.

### 6. Signaux marketing futurs
- **Donnée nécessaire** : calendrier marketing planifié (campagnes email/pub, budget par période),
  connu à l'avance.
- **Gain attendu** : moyen, surtout pour les pics ponctuels hors promotion produit.
- **Complexité** : moyenne — nécessite une source de données marketing non présente actuellement.
- **Priorité** : basse à moyenne.
- **Risque de fuite** : faible si strictement un plan connu à l'avance (même statut que le calendrier
  promotionnel actuel, déjà documenté comme hypothèse explicite non vérifiable techniquement — cf.
  docstring `FUTURE_KNOWN_COLS` dans `src/pipelines/backtest_lightgbm.py`).
- **Condition de validation** : documenter la même réserve que pour le calendrier promotionnel actuel.

### 7. Événements locaux et jours fériés sénégalais
- **Donnée nécessaire** : aucune — déjà partiellement implémenté (Korité, Tabaski, Magal, Tamxarit,
  Maouloud, fenêtre Ramadan — `src/features/calendar.py`).
- **Gain attendu** : faible à moyen pour un enrichissement (événements locaux non religieux : marchés,
  foires) au-delà de ce qui existe déjà.
- **Complexité** : faible.
- **Priorité** : basse — le socle calendaire est déjà solide.
- **Risque de fuite** : nul (dates connues à l'avance par construction).
- **Condition de validation** : test A/B sur le WAPE avant/après ajout, par fenêtre.

### 8. Météo (si pertinente selon les catégories)
- **Donnée nécessaire** : historique météo + prévisions météo à l'horizon de prévision (J+1 à J+30 —
  la prévision météo elle-même n'est fiable qu'à quelques jours, ce qui limite l'intérêt au-delà de J+7).
- **Gain attendu** : faible à moyen, probablement concentré sur quelques catégories (boissons, produits
  saisonniers) — à vérifier catégorie par catégorie avant d'investir.
- **Complexité** : moyenne (source externe à intégrer).
- **Priorité** : basse.
- **Risque de fuite** : élevé si la météo *réelle* du jour prédit est utilisée au lieu de la *prévision*
  météo qui aurait été disponible à la date de la prévision — piège classique.
- **Condition de validation** : utiliser exclusivement des prévisions météo historiques (pas la météo
  observée a posteriori) dans tout backtest.

### 9. Modèles séparés par catégorie ou typologie de vente
- **Donnée nécessaire** : aucune nouvelle donnée — réorganisation de l'entraînement.
- **Gain attendu** : moyen — certaines catégories peuvent avoir une dynamique très différente
  (saisonnalité, intermittence) diluée dans un modèle global par série.
- **Complexité** : faible à moyenne (AutoETS est déjà par série ; un modèle par catégorie serait surtout
  pertinent pour une approche globale type LightGBM/deep learning, cf. point 15).
- **Priorité** : moyenne.
- **Risque de fuite** : nul en soi.
- **Condition de validation** : comparer au backtest actuel sur le même découpage de fenêtres, jamais
  sur un découpage différent qui rendrait la comparaison invalide.

### 10. Modèles probabilistes pour séries intermittentes
- **Donnée nécessaire** : aucune nouvelle donnée.
- **Gain attendu** : moyen-élevé pour la qualité des intervalles (actuellement conformes/empiriques,
  pas nativement probabilistes) — CrostonOptimized/TSB existent déjà mais n'ont pas battu AutoETS en
  WAPE dans ce backtest (cf. rapport 18 §1).
- **Complexité** : moyenne.
- **Priorité** : moyenne — lié directement au point 12 (hurdle mieux calibré).
- **Risque de fuite** : nul en soi si le même protocole walk-forward est respecté.
- **Condition de validation** : comparaison PR-AUC/calibration comme déjà fait pour le hurdle LightGBM
  (rapport 21 §4) — ne pas se contenter du WAPE seul pour ces modèles.

### 11. Hurdle ou zero-inflated mieux calibré
- **Donnée nécessaire** : aucune nouvelle donnée.
- **Gain attendu** : moyen — le hurdle LightGBM testé a un ROC-AUC de seulement 0,62 (discrimination
  faible à modeste, cf. rapport 21 §4) ; un modèle mieux calibré (ex. régularisation différente,
  features supplémentaires ciblées sur le zéro/positif, calibration isotonique post-hoc) pourrait
  améliorer nettement ce chiffre sans changer d'architecture.
- **Complexité** : faible-moyenne (ajustement, pas refonte).
- **Priorité** : haute — c'est la piste la moins coûteuse pour attaquer directement le problème
  identifié (sur-prévision des zéros).
- **Risque de fuite** : nul si le protocole recursive déjà validé (`recursive_predict`) est réutilisé
  tel quel.
- **Condition de validation** : reproduire les tests de perturbation existants
  (`test_hurdle_perturber_la_validation_ne_change_rien`) + viser ROC-AUC > 0,70 comme seuil indicatif
  avant de reconsidérer LightGBM face à AutoETS.

### 12. Prévision directe par horizon plutôt qu'une récursion longue
- **Donnée nécessaire** : aucune nouvelle donnée.
- **Gain attendu** : moyen-élevé — la stratégie récursive actuelle de LightGBM montre une dérive du
  biais avec l'horizon (rapport 23 §4, LightGBM_Hurdle : biais +0,10 à J+1 → +0,19 à J+15-30), un
  symptôme classique d'accumulation d'erreur en récursion longue. Un modèle direct par horizon (un
  modèle par h, ou un modèle avec `h` en feature sans récursion) éliminerait cet effet par construction.
- **Complexité** : moyenne-élevée (30 modèles à entraîner et maintenir, ou architecture multi-sortie).
- **Priorité** : haute si LightGBM est repris en V2.
- **Risque de fuite** : nul en soi, mais nécessite les mêmes garde-fous sur les variables connues au
  cutoff (`FUTURE_KNOWN_COLS`) — pas de relâchement des règles actuelles.
- **Condition de validation** : même suite de tests anti-fuite, adaptée à l'absence de récursion (plus
  besoin de tester la boucle des 30 pas, mais toujours besoin de tester qu'aucune vraie valeur de
  validation n'entre dans les features).

### 13. Optimisation spécifique produits A
- **Donnée nécessaire** : aucune nouvelle donnée.
- **Gain attendu** : élevé en valeur métier (les produits A pèsent disproportionnellement dans le CA/la
  marge) même si le gain en WAPE brut reste modeste — AutoETS est déjà le meilleur sur ce segment
  (0,2801, cf. rapport 18 §10 corrigé) mais un modèle dédié pourrait faire mieux.
- **Complexité** : moyenne (nécessite un jeu de features et un tuning séparés, cf. point 9).
- **Priorité** : haute — c'est le segment où la valeur métier justifie le plus l'investissement.
- **Risque de fuite** : nul en soi.
- **Condition de validation** : comparaison stricte au benchmark AutoETS actuel sur le même périmètre A
  (376 produits×fenêtres, grain corrigé — cf. rapport 18 §10), pondérée CA/marge comme au rapport 23 §7.

### 14. Recalibration des intervalles par segment
- **Donnée nécessaire** : aucune nouvelle donnée.
- **Gain attendu** : élevé et rapide — limite déjà identifiée et quantifiée (rapport 23 §8) : couverture
  80 % visée mais 74,4 % réelle sur la classe A avec la calibration poolée actuelle.
- **Complexité** : faible — même méthode conforme, calibrée séparément par segment (classe ABC ou profil
  de demande) au lieu d'un pool unique.
- **Priorité** : **très haute** — correction peu coûteuse d'un défaut déjà mesuré, pas une hypothèse.
- **Risque de fuite** : nul (même protocole de calibration hors-fenêtre déjà en place).
- **Condition de validation** : revalider la couverture empirique par segment après recalibration,
  cible ≥78-82 % pour un niveau visé de 80 %.

### 15. Comparaison avec N-BEATS, N-HiTS ou DeepAR
- **Donnée nécessaire** : historique nettement plus long (point 1) — ces modèles deep learning ont
  besoin de volume pour apprendre au-delà de ce qu'apporte un modèle par série comme AutoETS.
- **Gain attendu** : incertain avec le volume actuel (~300 séries, ~18 mois) — probablement faible à ce
  stade, potentiellement élevé avec 2-3 ans d'historique et plusieurs centaines de séries
  supplémentaires.
- **Complexité** : élevée (infrastructure d'entraînement, GPU recommandé, plus de code à maintenir).
- **Priorité** : basse tant que le point 1 n'est pas résolu — investissement prématuré aujourd'hui.
- **Risque de fuite** : élevé si mal implémenté (ces architectures encodent nativement plusieurs séries
  ensemble — vérifier qu'aucune série de validation ne contamine l'entraînement d'une autre via un
  découpage temporel global mal posé, pas seulement par série).
- **Condition de validation** : même protocole de backtest à 6 fenêtres + tests de non-fuite adaptés à
  l'architecture globale (pas seulement par série comme les tests actuels).

### 16. Monitoring des erreurs et détection de dérive
- **Donnée nécessaire** : aucune nouvelle donnée — nécessite un pipeline de suivi post-déploiement
  (comparer prévisions passées aux ventes réelles une fois connues).
- **Gain attendu** : élevé en fiabilité opérationnelle (détecter une dégradation du modèle en production
  avant qu'elle ne devienne coûteuse) — indépendant d'un gain de WAPE.
- **Complexité** : moyenne (infrastructure de suivi, alerting).
- **Priorité** : haute avant tout déploiement réel (actuellement aucun déploiement, cf. `metadata.json`
  `aucun_deploiement: true`) — condition préalable à la mise en production, pas une amélioration de
  modèle à proprement parler.
- **Risque de fuite** : nul (mesure a posteriori).
- **Condition de validation** : définir un seuil d'alerte (ex. WAPE glissant sur 4 semaines dépassant de
  X % le WAPE de backtest) avant la mise en place, pas après.

## Priorisation synthétique (ordre suggéré, à rediscuter)

1. Recalibration des intervalles par segment (#14) — rapide, gain mesuré, aucun risque.
2. Hurdle mieux calibré (#11) — attaque directement le problème prioritaire (zéro vs positif).
3. Historique plus long (#1) — condition préalable à plusieurs autres pistes.
4. Optimisation produits A (#13) — valeur métier la plus directe.
5. Prévision directe par horizon (#12) — corrige un défaut structurel déjà mesuré (dérive du biais).
6. Monitoring et détection de dérive (#16) — condition avant tout déploiement réel.
7. Le reste, conditionné à la disponibilité des données correspondantes.
