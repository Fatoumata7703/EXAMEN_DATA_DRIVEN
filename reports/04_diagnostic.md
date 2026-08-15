# 04 — Diagnostic avant modélisation

_Établi le 2026-08-13, à partir de l'audit lecture seule de la base Supabase
`dvpeohgzhdrkpmqnzpkh` (schéma `public`, backend REST)._

Tous les chiffres de ce document proviennent de l'exécution de
`python -m src.pipelines.audit` puis `python -m src.pipelines.prepare`.
Aucune valeur n'est illustrative.

---

## 1. Schéma réel découvert

Modèle en étoile, 6 tables, 461 177 lignes au total.

| Table | Lignes | Colonnes |
|---|---:|---|
| `fact_ventes` | 85 419 | `vente_id`, `produit_key`, `client_key`, `date_key`, `promo_key`, `quantite`, `montant_net_xof` |
| `fact_evenements_web` | 374 792 | `event_id`, `produit_key`, `client_key`, `date_key`, `type_event`, `device` |
| `dim_client` | 5 000 | `client_key`, `customer_id`, `region`, `age_bracket`, `segment_fidelite`, `valid_from`, `valid_to`, `is_current` |
| `dim_date` | 546 | `date_key`, `date_complete`, `annee`, `mois`, `jour`, `jour_semaine`, `est_weekend` |
| `dim_produit` | 300 | `produit_key`, `product_id`, `product_name`, `categorie`, `marque`, `prix_base_xof`, `cout_xof`, `valid_from`, `valid_to`, `is_current` |
| `dim_promotion` | 120 | `promo_key`, `promotion_id`, `scope`, `cible`, `remise_pct`, `start_date`, `end_date` |

### Relations réelles — déclarées dans la base **et** vérifiées sur les données

> **Correction du 2026-08-13.** Une version précédente de ce rapport affirmait
> qu'aucune contrainte de clé étrangère n'était déclarée. C'était faux : l'API
> de données ne les expose pas, mais **PostgREST publie un schéma OpenAPI** à la
> racine de l'API qui porte les types PostgreSQL réels ainsi que les clés
> primaires et étrangères. Les 7 clés étrangères ci-dessous sont **déclarées
> dans la base**. Le rapport de schéma les lit désormais au lieu de les deviner.

Les relations sont donc doublement établies : déclarées dans le catalogue, et
confirmées sur les données par recouvrement de valeurs.

| Relation | Clé de jointure | Recouvrement | Orphelines |
|---|---|---:|---:|
| `fact_ventes` → `dim_produit` | `produit_key` | 100 % | 0 / 300 |
| `fact_ventes` → `dim_client` | `client_key` | 100 % | 0 / 5 000 |
| `fact_ventes` → `dim_promotion` | `promo_key` | 100 % | 0 / 97 |
| `fact_ventes` → `dim_date` | `date_key` | 100 % | 0 / 546 |
| `fact_evenements_web` → `dim_produit` | `produit_key` | 100 % | 0 / 300 |

> **Piège identifié.** Chaque dimension porte à la fois une **clé de substitution**
> (`produit_key` = `PRD000091`, `promo_key` = `PRM0095`) et une **clé naturelle**
> (`product_id` = `P00049`, `promotion_id` = `PROMO0001`). Seule la première joint
> avec les faits. Une première version de l'audit comparait la clé naturelle et
> concluait à tort à « 100 % de clés orphelines ». Le mapping est désormais résolu
> par recouvrement de valeurs, et non par ressemblance de nom.
>
> Conséquence directe : les promotions à portée `product` ciblent la clé
> **naturelle** (`cible` = `P00049`), pas la clé de substitution. Le calendrier
> promotionnel doit donc joindre sur `dim_produit.product_id`, tandis que les
> ventes joignent sur `dim_produit.produit_key`.

### Granularité réelle de `fact_ventes`

Une ligne = **une transaction** (`vente_id` unique sur 85 419 lignes), rattachée à
un produit, un client, un jour, et facultativement une promotion. Il y a en
moyenne 1,47 transaction par couple produit×jour actif (max 8). La table n'est
donc **pas** déjà agrégée : l'agrégation produit×jour est une étape à part entière.

### Signification métier des grandeurs

