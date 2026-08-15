# 07 — Reprise de la chaîne data à partir des documents du data engineer

_Établi le 2026-08-13. Sources de référence : `DATA_DICTIONARY.md` et
`Architecture_Technique_Schema_Donnees.docx` (Downloads), confrontés aux
6 tables réellement exposées par Supabase._

Chiffres issus de `scripts/diagnostic_sources.py`. Aucune valeur illustrative.

---

## 1. Ce que les deux documents apportent réellement

### Éléments décisifs — qui changent la modélisation

| Information | Source | Conséquence |
|---|---|---|
| `stock_daily` existe (~118 000 lignes, grain produit × jour) | dictionnaire | **Les zéros ne sont pas tous de la demande nulle** |
| « si le stock tombe à 0, les ventes du produit s'arrêtent ce jour-là » | dictionnaire | Censure de la demande, non modélisable sans le stock |
| `stock_level` = **fin de journée**, réappro auto sous 20 unités | dictionnaire | Seul `stock_level(J-1)` est utilisable pour prévoir J |
| `dim_products.launch_date` = « produit absent des ventes avant cette date » | dictionnaire | **La vraie date de lancement existe** — `valid_from` n'est pas elle |
| `produit_key` « change à chaque nouvelle version du produit » | architecture | L'identifiant stable de série est `product_id` |
| `popularity_score` = « facteur de demande de base, utilisé pour la simulation » | dictionnaire | **Fuite de conception** : paramètre latent du générateur |
| `unit_price_xof` = « prix réellement payé, remise déjà appliquée » | dictionnaire | Explique le bruit de ±2 % ; prix payé reconstituable |
| `cost_xof` présent, marge 15 % à 55 % selon catégorie | dictionnaire | Marge calculable → pricing possible |
| Promo agit sur **λ du tirage Poisson** (nombre de commandes), pas sur la quantité par commande | dictionnaire | L'effet promo passe par la fréquence d'achat |
| Grain `fact_transactions` = 1 ligne par produit dans une commande | les deux | `n_transactions` ≠ nombre de commandes |
| Effet week-end +25 %, saisonnalité mensuelle par catégorie | dictionnaire | **Confirme mes mesures** (samedi 1,16 / dimanche 1,18) |

### Éléments confirmant l'audit précédent

- Période 2025-02-01 → 2026-07-31, 546 jours : **conforme**.
- 300 produits, 5 000 clients, 120 promotions : **conforme**.
- Électronique en pic novembre-décembre : **conforme** (décembre +55 % mesuré).
- SCD Type 2 sur `dim_produit` et `dim_client` : **structurellement conforme**.

---

## 2. Matrice de correspondance Raw → Supabase

Zones Bronze/Silver/Gold : **décrites dans l'architecture mais aucun artefact
n'est accessible** (ni fichier, ni bucket Storage, ni schéma Supabase). La
colonne correspondante est donc renseignée « non observable ».

### `dim_products` → `dim_produit`

| Colonne source | Type source | Supabase | Type cible | Transformation | Forecasting | Pricing | Reco | BI |
|---|---|---|---|---|---|---|---|---|
| `product_id` | string PK | `product_id` | text | conservé, **plus PK** (SCD2) | ✅ identifiant série | ✅ | ✅ | ✅ |
| — | — | `produit_key` | text **PK** | **créée** : clé de substitution SCD2 | jointure version | jointure | jointure | jointure |
| `product_name` | string | `product_name` | text | renommage nul | — | — | ✅ | ✅ |
| `category` | string | `categorie` | text | renommé + **casse normalisée** (15 lignes) | ✅ | ✅ | ✅ | ✅ |
| `brand` | string | `marque` | text | renommé | ✅ | ✅ | ✅ | ✅ |
| `base_price_xof` | float | `prix_base_xof` | numeric | renommé | ✅ | ✅ | — | ✅ |
| `cost_xof` | float | `cout_xof` | numeric | renommé | — | ✅ **marge** | — | ✅ |
| `popularity_score` | float | **ABSENT** | — | **supprimé** | 🚫 fuite | 🚫 | — | — |
| `launch_date` | date | **ABSENT** | — | **perdu** | ❌ **bloquant** | ❌ | ❌ | ❌ |
| `initial_stock` | int | **ABSENT** | — | **perdu** | ❌ | ❌ | — | — |
| — | — | `valid_from`/`valid_to`/`is_current` | date/date/bool | **créées** (SCD2) | version | version | — | — |

