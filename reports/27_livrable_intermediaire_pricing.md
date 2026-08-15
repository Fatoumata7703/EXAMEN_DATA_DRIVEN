# 27 — Livrable intermédiaire pricing (avant tout modèle)

_Généré le 2026-08-14. Synthèse pour validation, construite à partir de l'audit fraîchement recalculé
(`reports/26_audit_pricing.md`) et confrontée au diagnostic de faisabilité antérieur
(`reports/11_verdict_faisabilite.md` §2). Aucun modèle n'a été entraîné pour produire ce document._

## 1. Faisabilité exacte du pricing

Trois objectifs distincts, trois verdicts différents — jamais traités comme un seul bloc :

| Objectif | Faisable ? |
|---|---|
| **A. Analyse descriptive** (prix, promos, marges) | ✅ **Oui, sans réserve** |
| **B. Mesure de l'uplift / élasticité exploratoire** | ✅ **Oui, encadrée** — observationnelle, jamais causale |
| **C. Prix optimal généralisable hors promotion** | ❌ **Non — et aucune donnée supplémentaire ne le débloquerait** |

Le blocage de C n'est pas une lacune de collecte : **0/300 produits ont changé de prix catalogue ; le
prix catalogue est fixe pour 300/300 produits**, vérifié à la fois sur la table analytique aplatie et
sur les versions SCD brutes de `dim_produit` relues en direct (300 lignes pour 300 `produit_key`, soit
exactement 1 version par produit, aucune jamais close ni remplacée — `reports/26_audit_pricing.md` §1).
Il n'existe donc aucune variation de prix catalogue à exploiter, quelle que soit la quantité de données
reçues en plus.

## 2. Variation de prix exploitable

- **Hors promotion** : amplitude du prix payé (bruit résiduel) = médiane **1,040** (±4 % environ),
  corrélation prix×quantité = **+0,024**, quasi nulle. **Ce bruit n'est jamais traité comme un signal
  de prix.**
- **En promotion** : 7 niveaux de remise réels (5/10/15/20/25/30/40 %), dont **40 % repose sur 11
  produit-jours d'un seul produit — inexploitable, exclu de toute estimation**.
- La seule variation de prix réellement exploitable est donc la **grille discrète des 6 niveaux
  5-30 %**, en intra-produit (avant/pendant/après une promotion), jamais en absolu entre produits
  différents.

## 3. Qualité du dataset

- 117 763 lignes produit×jour, 300 produits, coût/prix/promotion/CA renseignés à 100 % (0 valeur
  manquante sur les colonnes structurelles, cf. `reports/26_audit_pricing.md` §0).
- Marge calculable sur 57 977 lignes avec vente (coût unitaire connu pour tous les produits).
- Calendrier promotionnel déjà validé à 100 % rappel/précision lors de l'audit initial (rapport 11).
- Stock joint (`stock_disponible_lag1`, décalé) : 0 % de rupture détectable en fin de journée sur cette
  livraison — le contrôle stock ne modifie donc pas les constats, mais reste appliqué par principe (une
  rupture intrajournalière reste possible et non mesurable, même limite que pour le forecasting).

## 4. Produits éligibles

**Pour l'objectif B (uplift)** : 263/300 produits exposés à ≥2 niveaux de remise réels distincts
(recalculé indépendamment, cf. réconciliation terminologique §3 du rapport 26 — mêmes données que le
rapport 11, définition clarifiée). Support en jours de promotion pour ces produits éligibles : médiane
48 jours, min 11, max 118 — suffisant pour une comparaison intra-produit avant/pendant promotion, pas
pour une estimation fine par niveau isolé sur les produits à faible support.

**Pour l'objectif A (descriptif)** : les 300/300 produits, sans restriction.

## 5. Produits non éligibles

- **12/300** produits n'ont jamais été en promotion — exclus de toute analyse d'uplift (aucune
  variation à observer).
- **25/300** produits n'ont été exposés qu'à un seul niveau de remise — utilisables pour un uplift
  global « promo vs pas promo » mais pas pour une comparaison entre niveaux de remise.
- Le niveau de remise 40 % (1 seul produit, 11 lignes) est exclu de toute analyse par niveau, quel que
  soit le produit.

## 6. Marges négatives

- **679 lignes vendues à marge unitaire négative** (1,17 % des jours avec vente), sur **73 produits**
  distincts (`reports/26_audit_pricing.md` §6).
- Remise appliquée médiane sur ces lignes : **25 %** — cohérent arithmétiquement : une remise profonde
  sur un produit à faible marge catalogue peut passer sous le coût sans qu'il y ait d'erreur de données.
- **Contrainte dure retenue pour tout simulateur futur : ne jamais recommander une remise qui pousserait
  le prix sous le coût unitaire**, produit par produit (pas seulement en moyenne).

## 7. Biais possibles

