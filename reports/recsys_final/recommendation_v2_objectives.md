# Registre d'objectifs — Recommandation V2

_Créé le 2026-08-14, révisé le 2026-08-14 pour fixer les 6 priorités immédiates validées. Recommandation
V1 reste une baseline de popularité générique (`recommendation_version: recommendation_v1_baseline`,
`personalization_validated: false`, `performance_modeste: true`, `couverture_catalogue_faible: true`) —
**jamais présentée comme un moteur de recommandation personnalisé**. Ce document décrit ce qui manque
pour justifier une V2._

## Objectif principal

> **Obtenir un gain de personnalisation réel et répété (filtrage collaboratif ou contenu battant
> clairement la popularité sur plusieurs fenêtres), en levant les limites structurelles identifiées en
> V1 — tout en corrigeant les défauts déjà mesurés de la V1 elle-même (couverture catalogue faible,
> confusion disponibilité/rupture, rachats non distingués par usage).**

## Priorités immédiates (fixées explicitement, dans cet ordre)

### 1. Améliorer la couverture catalogue sans dégrader NDCG@10
- **Constat V1** : couverture catalogue moyenne ≈5,4 % (`popularite_globale`) — la quasi-totalité du
  catalogue de 300 produits n'est jamais recommandée. Toute amélioration ne doit pas se faire au prix
  d'une perte de qualité de classement.
- **Donnée nécessaire** : aucune nouvelle donnée pour une première approche (ex. diversification
  contrôlée : mélanger popularité + exploration bornée, ou popularité par catégorie recalibrée pour ne
  pas perdre en NDCG — cf. l'écart déjà mesuré en V1, `popularite_categorie` NDCG@10=0,0351 contre
  0,0441 pour `popularite_globale`, rapport 41 §1).
- **Priorité** : haute.
- **Coût** : faible à moyen selon la méthode (re-ranking avec contrainte de diversité, bandits
  contextuels).
- **Gain attendu** : moyen — élargir l'exposition catalogue sans sacrifier le NDCG est un compromis
  documenté en recherche (re-ranking sous contrainte), pas un gain garanti d'emblée.
- **Risque** : toute méthode de diversification testée doit être comparée à `popularite_globale` sur
  **NDCG@10 ET couverture simultanément** — ne jamais accepter une baisse de NDCG non compensée par un
  gain de couverture clairement supérieur, jugé qualitativement.
- **Condition de validation** : même protocole de validation temporelle qu'en V1 (4 fenêtres), reporter
  les deux métriques côte à côte, jamais l'une sans l'autre.

### 2. Distinguer dans l'application le mode découverte du mode réapprovisionnement
- **Constat V1** : les deux scénarios sont mesurés (rapport 41 §5) mais V1 n'en retient qu'un par
  défaut (découverte, achats déjà faits exclus) — l'application ne propose pas aujourd'hui de bascule
  explicite entre les deux usages.
- **Donnée nécessaire** : aucune — logique déjà implémentée des deux côtés (`exclude_purchased` "true"/
  "false"), il manque l'exposition produit (UX) de ce choix, pas le calcul.
- **Priorité** : haute — corrige un vrai biais métier déjà quantifié (couverture des cibles 89,6-92,0 %
  en découverte contre 95,1-97,8 % en réapprovisionnement).
- **Coût** : faible (déjà calculé des deux côtés en V1, à exposer dans l'application).
- **Gain attendu** : élevé pour la pertinence perçue — un produit de consommation courante racheté
  naturellement ne doit pas être exclu par défaut.
- **Risque** : aucun techniquement ; nécessite une décision produit sur quels types de produits/usages
  relèvent de quel mode (pas un choix que ce projet tranche à la place du métier).
- **Condition de validation** : définir avec le métier une règle explicite de bascule (par catégorie de
  produit ? par contexte applicatif ?) avant l'implémentation.

### 3. Traiter l'absence de stock comme « disponibilité inconnue », jamais comme rupture
- **Constat V1** : la réconciliation (rapport 41 §3) a montré que 100 % des exclusions liées au stock
  viennent d'une absence d'enregistrement de stock avant le cutoff, **jamais** d'un niveau nul observé
  (le stock ne descend jamais sous 21 unités dans cette livraison). Le filtre actuel traite cette
  absence comme une indisponibilité, sans le nommer explicitement.
- **Donnée nécessaire** : aucune nouvelle donnée — correction de vocabulaire et de statut dans le code
  et l'application (`disponibilite_inconnue` comme statut distinct de `rupture_confirmee`, qui n'a
  jamais été observée dans cette livraison).
- **Priorité** : haute — corrige un risque de mauvaise communication déjà identifié explicitement par
  le métier.