### `dim_customers` → `dim_client`

| Colonne source | Supabase | Transformation | Usage |
|---|---|---|---|
| `customer_id` | `customer_id` | conservé, plus PK | reco, BI |
| — | `client_key` **PK** | créée (SCD2) | jointures |
| `full_name` | **ABSENT** | supprimé (RGPD probable) | — |
| `region` | `region` | **nulls imputés par `Non renseigné`** (11 modalités) | reco, BI |
| `age_bracket` | `age_bracket` | idem (6 modalités) | reco, BI |
| `signup_date` | **ABSENT** | perdu | contrôle « événement avant inscription » impossible |
| `loyalty_segment` | `segment_fidelite` | renommé, 4 modalités | reco, BI |

### `fact_transactions` → `fact_ventes`

| Colonne source | Supabase | Transformation | Usage |
|---|---|---|---|
| `order_id` | **ABSENT** | remplacé par `vente_id` | ❌ nombre de commandes non calculable |
| — | `vente_id` **PK** | créée, unique sur 85 419 | clé de ligne |
| `customer_id` | `client_key` | → clé de substitution | reco |
| `product_id` | `produit_key` | → clé de substitution ; **42 orphelines P99999 retirées** | ✅ |
| `order_date` | `date_key` | → texte `AAAAMMJJ`, FK `dim_date` | ✅ |
| `quantity` | `quantite` | **85 négatives retirées** | ✅ cible |
| `unit_price_xof` | **ABSENT** | mais = `montant_net_xof / quantite` | ✅ **reconstituable** |
| `discount_pct_applied` | **ABSENT** | déductible du prix payé vs catalogue | pricing |
| `promotion_id` | `promo_key` | → clé de substitution | ✅ |
| — | `montant_net_xof` | **créée** = `quantity × unit_price_xof` | ✅ |

Grain **inchangé** (1 ligne par produit dans une commande). Déduplication :
~425 doublons exacts retirés **avant** génération de `vente_id`.

### `stock_daily` → **AUCUNE TABLE**

| Colonne source | Supabase | Impact |
|---|---|---|
| `product_id`, `date`, `stock_level` | **TABLE ENTIÈREMENT ABSENTE** | ❌ censure de la demande non identifiable |

### `web_events` → `fact_evenements_web`

| Colonne source | Supabase | Transformation | Usage |
|---|---|---|---|
| `event_id` | `event_id` **PK** | conservé, unique sur 374 792 | ✅ |
| `session_id` | **ABSENT** | perdu | ❌ **reco séquentielle impossible** |
| `customer_id` | `client_key` | → clé de substitution | reco |
| `product_id` | `produit_key` | → clé de substitution | ✅ |
| `event_type` | `type_event` | renommé | ✅ |
| `event_timestamp` | `date_key` | **changement de grain : datetime → jour** | ❌ ordre intra-journée perdu |
| `device` | `device` | conservé | reco |
| `referral_source` | **ABSENT** | perdu | ❌ attribution impossible |

### `promotions` → `dim_promotion`

| Colonne source | Supabase | Transformation |
|---|---|---|
| `promotion_id` | `promotion_id` | conservé, plus PK |
| — | `promo_key` **PK** | créée |
| `scope`, `target` | `scope`, `cible` | conservés (`category` / `product`) |
| `discount_pct` | `remise_pct` | renommé, 5 à 40 % |
| `start_date`, `end_date` | idem | conservés |

---

## 3. Écarts entre documentation et données réelles