| Grandeur | Colonne | Constat |
|---|---|---|
| Quantité | `quantite` | entier de **1 à 5**, moyenne 1,82. Aucun zéro, aucune valeur négative. |
| Chiffre d'affaires ligne | `montant_net_xof` | 499 à 2 284 000 XOF. « net » confirmé : le montant est net de remise. |
| Prix unitaire | *absent des faits* | vit dans `dim_produit.prix_base_xof` (prix catalogue). |
| Remise | *absente des faits* | vit dans `dim_promotion.remise_pct` (5 % à 40 %). |
| Coût | `dim_produit.cout_xof` | présent, non utilisé pour la prévision de la demande. |
| Annulations / retours | **aucune colonne** | voir §2. |

**Cohérence quantité × prix × (1 − remise) vs chiffre d'affaires : validée.**
100 % des 85 419 lignes concordent à ±5 %. Le ratio réel/attendu est uniformément
réparti entre 0,9800 et 1,0200 autour d'une médiane de 1,0000 : il s'agit d'un
bruit multiplicatif borné à ±2 % (arrondi ou micro-variation de prix), pas d'une
incohérence de définition. La formule retenue est donc :

```
montant_net_xof ≈ quantite × prix_base_xof × (1 − remise_pct / 100)
```

> À noter : une première mesure avec une tolérance figée à 1 % annonçait « 49,9 %
> de concordance », un verdict trompeur puisque le bruit réel est de ±2 %. Le
> contrôle mesure désormais la concordance à plusieurs tolérances et décrit la
> distribution du ratio.

---

## 2. Problèmes de qualité détectés

Bilan de l'audit : **0 point critique, 2 alertes, 1 point non applicable** sur 24 contrôles.

### Ce qui est propre

- **Aucun doublon** : `vente_id`, `event_id`, `client_key`, `date_key`,
  `product_id`, `promotion_id` sont tous uniques.
- **Aucune valeur manquante** sur les colonnes indispensables (date, produit,
  quantité, montant).
- **Aucune rupture de calendrier** : 546 jours consécutifs du 2025-02-01 au
  2026-07-31, 100 % couverts, écart modal de 1 jour.
- **Aucune valeur négative ni nulle** sur quantité, montant, prix, remise.
- **Intégrité référentielle parfaite** sur les 7 relations déclarées : 0 clé orpheline.
- **Fenêtres promotionnelles cohérentes** : 100 % des 13 380 ventes promues
  tombent dans la fenêtre `[start_date, end_date]` déclarée.

### Alertes

