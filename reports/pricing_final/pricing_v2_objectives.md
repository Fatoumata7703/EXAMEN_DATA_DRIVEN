# Registre d'objectifs — Pricing V2

_Créé le 2026-08-14. Registre de pistes, pas un engagement de calendrier. Pricing V1 reste exploratoire
(`pricing_version: pricing_v1_exploratory`) — ce document décrit ce qui manque pour dépasser ce statut._

## Objectif principal

> **Construire une estimation causale et mieux calibrée de la réponse de la demande aux prix et
> promotions, puis valider prospectivement les recommandations.**

Deux manques structurels de la V1 motivent cet objectif : (1) l'affectation des campagnes promotionnelles
n'est pas randomisée — aucune méthode observationnelle ne peut prouver un effet causal à partir de ces
données seules ; (2) la précision individuelle du modèle retenu reste faible (WAPE quantité 107,1 %) —
une meilleure calibration est nécessaire avant toute application, même simulée.

## Pistes prioritaires

### 1. Tests A/B de remises
- **Donnée nécessaire** : infrastructure d'expérimentation (assignation aléatoire de remises à des
  groupes de produits/clients comparables).
- **Priorité** : **haute** — seul moyen direct d'obtenir un effet causal.
- **Coût** : élevé (organisationnel, pas seulement technique).
- **Gain attendu** : élevé — remplace l'association par un effet mesuré.
- **Risque** : coût commercial des bras de test à remise sous-optimale ; nécessite un accord métier.
- **Condition de validation** : puissance statistique calculée a priori, durée suffisante pour couvrir la
  variance saisonnière déjà mesurée (amplitude déc./mars ≈1,62 côté forecasting).

### 2. Groupe témoin
- **Donnée nécessaire** : produits/périodes délibérément non exposés à une promotion testée, comparables
  par catégorie/saisonnalité.
- **Priorité** : haute — condition du point 1.
- **Coût** : moyen.
- **Gain attendu** : élevé — permet une différence de différences (diff-in-diff) au minimum.
- **Risque** : contamination si le témoin est en réalité affecté par la promotion (ex. substitution
  produit).
- **Condition de validation** : vérifier l'absence de tendance parallèle avant traitement.

### 3. Collecte des changements réels de prix catalogue
- **Donnée nécessaire** : au moins quelques produits avec un historique de changement de `prix_base_xof`
  (actuellement 0/300, structurellement fixe — cf. rapport 26 §1).