| # | Affirmation | Réalité mesurée | Gravité |
|---|---|---|---|
| 1 | `stock_daily` fait partie du jeu | Absente de Supabase, du dépôt et du Storage | 🔴 **bloquant** |
| 2 | `launch_date` disponible | Absente ; seul `valid_from` subsiste | 🔴 **bloquant** |
| 3 | `produit_key` « change à chaque version » | **1 seule version par produit** : 300 `produit_key` = 300 `product_id` | 🟠 conception vs état |
| 4 | SCD2 sur `dim_client` | 5 000 `client_key` = 5 000 `customer_id`, aucune version | 🟠 idem |
| 5 | `order_id` est la PK | Absent ; remplacé par `vente_id` | 🟠 grain commande perdu |
| 6 | ~3 % de nulls région / âge | **0 %** — imputés par `Non renseigné` | 🟢 traçable |
| 7 | ~86 000 transactions | 85 419 après nettoyage (attendu ~85 448, écart +29) | 🟢 à confirmer |
| 8 | ~1 % de timestamps désordonnés | **Invérifiable** : `event_timestamp` absent | 🟠 |
| 9 | `unit_price_xof` = prix payé | Reconstituable exactement par `montant / quantite` | 🟢 récupéré |
| 10 | `popularity_score` utilisé par le générateur | Absent du warehouse | 🟢 fuite déjà écartée |

---

## 4. Analyse SCD Type 2 complète

| Contrôle | `dim_produit` | `dim_client` |
|---|---:|---:|
| Lignes | 300 | 5 000 |
| Clés de substitution distinctes | 300 | 5 000 |
| Identifiants métier distincts | 300 | 5 000 |
| Versions par identifiant (min / méd. / max) | 1 / 1 / 1 | 1 / 1 / 1 |
| Identifiants à plusieurs versions | **0** | **0** |
| `is_current = true` | 300 | 5 000 |
| `valid_to` renseigné | **0** | **0** |
| Plusieurs versions courantes | 0 | 0 |
| Aucune version courante | 0 | 0 |
| `valid_to` < `valid_from` | 0 | 0 |
| Chevauchements de fenêtres | 0 | 0 |
| Trous entre versions | 0 | 0 |

**Ventes rattachées à une version valide à leur date : 85 419 / 85 419 (100 %).**

> **Lecture.** Le SCD Type 2 est en place **structurellement** — colonnes,
> clés de substitution, drapeau courant — mais **aucune historisation n'a encore
> eu lieu**. La jointure temporelle est donc aujourd'hui strictement équivalente
> à une jointure simple, et le passage de `produit_key` à `product_id` comme
> identifiant de série **ne change ni le nombre de séries (300) ni les
> quantités**. Cela cessera d'être vrai dès le premier changement de prix ou de
> segment : le code doit donc être écrit dès maintenant pour la jointure
> temporelle correcte.