| Point | Constat | Interprétation |
|---|---|---|
| `dim_client.valid_to` | 100 % vide | SCD de type 2 dont toutes les lignes sont courantes (`is_current = true`). Structurel, sans impact sur la cible, mais inutilisable comme variable. |
| `dim_produit.valid_to` | 100 % vide | Idem. |
| Jour atypique | 2025-12-28, z robuste = 3,03 | 1 jour sur 546 (0,2 %). Statistiquement attendu à ce seuil ; à conserver (pic de fin d'année réel, pas une anomalie de saisie). |

### Point non applicable — et c'est le manque d'information le plus important

**Il n'existe aucune trace d'annulation ni de retour dans la base.** Pas de
colonne de statut, pas d'indicateur de retour, aucune quantité négative, aucun
montant négatif, aucun zéro. Trois lectures possibles, que les données seules ne
permettent pas de distinguer :

1. le périmètre ne comporte réellement ni annulation ni retour ;
2. `fact_ventes` ne contient que les ventes **déjà validées**, les autres étant
   filtrées en amont ;
3. les retours sont tracés dans un système non exposé ici.

**Hypothèse retenue, configurable :** quantité nette = quantité brute. Elle est
inscrite dans `config/config.yaml` (`target.name: quantite_vendue_observee`) et rappelée
dans chaque rapport. Si la lecture 2 ou 3 est la bonne, la cible actuelle
**surestime** la demande nette et devra être recalculée.

### Deux limites de contexte, indépendantes de la qualité

- **Fraîcheur** : l'historique s'arrête au 2026-07-31, soit 13 jours avant la date
  de cet audit. Toute prévision produite aujourd'hui démarre donc avec 13 jours
  d'angle mort. À traiter par un rafraîchissement de l'extraction avant mise en
  production.
- **Backend REST** : le schéma OpenAPI de PostgREST fournit les types réels et
  les clés déclarées, mais **pas les commentaires de colonnes**. C'est
  précisément ce qui empêche de prouver la signification de `valid_from` (§3).
  Une connexion PostgreSQL directe (`DATABASE_URL`) donnerait accès à
  `information_schema` et aux commentaires.

---

## 3. Cible et granularité retenues

> **Formulation de la cible.** `y` est la **quantité vendue observée**, et non
> « la demande réelle ». Sans donnée de stock, de disponibilité ou de rupture,
> un `y = 0` est indistinguable entre absence de demande et impossibilité
> d'acheter : la demande censurée par une rupture est invisible. Cette
> distinction est inscrite dans `config/config.yaml`
> (`target.name: quantite_vendue_observee`) et doit accompagner toute
> restitution des prévisions.

| Décision | Valeur | Justification tirée des données |
|---|---|---|
| **Cible** `y` | quantité vendue observée = `SUM(quantite)` | Seule quantité disponible ; aucune annulation ni retour à déduire (§2). |
| **Granularité** | **produit × jour** | `fact_ventes` est transactionnelle et `date_key` est journalier : la granularité produit×jour est atteignable sans agrégation dégradante. 300 séries. |
| **Fréquence** | **journalière (`D`)** | 546 jours distincts sur 546, écart modal 1 jour, 100 % de couverture. Confirmée par les données, pas supposée. |
| **Identifiant de série** | `produit_key` | 300 `produit_key` pour 300 `product_id` : correspondance 1:1, aucune historisation SCD active. Les deux conviennent ; la clé de substitution est celle qui joint aux faits. |
| **Saisonnalité principale** | 7 jours | Effet week-end net et régulier (§5). |

### Complétion par des zéros : périmètre strictement borné (règle A)

La table analytique compte **117 763 lignes**, et non 300 × 546 = 163 800. La
différence de 46 037 lignes est délibérée :

- borne gauche = **`max(début de validité du produit, première date des
  données)`**, plafonnée par la première vente observée ;
- borne droite = **dernière date globale de l'historique** (2026-07-31),
  identique pour toutes les séries.

L'écrêtage à la première date des données est essentiel : 120 produits ont un
début de validité antérieur au 2025-02-01 (jusqu'à 365 jours avant). Y écrire
des zéros reviendrait à **affirmer une absence de vente là où aucune
observation n'existe**. La borne droite commune évite pour sa part un biais de
survie : s'arrêter à la dernière vente de chaque produit empêcherait le modèle
d'apprendre qu'une fin de période peut être vide.

Hors de cette fenêtre, il n'y a pas « vente = 0 » mais **absence
d'observation** : aucune ligne n'est créée.

> **Sur la signification de `valid_from` — hypothèse, non certitude.** Aucune
> preuve n'a pu être établie : la base ne porte aucun commentaire de colonne, et
> il n'existe ni migration ni documentation. Le faisceau d'indices est partagé.
> *Pour* une date de mise en vente : aucune des 85 419 ventes ne la précède, et
> pour les 180 produits dont elle tombe dans la fenêtre de données, l'écart
> médian avec la première vente est de **1 jour** (98,3 % sous 7 jours). *Pour*
> une simple date de validité SCD : le triplet `valid_from`/`valid_to`/
> `is_current` est canonique, et `dim_client` porte exactement le même — or une
> « date de lancement » n'a aucun sens pour un client. L'hypothèse d'une date de
> création en masse est en revanche écartée (254 dates distinctes pour 300
> produits).
>
> En conséquence, la colonne est exposée sous le nom neutre
> **`date_debut_validite`**, jamais `date_lancement`, et `age_produit_jours` est
> défini comme « jours écoulés depuis `date_debut_validite` ». Elle est utilisée
> comme **meilleure approximation disponible** de la disponibilité commerciale.

Les quatre situations que le cahier des charges demande de ne pas confondre sont
ainsi distinguées :

| Situation | Traitement |
|---|---|
| Produit pas encore lancé | aucune ligne (hors fenêtre d'activité) |
| Jour sans vente d'un produit lancé | ligne avec `y = 0` |
| Vente effective | ligne avec `y > 0` |
| Rupture de stock / indisponibilité | **indistinguable** — voir §10 |

**50,77 % des couples produit×jour de la fenêtre d'activité sont à zéro.** Ce n'est
donc pas un détail de traitement : c'est la caractéristique dominante des séries.

### Colonnes de la table analytique

`data/processed/table_analytique.parquet` — 117 763 × 23.

| Colonne | Nature | Connue à l'avance ? |
|---|---|---|
| `unique_id`, `ds`, `y` | identifiant, date, cible | — |
| `ca`, `n_transactions` | chiffre d'affaires, nb de transactions du jour | non (a posteriori) |
| `categorie`, `marque`, `libelle`, `product_id` | attributs produit | oui (statiques) |
| `prix_catalogue` | `prix_base_xof` | oui |
| `prix_realise` | `ca / y`, manquant les jours sans vente | **non** (dérivé de la vente) |
| `prix_attendu` | `prix_catalogue × (1 − remise/100)` | oui |
| `en_promotion`, `remise_pct`, `n_promotions`, `portee_promo` | calendrier promotionnel | **oui** (promos planifiées) |
| `date_debut_validite`, `age_produit_jours` | cycle de vie produit | oui |
| `web_view`, `web_add_to_cart`, `web_purchase`, `web_total` | événements web du jour | **non** (voir §7) |
| `web_data_observed` | 1 = suivi web actif, 0 = aucune donnée | oui |

`web_data_observed` distingue deux situations que le remplissage par zéro
confondait : **aucun événement observé** (21 565 produit-jours à l'intérieur de
la fenêtre de suivi — un vrai zéro) et **aucune donnée disponible** (93
produit-jours hors fenêtre de suivi, où les compteurs valent `NaN` et non 0).

**Absent du schéma : la sous-catégorie.** Le cahier des charges la demande ; elle
n'existe pas. La hiérarchie disponible est `categorie` (8 modalités) → `marque`.
Aucun proxy n'a été inventé.

### Le calendrier promotionnel est reconstruit, pas lu

`fact_ventes.promo_key` ne suffit pas comme indicateur de promotion, pour deux
raisons dirimantes :

1. **les jours sans vente n'ont pas de ligne** : l'information « ce produit était
   en promotion » disparaîtrait exactement là où elle est la plus informative
   (une promotion sans vente est un signal, pas une absence de signal) ;
2. **la clé de promotion d'une vente future est inconnue** : impossible de
   prévoir avec elle. En revanche une promotion *planifiée* a des dates connues.

Le calendrier est donc déplié depuis `dim_promotion` (portée + cible + fenêtre) :
63 promotions à portée `category` (cible = nom de catégorie) et 57 à portée
`product` (cible = `product_id`), de 4 à 15 jours (médiane 9), soit **22 245
couples produit×jour en promotion**.

**Validation contre les faits : rappel 100 %, précision 100 %.** Les 13 380 ventes
marquées en promotion sont toutes couvertes par le calendrier reconstruit, et
tout couple produit×jour couvert qui porte une vente porte bien une promotion.
Règle en cas de promotions concurrentes : **la remise la plus forte l'emporte**
(hypothèse configurable, `n_promotions` conservé comme variable).

---

## 4. Justification de l'horizon

L'historique utile est de **546 jours (17,9 mois)**.

| Horizon | Fenêtres de backtest possibles | Jours d'entraînement minimaux | Verdict |
|---:|---:|---:|---|
| 7 j | 6 (pas de 7 j) | 504 | confortable |
| 14 j | 6 (pas de 14 j) | 462 | confortable |
| **30 j** | **6 (pas de 30 j)** | **366** | **retenu comme horizon principal** |
| 90 j | 3 (pas de 90 j) | 276 | produit, mais fragile — voir ci-dessous |

**Horizon principal retenu : h = 30 jours, 6 fenêtres glissantes**, avec
entraînement strictement antérieur à chaque fenêtre de test. C'est le meilleur
compromis : 366 jours d'entraînement au minimum (soit plus d'un an, ce qui couvre
un cycle annuel complet) et 6 fenêtres, assez pour que la comparaison entre
modèles ne dépende pas d'une période particulière.

Les horizons 7, 14 et 90 jours sont produits en sortie, mais avec une réserve
explicite sur 90 jours : trois fenêtres seulement, et un entraînement pouvant
descendre à 276 jours, ce qui ne couvre pas une année entière.

**Réserve majeure sur la saisonnalité annuelle.** L'historique ne contient
**qu'un seul pic de fin d'année** (novembre 2025 : moyenne 1,66 unité/produit/jour ;
décembre 2025 : 1,98 ; contre une base de 1,20 à 1,30 le reste de l'année, soit
+55 % en décembre). Un effet annuel observé une seule fois **ne peut pas être
validé par validation croisée temporelle** : aucune fenêtre de test ne peut à la
fois contenir un décembre et être précédée d'un entraînement qui en contient un
autre. Toute prévision couvrant novembre-décembre 2026 repose donc sur une
extrapolation non validée, et doit être signalée comme telle. Concrètement, une
prévision à 90 jours émise à partir du 2026-07-31 s'arrête fin octobre et
n'atteint pas le pic — mais la même prévision émise en septembre y entrerait.

---

## 5. Structure temporelle observée

### Saisonnalité hebdomadaire — réelle et exploitable

Moyenne de `y` rapportée à la moyenne générale :

| Lun | Mar | Mer | Jeu | Ven | Sam | Dim |
|---:|---:|---:|---:|---:|---:|---:|
| 0,93 | 0,95 | 0,92 | 0,92 | 0,93 | **1,16** | **1,18** |

Le week-end pèse environ **+25 %** par rapport aux jours de semaine. C'est le
signal calendaire le plus net, et il est intégralement connu à l'avance.

### Effet promotionnel — réel et modéré

- Toutes séries confondues : `y` moyen de 1,29 hors promotion contre **1,57 en
  promotion**, soit +21 %.
- En comparaison **intra-produit** (288 produits observés dans les deux états) :
  uplift médian **×1,23**, moyen ×1,25.

L'effet est donc cohérent aux deux niveaux d'analyse, ce qui le rend crédible.
Couverture : 13,2 % des lignes produit×jour, 96 % des produits concernés au moins
une fois, 76 % des jours.

### Autocorrélation — et c'est le résultat déterminant

| Décalage | 1 j | 7 j | 14 j | 28 j | 364 j |
|---|---:|---:|---:|---:|---:|
| Corrélation `y(t)` ~ `y(t−k)` | **+0,095** | +0,091 | +0,085 | +0,079 | +0,084 |

**Les séries produit×jour sont pratiquement sans mémoire.** L'autocorrélation est
d'environ 0,09 quel que soit le décalage — c'est-à-dire qu'elle ne décroît pas,
signe qu'elle ne reflète pas une dynamique temporelle mais seulement le fait que
les produits n'ont pas tous le même niveau moyen.

Ce constat gouverne toute la suite. Avec une moyenne de 1,33 unité par
produit-jour, 50,8 % de zéros et un maximum de 20, le signal quotidien au niveau
produit est **dominé par du bruit de comptage** (de type Poisson). Il faut donc
s'attendre à ce que :

- les variables de retard et de moyenne mobile apportent **peu** ;
- la part réellement prévisible se réduise au **niveau moyen du produit**, à
  l'**effet week-end**, à l'**effet promotion** et à la **saisonnalité de fin
  d'année** ;
- un modèle global sophistiqué ne batte les baselines que d'une marge modeste.

Ce n'est pas une raison de renoncer, mais une raison de **mesurer avant
d'affirmer**. Aucun modèle ne sera présenté comme performant sans backtesting, et
l'écart avec la baseline sera rapporté tel quel, même s'il est faible.

### Concentration du chiffre d'affaires

| Part du CA | Nombre de produits | Part du portefeuille |
|---|---:|---:|
| 50 % | 25 | 8 % |
| 80 % | 74 | 25 % |
| 95 % | 169 | 56 % |

Pareto classique : un quart des produits porte 80 % du chiffre d'affaires. Les
métriques de backtesting seront donc **pondérées par le volume et par le CA**, et
ventilées par classe ABC : une erreur sur un produit A ne coûte pas ce que coûte
la même erreur sur un produit C.

---

## 6. Typologie des séries

Classification Syntetos-Boylan-Croston, calculée **sur la grille complétée**
(zéros inclus dans la fenêtre d'activité) — la calculer sur les seuls jours de
vente sous-estimerait mécaniquement l'intermittence.

| Indicateur | Médiane | 5 % – 95 % |
|---|---:|---|
| ADI (intervalle moyen entre deux ventes) | 2,07 | 1,41 – 3,35 |
| CV² (dispersion des tailles de demande) | 0,50 | 0,39 – 0,60 |
| CV de la série complète | 1,45 | 1,05 – 2,02 |
| Taux de jours sans vente | 51,6 % | 29,3 % – 70,1 % |

### Profil de demande

| Profil | Séries | Part | Part du volume |
|---|---:|---:|---:|
| Grumeleux (*lumpy*) | 166 | 55,3 % | 59,5 % |
| Intermittent | 129 | 43,0 % | 38,3 % |
| Erratique | 4 | 1,3 % | 2,2 % |
| Régulier | **1** | 0,3 % | 0,1 % |

> **Lecture honnête de ce tableau.** La distinction entre « intermittent » et
> « grumeleux » n'a ici presque aucune portée : elle dépend du seul franchissement
> du seuil CV² = 0,49, alors que le CV² de l'ensemble du portefeuille est
> concentré autour de 0,50 (5 %–95 % : 0,39–0,60). Le fait marquant n'est pas la
> répartition entre ces deux cases, mais que **l'ADI médian soit de 2,07, très
> au-dessus du seuil de 1,32** : le portefeuille est intermittent dans sa
> quasi-totalité. Une seule série sur 300 est régulière.

### Cycle de vie

| Statut | Séries | Part | Part du volume |
|---|---:|---:|---:|
| Actif | 283 | 94,3 % | 99,2 % |
| Nouveau (< 90 jours de fenêtre) | 17 | 5,7 % | 0,8 % |
| Inactif / abandonné | **0** | 0 % | 0 % |

**Aucun produit abandonné** : les 300 produits ont vendu dans les 15 derniers
jours de l'historique. En revanche, le portefeuille se renouvelle vite : 62
produits ont été lancés après le 2026-01-01, 53 ont moins de 180 jours de
fenêtre d'activité et 17 moins de 90 jours. Le **démarrage à froid** est donc un
cas courant, pas marginal.

### Valeur (ABC) et régularité (XYZ)

| Classe ABC | Séries | Part | Part du CA |
|---|---:|---:|---:|
| A | 73 | 24,3 % | 80 % |
| B | 95 | 31,7 % | 15 % |
| C | 132 | 44,0 % | 5 % |

| | X | Y | Z |
|---|---:|---:|---:|
| A | 0 | 2 | 71 |
| B | 0 | 1 | 94 |
| C | 0 | 3 | 129 |

> **L'axe XYZ est dégénéré à cette granularité** : 294 séries sur 300 sont en
> classe Z (CV > 1), conséquence directe du taux de zéros. Il ne discrimine rien
> et ne sera pas utilisé comme axe d'analyse ; ABC, lui, est informatif. La
> matrice est reproduite par exigence de complétude, avec cette réserve.

### Groupes de stratégie (à confirmer par le backtesting)

| Groupe | Séries | Part du volume | Modèles candidats |
|---|---:|---:|---|
| `intermittent` | 279 | 97,0 % | Croston / TSB, Seasonal Naive, LightGBM Tweedie |
| `standard` | 4 | 2,2 % | LightGBM, ETS, ARIMA |
| `demarrage_a_froid` | 17 | 0,8 % | moyenne catégorie / produits similaires |

Ces affectations sont des **hypothèses de départ**. Le choix final se fera sur les
résultats mesurés, groupe par groupe.

---

## 7. Risques de fuite de données identifiés

| # | Risque | Statut | Traitement |
|---|---|---|---|
| 1 | **`web_purchase` est un miroir de la vente** : égal à `n_transactions` dans **80,1 %** des cas, corrélation 0,844. L'utiliser au jour J revient à donner la réponse au modèle. | **identifié, à neutraliser** | Toute variable web est décalée d'au moins 1 pas. Décalée, sa corrélation avec `y` retombe à 0,088 — l'apport réel est marginal, ce qui confirme que la corrélation brute était de la fuite. |
| 2 | `prix_realise` = `ca / y` : dérivé de la vente du jour. | identifié | Exclu des variables explicatives au jour J ; seul `prix_attendu` (catalogue × remise planifiée) est connu à l'avance. |
| 3 | `ca` et `n_transactions` sont contemporains de la cible. | identifié | Traités comme historiques, décalés. |
| 4 | Dénominateur de la MASE calculé sur le test. | évité par construction | `compute_train_scales()` ne voit que l'entraînement. |
| 5 | Statistiques de normalisation ou d'encodage calculées sur l'ensemble des données. | à surveiller | LightGBM n'exige pas de normalisation ; les catégories sont encodées en `category` sans statistique issue de la cible. |
| 6 | Complétion par zéros au-delà de la dernière date connue. | évité | La grille s'arrête à `max(ds)` de l'historique. |
| 7 | Promotions futures traitées comme connues. | **assumé et documenté** | Une promotion planifiée *est* connue à l'avance : c'est une variable exogène future légitime. En revanche, si en production le calendrier promo n'est pas figé à l'avance, cette hypothèse tombe et la variable devra être mise à zéro sur l'horizon. |

**Séparation des trois natures de variables**, telle qu'elle sera implémentée :

- **futures connues** : calendrier (jour, semaine, mois, week-end, fériés
  sénégalais, Ramadan/Korité/Tabaski/Magal), promotions planifiées, prix attendu,
  âge du produit, attributs produit ;
- **historiques** : `y` et ses retards/moyennes mobiles, `ca`, `n_transactions`,
  prix réalisé — tous décalés d'au moins 1 jour ;
- **futures inconnues** : événements web. Jamais utilisés à leur valeur future ;
  seuls leurs agrégats passés décalés entrent dans le modèle.

---

## 8. Ce que je vais faire maintenant

1. **Baselines** (phase 3) : Naive, Seasonal Naive (7 j), moyenne mobile, AutoETS,
   AutoARIMA, Croston optimisé, TSB — évalués en validation temporelle glissante,
   h = 30, 6 fenêtres.
2. **Modèle global** (phase 4) : LightGBM via MLForecast, objectif Tweedie/Poisson
   adapté à des comptages faibles avec 50 % de zéros, features décalées, puis
   optimisation Optuna et challenger CatBoost.
3. **Sélection** (phase 5) sur les résultats mesurés, ventilée par horizon,
   catégorie, classe ABC et profil de demande.
4. **Réseaux de neurones** : non prévus à ce stade. 300 séries et 18 mois
   d'historique ne justifient pas leur complexité, et l'autocorrélation quasi
   nulle indique qu'il n'y a pas de dynamique temporelle riche à capturer. Cette
   décision sera réexaminée si LightGBM montre un gain net sur les baselines.
5. **Variante hebdomadaire** : au vu de la faiblesse du signal quotidien, une
   agrégation produit×semaine sera évaluée en parallèle. Si elle s'avère nettement
   plus prévisible, elle sera proposée comme granularité alternative — sans
   remplacer la livraison journalière demandée.

---

## 9. Informations métier encore nécessaires

Par ordre d'impact sur la qualité du résultat :

1. **Annulations et retours** — `fact_ventes` contient-elle uniquement des ventes
   validées ? Existe-t-il une source de retours ailleurs ? Impact : la définition
   même de la cible.
2. **Ruptures de stock** — un `y = 0` signifie-t-il « pas de demande » ou
   « produit indisponible » ? Sans donnée de stock ou de disponibilité, un modèle
   entraîné sur des zéros de rupture apprend à prévoir l'absence d'offre plutôt
   que la demande. C'est la limite structurelle la plus sérieuse de ce jeu de
   données, et elle est **invisible** dans les données actuelles.
3. **Calendrier promotionnel futur** — les promotions sont-elles arrêtées à
   l'avance et disponibles au moment de la prévision ? Si non, la variable promo
   doit être neutralisée sur l'horizon.
4. **Usage métier de la prévision** — réapprovisionnement, budget, staffing ? Cela
   détermine s'il faut minimiser l'erreur symétrique (WAPE) ou pénaliser
   davantage la sous-prévision (rupture) que la sur-prévision (surstock).
5. **Sous-catégorie** — existe-t-elle dans le système source ? Elle est demandée
   au cahier des charges et absente du schéma.
6. **Périmètre** — 300 produits et 5 000 clients sur 18 mois : s'agit-il d'un
   extrait de démonstration ou du périmètre réel ? Cela conditionne la
   généralisation des conclusions.

---

_Références : `reports/01_schema.md` (schéma détaillé), `reports/02_audit_qualite.md`
(24 contrôles), `reports/audit_snapshot.json` (résultats bruts),
`reports/03_table_analytique.json` (construction de la table)._