- **Coût** : faible (renommage de statut, pas de nouveau calcul).
- **Gain attendu** : moyen — évite qu'une future personne interprète à tort une absence de suivi stock
  comme une preuve de rupture.
- **Risque** : aucun.
- **Condition de validation** : grep/revue de tout le code et tous les rapports V2 pour vérifier
  qu'aucune absence de donnée stock n'est jamais qualifiée de « rupture » sans preuve directe
  (`niveau_stock == 0` observé, jamais rencontré à ce jour).

### 4. Obtenir `order_id`, `session_id` et `event_timestamp`
- **Constat V1** : les trois colonnes sont absentes du schéma actuel (confirmé à l'audit, rapport 36) —
  bloquent respectivement les règles d'association produit-produit, la recommandation séquentielle, et
  toute reconstruction d'ordre intra-journalier.
- **Donnée nécessaire** : ajout de ces 3 colonnes côté source (`fact_ventes` pour `order_id`,
  `fact_evenements_web` pour `session_id`/`event_timestamp`).
- **Priorité** : haute — débloque des familles de modèles entièrement nouvelles.
- **Coût** : dépend entièrement du système source, hors périmètre technique de ce projet.
- **Gain attendu** : élevé si le volume est suffisant — capte l'intention court terme et les paniers
  réels, complémentaire à la popularité.
- **Risque** : `event_timestamp` doit être audité aussi rigoureusement que les autres colonnes
  (fuseau horaire, granularité) avant tout usage.
- **Condition de validation** : mêmes contrôles d'intégrité référentielle et d'absence de fuite qu'en
  V1, adaptés à l'ordre temporel intra-journalier et à la granularité commande.

### 5. Collecter davantage d'interactions par client
- **Constat V1** : ~18 mois d'historique, médiane 17 lignes de vente/client — suffisant pour une
  baseline de popularité, probablement insuffisant pour stabiliser un filtrage collaboratif ou un
  modèle de séquence.
- **Donnée nécessaire** : au moins 24-36 mois d'historique continu, et plus d'interactions web par
  client (V1 : ~3,3 événements web en moyenne pour les clients cold-start, rapport 39 §4 — trop peu
  pour battre un simple repli popularité).
- **Priorité** : haute — condition de base pour toute tentative sérieuse de personnalisation V2.
- **Coût** : nul (attente/collecte continue).
- **Gain attendu** : moyen-élevé.
- **Risque** : aucun.
- **Condition de validation** : re-belltest complet, même protocole ; n'accepter un modèle personnalisé
  que s'il bat `popularite_globale`/`popularite_recente` sur au moins 3 fenêtres sur 4, comme en V1.

### 6. Réaliser un test A/B avant toute conclusion commerciale
- **Constat V1** : la validation temporelle mesure la capacité à prévoir des achats déjà arbitrés par
  la politique historique, jamais l'effet réel d'une recommandation sur le comportement futur —
  aucune conclusion commerciale ne peut s'appuyer sur les seules métriques V1.
- **Donnée nécessaire** : infrastructure d'expérimentation en production (assignation aléatoire de
  variantes à des groupes de clients comparables).
- **Priorité** : haute — condition explicite avant toute utilisation des recommandations dans une
  campagne commerciale (cf. `human_validation_required=true` dans les métadonnées V1).
- **Coût** : élevé (organisationnel, pas seulement technique) — même nature que les tests A/B déjà
  identifiés aux registres V2 forecasting/pricing.
- **Gain attendu** : élevé — seule preuve directe qu'une recommandation change un comportement d'achat.
- **Risque** : coût commercial d'une variante sous-optimale ; accord métier explicite requis avant tout
  déploiement, même partiel.
- **Condition de validation** : puissance statistique calculée a priori, durée suffisante pour couvrir
  la variance saisonnière déjà caractérisée côté forecasting.

## Priorisation synthétique

1. **#3 (disponibilité inconnue vs rupture)** — coût quasi nul, corrige un risque de communication déjà
   identifié, à faire en premier.
2. **#1 (couverture sans dégrader NDCG) et #2 (découverte vs réapprovisionnement)** — gains mesurables,
   coût faible à moyen, bâtis sur des mesures déjà faites en V1.
3. **#5 (plus d'interactions) et #4 (order_id/session_id/event_timestamp)** — conditions préalables à
   toute tentative de personnalisation V2, dépendent en partie du système source.
4. **#6 (test A/B)** — la vraie validation causale, mais à ne lancer qu'après qu'un modèle personnalisé
   ait effectivement dépassé la baseline hors ligne (ce qui n'est pas encore le cas en V1) ou qu'une
   liste de popularité modifiée (couverture/mode) soit prête à être testée en conditions réelles.
