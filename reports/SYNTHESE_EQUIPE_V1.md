# Synthèse V1 — Forecasting, Pricing, Recommandation

_Document destiné aux équipes Data, métier et management. Généré le 2026-08-15. Tous les chiffres
ci-dessous ont été recoupés avec les métadonnées figées de chaque phase (`models/forecast_final/metadata.json`,
`reports/pricing_final/metadata.json`, `reports/recsys_final/metadata.json`) — aucun écart trouvé._

---

## 1. Contexte et objectif

Ce projet couvre trois axes indépendants, construits sur les mêmes données sources :

1. **Prévision des quantités vendues** (forecasting) — anticiper combien un produit va se vendre.
2. **Simulation de promotions et de prix** (pricing) — comprendre l'effet des remises et simuler des
   scénarios sous contrainte de marge.
3. **Recommandation de produits** — proposer des produits pertinents aux clients.

Les données proviennent de Supabase (base de données du projet). **Avant toute modélisation**, leur
qualité, leurs jointures entre tables et leur cohérence métier ont été auditées en profondeur — c'est
cet audit qui a déterminé ce qui était réellement faisable, plutôt que de partir d'hypothèses.

---

## 2. Données analysées

| Élément | Valeur |
|---|---|
| Clients | 5 000 |
| Produits | 300 |
| Lignes de vente (`fact_ventes`) | 85 419 |
| Historique | 546 jours |
| Observations produit-jour (table d'analyse) | 117 763 |
| Part de jours sans vente | 50,77 % |
| Observations de stock (`fact_stock`) | 117 763 (même volume que ci-dessus, deux tables distinctes) |
| Intégrité référentielle | Validée — aucune ligne orpheline entre les tables |
| Stock minimal observé | 21 unités — **aucune rupture de stock visible en fin de journée** dans les données disponibles |
| Grain d'une ligne de vente | Un produit vendu à un instant donné — **pas une commande complète** (plusieurs produits achetés ensemble ne peuvent pas être reliés entre eux dans ces données) |

_Aucune information de connexion, aucun identifiant technique, aucune donnée personnelle n'est reprise
dans ce document ni dans les rapports publiés._

---

## 3. Forecasting V1

**Modèle retenu :** AutoETS, avec un modèle de secours (Naive) pour les rares séries où AutoETS échoue.

**Usage recommandé : planification cumulée à 7, 14 ou 30 jours par produit.**

| Indicateur | Valeur |
|---|---|
| Erreur (WAPE) cumulée à 30 jours | **27,72 %** |
| Erreur (WAPE) cumulée à 7 jours | **46,2 %** |
| Erreur (WAPE) au jour le jour | **≈109 %** — nettement plus faible |
| Horizon 90 jours | Disponible, mais **expérimental, non validé** par nos tests |

**Limite principale :** beaucoup de produits ont une demande intermittente (environ 50 % de jours sans
aucune vente) et peu de « mémoire » d'un jour à l'autre — un modèle ne peut pas deviner avec précision
si un produit précis se vendra ou non un jour donné.

**Formulation métier :** le modèle est fiable pour anticiper des **volumes agrégés sur 30 jours**
(utile pour la planification, les commandes fournisseurs, le budget) — **il ne doit pas être utilisé
pour garantir la vente exacte d'un produit un jour précis.**

---

## 4. Pricing V1 (exploratoire)

**Constat de départ :** le prix catalogue n'a jamais varié pour aucun des 300 produits sur toute la
période observée. Seules les promotions ponctuelles offrent une variation de prix exploitable.

**Ce qui a été produit :** un simulateur de remises, contraint à ne jamais proposer une marge inférieure
à 5 %.

| Indicateur | Valeur |
|---|---|
| Simulations produites (plancher de marge 5 %) | **288** |
| Répartition des remises simulées | 240 produits à 0 %, 29 à 5 %, 17 à 10 %, 2 à 15 % |
| Remises simulées entre 20 % et 40 % | **Aucune** |
| Simulations sous le coût ou sous le plancher de marge | **Aucune** (garde-fou vérifié automatiquement) |
| Erreur (WAPE) sur la quantité prévue | **107,1 %** — élevée |
| Simulations en « confiance haute » | **Aucune** |
| Nature des résultats | **Observationnels, pas causaux** (une association mesurée, pas une preuve d'effet) |

**Formulation métier obligatoire : il s'agit d'un simulateur exploratoire fonctionnant sous garde-fous
stricts — pas d'un moteur de prix optimal, et pas d'un système qui appliquerait des remises
automatiquement.** Toute simulation doit être revue par une personne avant toute décision commerciale.

---

## 5. Recommandation V1

**Méthode retenue : popularité globale** (les produits les plus vendus, recommandés à tous les
clients). **La personnalisation par client a été testée et désactivée** — aucune méthode personnalisée
testée n'a apporté de gain suffisant et régulier.

| Indicateur | Valeur |
|---|---|
| Recall@10 (part des bons produits retrouvés dans le top 10) | **7,59 %** |
| NDCG@10 (qualité du classement) | **4,41 %** |
| Couverture du catalogue | **5,42 %** — donc **≈94,6 % du catalogue n'apparaît jamais** dans les recommandations |
| Méthode de secours | Popularité récente |
| Signal de navigation web et modèles personnalisés | Ne battent pas suffisamment la méthode simple retenue |

**Formulation métier :** la V1 peut alimenter un bloc générique de type **« Produits populaires »**
(page d'accueil, page catégorie) — **elle ne doit jamais être présentée comme une recommandation
personnalisée**, puisque tous les clients d'un même segment reçoivent la même liste.

---

## 6. Qualité et sécurité

- Validation temporelle stricte sur les trois modèles : chaque évaluation utilise uniquement des
  données antérieures à la date de prévision (aucune fuite d'information depuis le futur).
- Tests automatisés dédiés contre les fuites de données, en plus de la validation temporelle.
- **156 tests automatisés**, tous réussis.
- Résultats, métadonnées et manifestes d'intégrité archivés pour chacune des trois phases.
- **Aucun secret (clé, mot de passe, identifiant) publié.**
- **Aucune écriture dans Supabase.**
- **Aucun modèle déployé** à ce stade — tout reste au niveau de l'analyse et de la simulation.

---

## 7. Tableau de décision

| Module | Statut | Usage autorisé | Usage interdit |
|---|---|---|---|
| Forecasting | V1 validée | Planification cumulée, en priorité à 30 jours | Prévision exacte au jour le jour |
| Pricing | V1 exploratoire | Simulation et analyse, avec validation humaine systématique | Application automatique des remises, ou promesse de « prix optimal » |
| Recommandation | V1 baseline | Bloc générique de produits populaires | Recommandation présentée comme personnalisée |

---

## 8. Objectifs V2 (seuils d'acceptation à atteindre — pas des résultats déjà obtenus)

**Forecasting**
- WAPE cumulée à 30 jours ≤ 26,5 %
- Amélioration mesurable de la précision au jour le jour
- Recalibration des intervalles de prévision (actuellement trop étroits sur certains segments)

**Recommandation**
- Recall@10 ≥ 8 %
- NDCG@10 ≥ 4,7 %
- Couverture du catalogue ≥ 10 %

**Pricing**
- WAPE sur la quantité < 100 %
- Biais absolu ≤ 10 %
- Toujours : aucune violation du plancher de marge

**Collecte de données souhaitée pour la V2** : identifiant de commande (`order_id`), identifiant de
session web (`session_id`), horodatage précis des événements (`event_timestamp`), et mise en place
d'expérimentations promotionnelles contrôlées (tests A/B) pour valider un effet réel, pas seulement une
association statistique.

---

## 9. Décisions attendues de l'équipe

1. **Valider l'usage du forecasting** pour la planification mensuelle (cumul 30 jours).
2. **Valider le positionnement exploratoire du pricing** — outil d'aide à la décision, jamais
   d'application automatique.
3. **Trancher un choix métier sur la recommandation** : faut-il exclure les produits déjà achetés
   (logique de découverte) ou les autoriser (logique de réapprovisionnement) ? Les deux scénarios ont
   été mesurés et sont comparables sur demande.
4. **Donner un accord sur les objectifs V2** proposés ci-dessus (section 8).
5. **Confirmer qu'aucun déploiement n'aura lieu avant validation métier explicite** des trois modules.

---

_Rapports détaillés, métadonnées et manifestes disponibles dans le dépôt :
[github.com/younesda/EXAMEN_DATA_DRIVEN](https://github.com/younesda/EXAMEN_DATA_DRIVEN)_