- **Priorité** : haute si l'objectif « prix optimal hors promotion » reste souhaité à terme.
- **Coût** : dépend entièrement du système source (hors du périmètre de ce projet).
- **Gain attendu** : débloquerait, pour la première fois, une estimation d'élasticité hors promotion.
- **Risque** : aucun risque technique, seulement organisationnel (dépend d'une décision produit externe).
- **Condition de validation** : au moins quelques dizaines de changements de prix par produit concerné,
  répartis dans le temps, pour espérer un signal exploitable.

### 4. Historique plus long
- **Donnée nécessaire** : au moins 24-36 mois (actuellement ~18 mois).
- **Priorité** : haute — condition préalable à plusieurs pistes ci-dessous.
- **Coût** : nul (attente).
- **Gain attendu** : moyen — plus de campagnes, plus de niveaux de remise par produit, meilleure
  stabilité des estimations.
- **Risque** : aucun.
- **Condition de validation** : re-belltest complet sur le portefeuille étendu.

### 5. Propension de mise en promotion
- **Donnée nécessaire** : aucune nouvelle donnée — modéliser explicitement `P(produit mis en promotion |
  caractéristiques)` à partir des données actuelles.
- **Priorité** : moyenne-haute — première étape vers un ajustement du biais de sélection sans
  expérimentation.
- **Coût** : moyen (un modèle de propension supplémentaire à maintenir).
- **Gain attendu** : moyen — permet une pondération par score de propension (IPW) en attendant
  l'expérimentation.
- **Risque** : si le modèle de propension est mal spécifié, le biais de sélection peut être aggravé plutôt
  que corrigé — à valider par des tests de balance covariée.
- **Condition de validation** : vérifier l'équilibre des covariables entre groupes pondérés avant
  d'utiliser les poids pour toute estimation d'effet.

### 6. Double machine learning ou modèle causal
- **Donnée nécessaire** : aucune nouvelle donnée, mais nécessite le point 5 (propension) au minimum.
- **Priorité** : moyenne.
- **Coût** : élevé (expertise méthodologique, temps d'implémentation et de validation).
- **Gain attendu** : moyen sans randomisation réelle — un DML réduit le biais de confusion observée
  (catégorie, calendrier, stock) mais ne peut pas corriger un biais de sélection sur des variables non
  observées.
- **Risque** : présenter un résultat DML comme causal alors que l'hypothèse d'ignorabilité reste
  invérifiable sans expérimentation — même réserve qu'aujourd'hui, à documenter aussi explicitement.
- **Condition de validation** : comparaison à la méthode actuelle (panel FE) sur le même protocole de
  validation temporelle ; test de robustesse à la spécification.

### 7. Validation hors politique (off-policy evaluation)
- **Donnée nécessaire** : aucune nouvelle donnée pour une première approche (importance sampling
  pondérée par propension), un groupe témoin pour une validation forte.
- **Priorité** : haute — condition explicite pour lever `off_policy_evaluation_validated=false`.
- **Coût** : moyen.
- **Gain attendu** : élevé — c'est le chaînon manquant entre « le modèle prévoit bien la quantité
  observée » et « la remise recommandée produirait la marge simulée ».
- **Risque** : les estimateurs off-policy (IPS, doubly robust) restent sensibles à un mauvais recouvrement
  de support — déjà partiellement documenté (rapport 29 §support commun).
- **Condition de validation** : comparer l'estimation off-policy à un résultat A/B réel dès que
  disponible (point 1), pour calibrer la confiance à accorder à la méthode hors politique seule.

### 8. Intervalles conformes par segment
- **Donnée nécessaire** : aucune nouvelle donnée — méthode déjà utilisée côté forecasting
  (`reports/23_rapport_final_forecasting.md` §8), à porter au pricing.
- **Priorité** : haute — remplace directement la bande d'incertitude simplifiée actuelle
  (`scenario_uncertainty_band` ±WAPE poolée).
- **Coût** : faible (méthode déjà implémentée ailleurs dans le projet).
- **Gain attendu** : élevé pour la qualité de la communication du risque, indépendamment du gain de
  précision du modèle lui-même.
- **Risque** : aucun.
- **Condition de validation** : couverture empirique mesurée par segment (catégorie, éligibilité
  individuel/pooling), cible ≥80 % pour un niveau visé de 80 %.

### 9. Modèle de demande mieux calibré
- **Donnée nécessaire** : aucune nouvelle donnée — travail de modélisation (feature engineering,
  régularisation, ensembling) sur le challenger ML actuel.
- **Priorité** : haute — attaque directement la WAPE quantité de 107,1 %, le principal frein identifié en
  V1.
- **Coût** : moyen.
- **Gain attendu** : élevé si réussi — objectif indicatif : WAPE quantité < 50 % pour que le palier de
  confiance « haute » redevienne atteignable (cf. règle documentée, rapport 32).
- **Risque** : sur-ajustement si la validation temporelle n'est pas strictement respectée à chaque
  itération.
- **Condition de validation** : même protocole à 3 (ou davantage, cf. point 4) fenêtres, jamais
  d'hyperparamètre choisi sur le test.

### 10. Suivi du stock intrajournalier
- **Donnée nécessaire** : timestamp de rupture de stock (même limite que le forecasting, cf.
  `reports/forecast_final/forecasting_v2_objectives.md` #4).
- **Priorité** : moyenne — une promotion en rupture partielle biaise l'uplift mesuré vers le bas.
- **Coût** : élevé, dépend de la source.
- **Gain attendu** : moyen — débiaise partiellement l'estimation d'uplift sans nécessiter
  d'expérimentation.
- **Risque** : élevé si mal maîtrisé (même garde-fou anti-fuite qu'en forecasting : jamais de stock
  contemporain au jour prédit).
- **Condition de validation** : mêmes tests de perturbation qu'en forecasting avant tout usage en feature.

### 11. Objectifs marge/volume configurables
- **Donnée nécessaire** : aucune — déjà partiellement fait (4 objectifs simulés en V1 : marge, CA,
  écoulement stock, compromis).
- **Priorité** : basse — raffinement d'une fonctionnalité déjà existante (pondération configurable du
  compromis marge/volume, actuellement fixée à 50/50).
- **Coût** : faible.
- **Gain attendu** : faible à moyen (flexibilité métier).
- **Risque** : aucun.
- **Condition de validation** : aucune, amélioration ergonomique.

### 12. Monitoring des recommandations
- **Donnée nécessaire** : aucune nouvelle donnée — pipeline de suivi post-décision (si des remises
  simulées sont un jour appliquées avec validation humaine, comparer prévision vs résultat réel).
- **Priorité** : haute avant toute application, même partielle, des simulations en conditions réelles.
- **Coût** : moyen (infrastructure de suivi).
- **Gain attendu** : élevé en fiabilité opérationnelle — condition de fait pour transformer une V1
  exploratoire en outil réellement utilisable.
- **Risque** : aucun (mesure a posteriori).
- **Condition de validation** : définir un seuil d'alerte sur l'écart prévision/réel avant toute mise en
  usage, pas après.

## Priorisation synthétique (ordre suggéré, à rediscuter)

1. Intervalles conformes par segment (#8) — rapide, méthode déjà disponible dans le projet.
2. Modèle de demande mieux calibré (#9) — attaque directement le frein principal (WAPE 107 %).
3. Historique plus long (#4) — condition préalable à plusieurs autres pistes.
4. Propension de mise en promotion (#5) puis validation hors politique (#7) — première étape vers un
   effet moins biaisé sans attendre l'expérimentation.
5. Tests A/B (#1) + groupe témoin (#2) — la vraie réponse à la question causale, mais coûteuse et
   organisationnelle.
6. Le reste, conditionné à la disponibilité des données ou à une décision métier externe (notamment #3,
   hors du périmètre technique de ce projet).