- **Sélection de campagne** : rien n'indique que l'affectation produit→niveau de remise soit
  indépendante de la demande latente — non vérifiable sans le générateur (même réserve que le rapport
  11). Un uplift mesuré peut refléter en partie *pourquoi* un produit a été mis en promotion, pas
  seulement *l'effet* de la promotion.
- **Confusion catégorie × niveau de remise** : la remise moyenne varie fortement par catégorie (9,5 % en
  Maison & Cuisine à 20,4 % en Mode & Vêtements, `reports/26_audit_pricing.md` §9) — la relation
  remise↔marge du §7 de l'audit (marge moyenne décroissante avec le niveau de remise) peut refléter des
  différences de catégorie plutôt qu'un effet pur du niveau de remise. **Jamais interprétée comme un
  effet du taux de remise seul sans contrôle de catégorie.**
- **Rupture intrajournalière non mesurable** : une promotion en rupture partielle biaiserait l'uplift
  mesuré vers le bas — risque resté faible mais non nul (cf. rapport 11).
- **Jours avec vente seulement** : le prix payé n'existe que les jours de vente positive — tout effet
  mesuré sur le prix est conditionnel à `y > 0`, jamais sur l'ensemble des jours.

## 8. Modèle ou méthode recommandée

**Pour l'instant, aucun modèle causal** (pas de régression structurelle, pas de matching, pas
d'instrumentation) — la donnée ne le justifie pas et ce serait présenter une association comme un effet.

**Méthode recommandée pour un prototype V1** :
1. **Objectif A** : tableau de bord descriptif (CA, marge, taux de marge, couverture promotionnelle) par
   produit/catégorie/campagne — déjà entièrement calculable, aucun risque méthodologique.
2. **Objectif B** : comparaison **intra-produit**, avant/pendant/après promotion, par niveau de remise,
   avec contrôle explicite du jour de semaine et du mois (mêmes contrôles calendaires que le
   forecasting), intervalle de confiance par bootstrap sur les 263 produits éligibles, résultat présenté
   comme **« association observationnelle »**, jamais comme une élasticité causale. Le résultat
   exploratoire déjà mesuré au rapport 11 (pente log-log intra-produit −0,383, sans contrôle) sera
   recalculé avec les contrôles calendaires avant toute présentation comme résultat.
3. **Objectif C** : simulateur de remise **restreint à la grille des 6 niveaux observés (5-30 %)**, sous
   contrainte de marge minimale — pas de recherche d'un prix continu optimal.

## 9. Garde-fous (appliqués et à maintenir)

- Bruit hors-promotion (±4 %) jamais lu comme un signal de prix (§2).
- Aucune corrélation présentée comme un effet causal (§7 audit, §7 ci-dessus).
- `popularity_score` absent du dataset, et de toute façon exclu par principe.
- Stock contrôlé (décalé, jamais contemporain) partout où pertinent.
- Seules les informations disponibles au moment de la recommandation seraient utilisées par un futur
  simulateur.
- Validation temporelle systématique (split avant/après déjà appliqué en §10 de l'audit — corrélation
  stable dans le temps).
- Toute méthode comparée à une politique simple (« pas de remise » / « remise fixe uniforme ») avant
  d'être retenue.
- Aucune recommandation de prix sous le coût, produit par produit.
- Aucune publication Supabase, aucun déploiement.

## 10. Limites causales

- L'affectation des campagnes promotionnelles n'est pas randomisée et son mécanisme n'est pas
  documenté — **aucune méthode observationnelle ne peut le prouver, seulement le supposer**.
- Sans données de contrôle expérimental (A/B test prix) ou d'instrument valide, tout effet mesuré reste
  une **association**, quel que soit le raffinement statistique appliqué.
- La grille de remise (5 à 30 %) borne strictement le domaine de validité de toute conclusion — aucune
  extrapolation en dehors de cette grille.

## 11. Plan de validation

1. Recalcul de l'uplift intra-produit avec contrôles calendaires (jour de semaine, mois) sur les 263
   produits éligibles, split temporel (train sur la première moitié de la période, test sur la seconde,
   comme au §10 de l'audit) pour vérifier la stabilité du résultat avant toute présentation.
2. Comparaison systématique à deux politiques simples : « aucune remise » et « remise uniforme
   médiane » — un résultat n'est retenu que s'il apporte un gain mesurable par rapport à ces deux
   références.
3. Bootstrap par produit (pas par ligne, pour respecter la structure de série temporelle) pour les
   intervalles de confiance.
4. Vérification explicite, produit par produit, qu'aucune recommandation du simulateur de remise ne
   descend sous le coût unitaire connu.
5. Revue qualitative des 73 produits à marge négative avant toute inclusion dans un simulateur —
   certains peuvent nécessiter une exclusion metier (produits d'appel volontairement vendus à perte,
   information non disponible dans ce dataset).

---

**Ce document s'arrête ici pour validation, conformément à la méthodologie déjà appliquée en
forecasting. Le prototype pricing (comparaison de méthodes, simulateur de remise) ne sera construit
qu'après validation de ce livrable.**