**Convention d'inclusivité de `valid_to` : non déterminable** — aucune ligne
n'a de `valid_to` renseigné. La règle `date >= valid_from AND (date <= valid_to
OR valid_to IS NULL)` est retenue par défaut, avec un test qui échouera si une
date se retrouvait un jour rattachée à deux versions.

**Prix catalogue : 0 produit sur 300 a connu une variation** (conséquence
directe de l'absence de versionnement). Voir §8.

---

## 5. Le stock : localisation et impact

**Localisation : introuvable.** Recherches menées, toutes infructueuses :

| Emplacement | Résultat |
|---|---|
| Schéma `public` Supabase | 6 tables, `stock_daily` absente (HTTP 404) |
| Schémas `bronze`/`silver`/`gold`/`raw`/`staging`/`analytics`/`dwh` | HTTP 406 — non exposés ou inexistants |
| Supabase Storage | **0 bucket** |
| `Downloads`, `Documents`, `Desktop`, dépôt | Aucun `stock_daily.csv.gz`, aucun CSV source |

**Indice de cohérence** : `stock_daily` est annoncée à ~118 000 lignes ; ma
table analytique en compte **117 763** au grain produit × jour sur la même
fenêtre. L'écart de ~237 lignes suggère que `stock_daily` couvre exactement le
même périmètre — donc que ma borne de début reconstituée est proche de
`launch_date`.

**Impact sur les 50,77 % de zéros : non quantifiable en l'état.** Le
dictionnaire indique que les ventes **s'arrêtent** quand le stock atteint 0.
Une part inconnue des 59 786 zéros est donc de la **demande censurée**, pas de
la demande nulle. Ce qui reste mesurable :

- séquences de zéros : moyenne 2,18 j, médiane 2, max **27 j**, aucune > 30 j ;
- 581 séquences > 7 j, 35 > 14 j.

Les séquences longues sont les candidates naturelles à la rupture, mais **rien
ne permet de les distinguer d'une demande faible** sans `stock_level`.

---

## 6. La vraie date de lancement

**Absente.** `dim_products.launch_date` n'a pas été chargée dans le warehouse.

Ce que l'audit précédent avait établi sur `valid_from`, désormais **tranché par
la documentation** : le document d'architecture indique explicitement que
`valid_from` décrit la **fenêtre de validité de la version**, pas le lancement.
Les deux coïncident aujourd'hui uniquement parce qu'il n'existe qu'une version
par produit.

| Mesure | Valeur |
|---|---|
| Produits dont `valid_from` précède le jeu de données | 120 / 300 (jusqu'à 365 j avant) |
| Écart médian `valid_from` → 1ʳᵉ vente (180 produits dans la fenêtre) | **1 jour** |
| Ventes antérieures à `valid_from` | 0 / 85 419 |

**Décision appliquée** : `date_debut_validite` conservée, `age_produit_jours`
renommé **`age_version_produit_jours`**, et **aucune ancienneté commerciale**
n'est publiée tant que `launch_date` n'est pas fournie.

---

## 7. Variables nécessaires manquantes

12 variables sources absentes du warehouse, par ordre de gravité :

| Variable | Usage bloqué | Contournement |
|---|---|---|
| `stock_daily.stock_level` | forecasting (censure), pricing (écoulement) | **aucun** |
| `dim_products.launch_date` | ancienneté produit, démarrage à froid | approximation `valid_from`, documentée |
| `web_events.session_id` | **recommandation séquentielle** | **aucun** |
| `web_events.event_timestamp` | ordre du funnel, événements en retard | jour seul |
| `fact_transactions.order_id` | nombre de commandes, panier | **aucun** |
| `web_events.referral_source` | attribution, reco | **aucun** |
| `dim_customers.signup_date` | contrôle « événement avant inscription » | **aucun** |
| `dim_products.initial_stock` | initialisation du stock | **aucun** |
| `fact_transactions.unit_price_xof` | pricing | ✅ `montant / quantite` |
| `fact_transactions.discount_pct_applied` | remise réellement appliquée | ✅ déduite du prix payé |
| `dim_products.popularity_score` | — | 🚫 **à ne pas demander** (fuite) |
| `dim_customers.full_name` | — | sans objet |

---

## 8. Prix, remise et marge — ce qui est récupérable

**Prix unitaire payé reconstitué exactement** : `montant_net_xof / quantite`.
Médiane 31 426 XOF (485 à 457 915).

**Le bruit de ±2 % est expliqué** : il s'agit de l'écart entre le prix
réellement payé et le prix catalogue remisé. Écart médian **+0,000 pt**,
p5/p95 = **±1,767 pt**, 99,95 % des lignes dans ±2 points.

> **Mais ce bruit n'est pas un signal de prix.** Sur les 72 039 lignes hors
> promotion : corrélation entre l'écart de prix et la quantité = **+0,001** ;
> élasticité intra-produit estimée sur ce seul écart = **+0,086** — positive et
> quasi nulle, la signature d'un bruit pur. **Estimer une élasticité sur cette
> variation produirait un résultat dénué de sens.**

**Marge calculable** (`cout_xof` présent) : taux de marge médian **26,3 %**
(p5 9,6 %, p95 47,4 %) — cohérent avec les 15 %–55 % annoncés.
**1 237 lignes à marge négative** (promotions profondes sur produits à faible
marge) : à traiter comme contrainte de pricing.

**Faisabilité de l'élasticité** :

| Constat | Valeur |
|---|---|
| Produits dont le prix catalogue varie | **0 / 300** |
| Produits ayant connu ≥ 2 niveaux de remise | **288 / 300** |
| Niveaux de remise observés | 0, 5, 10, 15, 20, 25, 30, 40 % |

Quantité moyenne par produit-jour selon la remise : 2,66 (0 %) · 2,58 (5 %) ·
3,03 (10 %) · 2,73 (15 %) · 2,88 (20 %) · 3,35 (25 %) · 2,83 (30 %) · 2,63
(40 %, n = 8). **Relation croissante mais non monotone et bruitée.**

Cohérent avec le dictionnaire : la promo agit sur λ (nombre de commandes), pas
sur la quantité par commande. **L'élasticité n'est identifiable que par la
variation promotionnelle**, sur 7 niveaux discrets, en intra-produit.

---

## 9. Réconciliation des anomalies

| Anomalie annoncée | Volume Raw | État dans Supabase | Traitement déduit |
|---|---:|---|---|
| Doublons exacts | ~425 | 0 (`vente_id` unique sur 85 419) | supprimés avant génération de la clé |
| Quantités négatives | ~85 | 0 (`quantite` ∈ [1, 5]) | supprimées |
| FK orphelines `P99999` | 42 | 0 clé orpheline | supprimées |
| Catégories en majuscules | 15 | 0 (8 catégories distinctes) | normalisées, **sans fusion erronée** |
| Nulls région / âge | ~3 % | 0 % | **imputés par `Non renseigné`** |
| Timestamps désordonnés | ~1 % | — | **invérifiable** |

```
volume Raw annoncé        ~86 000
− doublons exacts            −425
− quantités négatives         −85
− FK orphelines               −42
= attendu                 ~85 448
volume réel Supabase       85 419
écart                         +29
```

**Ce qui n'est pas vérifiable sans le Raw** : que les doublons supprimés étaient
réellement identiques ; que la déduplication n'a pas porté sur une clé trop
large ; que les quantités négatives étaient des erreurs et non des retours ;
que `P99999` n'a pas été réaffecté ; qu'aucune imputation client n'utilise
d'information future. **Aucune table de quarantaine ni rapport de qualité n'est
accessible.**

Point positif : l'imputation par `Non renseigné` est une **valeur explicite**,
donc traçable et sans risque de fuite — c'est le bon choix.

---

## 10. Trois schémas analytiques proposés

### A. Forecasting — `product_id × date`

Cible `quantite_vendue_observee`. Colonnes : identifiants, calendrier
(dont fêtes sénégalaises), attributs produit **en vigueur à la date**, prix
catalogue et prix attendu, promotions planifiées, retards de quantité, signaux
web **décalés**, `web_data_observed`. **Sous réserve `stock_daily`** :
`stock_fin_jour_lag1`, `indicateur_rupture`, `jour_censure_stock`,
`jours_depuis_derniere_rupture`, `jours_rupture_lag_7/14/28`.

### B. Pricing — `product_id × date`

`prix_catalogue_xof`, `prix_unitaire_paye_xof`, `remise_planifiee_pct`,
`remise_appliquee_pct`, `cout_unitaire_xof`, `marge_unitaire_xof`,
`marge_totale_xof`, `taux_marge`, quantité, demande prévue, stock, calendrier.
Garde-fous : prix ≥ coût + marge minimale, bornes métier, remise dans
{0, 5, …, 40}.

### C. Recommandation — interactions client × produit

`customer_id`, `product_id`, `date`, `type_event`, `device`, poids
d'interaction. **Sans `session_id` ni `event_timestamp`, aucun modèle
séquentiel n'est possible** : seul un filtrage collaboratif implicite au grain
journalier l'est.

---

## 11. Corrections à appliquer

| # | Correction | Impact |
|---|---|---|
| 1 | `unique_id` = `product_id` (identifiant stable), `produit_key` réservé à la jointure de version | 300 séries inchangées |
| 2 | Jointure SCD temporelle (`date >= valid_from AND (date <= valid_to OR NULL)`) | aucun aujourd'hui, indispensable demain |
| 3 | `age_produit_jours` → **`age_version_produit_jours`** | supprime une interprétation fausse |
| 4 | `n_transactions` → **`nombre_lignes_vente`** | lève l'ambiguïté commande / ligne |
| 5 | Ajouter `prix_unitaire_paye_xof`, `remise_appliquee_pct`, `cout_unitaire_xof`, `marge_*` | débloque le pricing |
| 6 | Séparer les trois datasets | évite la table universelle ambiguë |
| 7 | Interdire `popularity_score` par liste noire explicite | fuite de conception |
| 8 | Intégrer le stock **dès réception** | partitionne les zéros |

---

## 12. Questions au data engineer

**Bloquantes**

1. **`stock_daily`** — peut-elle être chargée dans Supabase ou fournie en
   fichier ? Sans elle, impossible de distinguer demande nulle et rupture.
   Préciser : stock de fin de journée (confirmé par le dictionnaire) ; moment
   d'application du réapprovisionnement ; `stock_level` peut-il être négatif ;
   chaque produit-date a-t-il une ligne ; initialisation des nouveaux produits.
2. **`launch_date`** — peut-elle être ajoutée à `dim_produit` ? C'est la seule
   ancienneté commerciale valide.
3. **`order_id`** — peut-il être conservé dans `fact_ventes` ? Sans lui, ni
   nombre de commandes, ni panier moyen, ni analyse multi-produits.

**Importantes**

4. **`session_id` et `event_timestamp`** — la recommandation séquentielle en
   dépend entièrement. La perte de l'heure est-elle volontaire ?
5. **`referral_source`** — attribution de canal.
6. **`signup_date`** — contrôle « événement avant inscription ».
7. **Rapports de quarantaine** — où sont les 425 + 85 + 42 lignes rejetées ?
   Existe-t-il une table de rejets et un rapport `great_expectations` ?
8. **Compte exact du Raw** — pour lever l'écart de +29 lignes.
9. **Convention `valid_to`** — inclusive ou exclusive ? Aucune ligne renseignée
   ne permet de trancher.
10. **Le prix catalogue variera-t-il ?** Aujourd'hui figé sur 300 produits :
    l'élasticité ne repose que sur les promotions.

**À ne pas fournir**

11. `popularity_score` : paramètre latent du générateur. Le recevoir créerait
    une fuite de conception. À exclure explicitement.

---

## 13. Plan d'exécution ordonné

| Étape | Contenu | Dépendance |
|---|---|---|
| 1 | Demande formelle au data engineer (§12) | — |
| 2 | Refonte du socle : `product_id` comme série, jointure SCD temporelle, renommages | aucune |
| 3 | Dataset **pricing** : prix payé, remise appliquée, coût, marge | aucune |
| 4 | Tests de non-régression (§15 de la consigne) | étapes 2-3 |
| 5 | Dataset **forecasting** v2 sans stock, avec réserve documentée | étape 2 |
| 6 | **Intégration du stock** dès réception : masque de censure, features décalées | `stock_daily` |
| 7 | Baselines + LightGBM (Poisson/Tweedie/hurdle), 3 stratégies de censure | étapes 5-6 |
| 8 | Backtesting h=30, 6 fenêtres, métriques par segment | étape 7 |
| 9 | Élasticité et optimisation sous contraintes de marge | étapes 3, 8 |
| 10 | Recommandation — **uniquement si** `session_id` est fourni | question 4 |
| 11 | Industrialisation, documentation, lineage | tout |

**Les étapes 2 à 5 sont réalisables immédiatement. L'étape 7 ne doit pas être
lancée avant arbitrage sur `stock_daily` : entraîner sans le stock produit un
modèle qui apprend partiellement la contrainte d'offre au lieu de la demande.**
