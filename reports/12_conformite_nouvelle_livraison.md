# 12 — Conformité de la nouvelle livraison (2026-08-13)

_Diagnostic établi en lecture seule, via connexion PostgreSQL directe
(transaction `READ ONLY`, `ROLLBACK` final) et `scripts/inspect_postgres_full.py`,
`scripts/validate_stock.py`, `scripts/validate_dataset.py`, `python -m pytest`._

---

## 1. Identification exacte de la livraison

**Ce n'est pas une nouvelle instance.** Même projet Supabase (même préfixe
d'hôte, même `SUPABASE_URL`, même chaîne de connexion) — c'est une **migration
de schéma en place** sur la base déjà auditée le 2026-08-13 matin.

Deux nouveaux fichiers déposés directement dans le dépôt à 20:02 (et non dans
Downloads, où résidaient les précédents) :

| Fichier | Rôle | Remplace |
|---|---|---|
| `DATA_DICTIONARY 3.md` | Décrit désormais le **warehouse Supabase**, plus les tables brutes | `Downloads/DATA_DICTIONARY.md` (14:41) |
| `GUIDE_TABLES_MODELES 3.md` | Nouveau — mapping table → cas d'usage | aucun équivalent antérieur |

Le document d'architecture (`Architecture_Technique_Schema_Donnees.docx`,
14:41) n'a **pas** été mis à jour : il ne mentionne toujours que 6 tables, pas
`fact_stock`. **Incohérence entre les deux documents fournis**, à signaler.

Les deux nouveaux fichiers renvoient à un `HANDOFF_DATA_SCIENTIST.md` et à un
`create_star_schema.sql` — **recherchés et introuvables** nulle part sur le
poste (Downloads, Documents, Desktop, dépôt).

### Ce qui a changé côté base (vérifié en SQL direct, pas supposé)

| Élément | Avant (cache 14:22) | Après (SQL, 20:26) | Changement |
|---|---|---|---|
| Nombre de tables `public` | 6 | **7** | + `fact_stock` |
| `fact_stock` | absente | **117 763 lignes** | table entière ajoutée |
| `dim_promotion.scope` | présent | **absent** | renommée `portee` |
| `dim_promotion.start_date`/`end_date` | présents | **absents** | renommées `date_debut`/`date_fin` |
| `fact_evenements_web.device` | présent | **absent** | renommée `appareil` |
| `fact_ventes`, `dim_produit`, `dim_client`, `dim_date` | — | — | **inchangées**, colonnes et volumes identiques |
| Lignes des 6 tables préexistantes | 85 419 / 300 / 5 000 / 546 / 374 792 / 120 | **identiques** | aucune |

**Étiquetage** : `ancienne_livraison` = cache `data/raw/` du 2026-08-13 14:22
(archivé intégralement dans `data/archive/v1_2026-08-13_pre_stock/` avant toute
ré-extraction) ; `nouvelle_livraison` = extraction fraîche du 2026-08-13 20:33
via connexion PostgreSQL directe.

---

## 2. Sécurisation de la connexion

Aucune nouvelle chaîne de connexion n'a été fournie : `$SUPABASE_CONNECTION_STRING`
est identique à la session précédente (même longueur, même préfixe d'hôte
masqué). Elle n'a jamais été affichée, journalisée ni modifiée.

Session ouverte en lecture seule via `ReadOnlyInspector` : `readonly=True`,
`statement_timeout=60s`, `lock_timeout=5s`,
`idle_in_transaction_session_timeout=120s`, fermeture par `ROLLBACK`. Les
pipelines principaux (`audit`, `extract`, `prepare`) utilisent désormais le
même repli automatique vers le pooler (`resolve_reachable_url`, jusqu'ici
réservé au script d'inspection) — nécessaire ici car l'hôte direct ne résout
toujours pas depuis ce poste.

---

## 3. Inventaire complet de la nouvelle base (SQL direct)

| Table | Lignes exactes | Grain | PK | FK | RLS | Commentaires |
|---|---:|---|---|---|---|---|
| `dim_produit` | 300 | 1 produit | `produit_key` | — | activée, 0 politique | aucun |
| `dim_client` | 5 000 | 1 client | `client_key` | — | activée, 0 politique | aucun |
| `dim_date` | 546 | 1 jour | `date_key` | — | activée, 0 politique | aucun |
| `dim_promotion` | 120 | 1 campagne | `promo_key` | — | activée, 0 politique | aucun |
| `fact_ventes` | 85 419 | 1 vente | `vente_id` | produit/client/date/promo | activée, 0 politique | aucun |
| `fact_evenements_web` | 374 792 | 1 événement | `event_id` | produit/client/date | activée, 0 politique | aucun |
| **`fact_stock`** | **117 763** | **produit × jour** | **(produit_key, date_key) composite** | produit, date | activée, 0 politique | aucun |

Aucune vue, vue matérialisée, foreign table, partition ni fonction métier.
Aucun autre schéma applicatif que `public`. Storage : 0 bucket (inchangé).
**RLS toujours activée sans aucune politique** sur les 7 tables — la lecture
exige toujours `service_role`.

---

## 4. Comparaison ancienne vs nouvelle livraison

| Élément | Ancienne | Nouvelle | Évolution | Impact |
|---|---|---|---|---|
| Tables `public` | 6 | 7 | + `fact_stock` | débloque le stock (§7) |
| `fact_ventes` | 85 419 lignes, 7 col. | identique | aucun | aucun |
| `dim_produit` | 300 lignes, 10 col. | identique | aucun | aucun |
| `dim_client` | 5 000 lignes, 8 col. | identique | aucun | aucun |
| `dim_date` | 546 lignes, 7 col. | identique | aucun | aucun |
| `dim_promotion` | `scope`,`start_date`,`end_date` | `portee`,`date_debut`,`date_fin` | renommage | **1 test cassé, corrigé** (§14) |
| `fact_evenements_web` | `device` | `appareil` | renommage | aucun impact fonctionnel (rôle non utilisé) |
| Extraction | REST | **PostgreSQL direct** (pooler) | changement de backend | a révélé un bug de coercion de type (§13) |

### Colonnes précédemment manquantes — statut mis à jour

| Colonne | Avant | Maintenant | Classement |
|---|---|---|---|
| `stock_daily` / `stock_level` | absente | ✅ **présente** (`fact_stock.niveau_stock`) | désormais présent directement |
| `launch_date` | absente | **toujours absente** | inchangé |
| `order_id` | absente | **toujours absente** | inchangé |
| `session_id` (métier) | absente | **toujours absente** | inchangé |
| `event_timestamp` | absente | **toujours absente** | inchangé |
| `referral_source` | absente | **toujours absente** | inchangé |
| `signup_date` | absente | **toujours absente** | inchangé |
| `unit_price_xof` | absente | **toujours absente**, mais dérivable exactement (`montant_net_xof / quantite`) | dérivable exactement |
| `discount_pct_applied` | absente | dérivable via prix payé vs catalogue remisé | seulement approximable (bruit ±2 %) |
| Quarantaine / rejets | absents | **toujours absents** | inchangé |
| Zones Raw/Bronze/Silver/Gold | absentes | **toujours absentes** | inchangé, confirmé par le nouveau dictionnaire lui-même (§5) |

**Seul `stock_daily` a été livré.** Les demandes bloquantes n°2 (`launch_date`)
et n°3 (`order_id`) du rapport précédent restent sans réponse.

---

## 5. Conformité au dictionnaire

### `fact_stock` vs `stock_daily` annoncée

| Colonne dictionnaire | Colonne réelle | Type attendu | Type réel | Conforme |
|---|---|---|---|---|
| `product_id` | `produit_key` | string | text | ⚠️ clé de **substitution**, pas l'identifiant métier — cohérent avec le reste du warehouse |
| `date` | `date_key` | date | text (`AAAAMMJJ`) | ⚠️ format warehouse, pas une régression |
| `stock_level` | `niveau_stock` | int | integer | ✅ |
| — | — | grain annoncé produit×jour, fin de journée | **confirmé empiriquement** (§7) | ✅ |

**117 763 lignes vs ~118 000 annoncées** dans l'ancien dictionnaire (écart de
237, cohérent avec l'écart déjà observé sur ma table analytique reconstruite).
Le nouveau dictionnaire annonce directement 117 763 : **exact**.

### Anomalies volontaires — inchangées, toujours cohérentes avec un warehouse nettoyé

Aucune des tables modifiées ou ajoutées n'introduit de nouvelle anomalie
volontaire déclarée. `fact_stock` : 0 valeur négative, 0 nulle, 0 manquante, 0
doublon, 0 trou temporel — cohérent avec une livraison Gold déjà nettoyée,
comme l'affirme le nouveau dictionnaire (« les données sont déjà nettoyées »).

### Couche livrée

**Confirmé : Gold / warehouse final**, pas un mélange. Le nouveau dictionnaire
le dit explicitement : « Les tables intermédiaires du pipeline… existent
seulement dans la zone Silver du data lake local, pas dans Supabase » — cela
recoupe exactement ce que l'inspection SQL avait établi de façon indépendante
le 2026-08-13 matin (aucun schéma `raw`/`bronze`/`silver`/`gold` dans
l'instance).

---

## 6. Réconciliation des volumes

| Élément | Ancienne livraison | Nouvelle livraison | Écart |
|---|---:|---:|---:|
| `fact_ventes` (lignes) | 85 419 | 85 419 | 0 |
| `SUM(quantite)` | 155 751 | 155 751 | 0 |
| `dim_produit` / `dim_client` / `dim_date` / `dim_promotion` (lignes) | 300/5000/546/120 | identiques | 0 |
| `fact_evenements_web` (lignes) | 374 792 | 374 792 | 0 |
| **`fact_stock`** (lignes) | — | **117 763** | **+117 763** |
| Table analytique (lignes) | 117 763 | 117 763 | 0 |
| Table analytique (`SUM(y)`) | 155 751 | 155 751 | 0 |
| Produits / mois en écart après reconstruction | 0 / 0 | 0 / 0 | — |

**Réconciliation exacte, globalement, par produit et par mois** — confirmée par
`scripts/validate_dataset.py` (0 échec sur 14 contrôles) après reconstruction
complète depuis les nouvelles sources.

---

## 7. Validation du stock — le résultat qui compte le plus

`scripts/validate_stock.py`, sortie complète : `reports/13_validation_stock.md`.

### Grain, unicité, couverture

| Contrôle | Résultat |
|---|---|
| Doublons produit-date | **0** |
| Produits couverts | **300 / 300** |
| Trous temporels | **0** |
| 1ʳᵉ date de stock = `valid_from` | 180 / 300 produits exactement ; écart médian **0 j**, max 365 j (mêmes 120 produits dont `valid_from` précède le début des données, déjà identifiés) |
| Ventes antérieures à la 1ʳᵉ date de stock connue | **0** |
| Stock négatif | **0** |
| Stock nul | **0** |
| **Stock minimal observé** | **21** (jamais en dessous) |

### Définition confirmée : stock de fin de journée

Non supposée — **démontrée par reconstruction exacte**. Réconciliation
`niveau_stock(t) = niveau_stock(t-1) − quantité_vendue(t) + réappro(t)` :

- **99,42 %** des jours : `delta = 0` (aucun réapprovisionnement, formule exacte) ;
- **0,48 %** des jours (559 événements) : réapprovisionnement détecté, toujours
  déclenché quand `stock_veille − vente ≤ 20` (99,8 % des cas) — **le seuil de
  20 unités documenté est confirmé empiriquement**, remontant le stock de
  100 à 299 unités ;
- **0,105 %** des jours (123 lignes) : `delta < 0`, une incohérence mineure
  (écart de 1 à 3 unités) — **anomalie à signaler**, non bloquante.

### Le résultat qui change le verdict précédent

| Mesure | Valeur |
|---|---|
| Produit-jours avec stock de veille ≤ 0 (rupture) | **0** |
| Ventes positives malgré rupture | sans objet (aucune rupture enregistrée) |
| Corrélation stock de la veille ↔ vente du jour | **−0,035** (quasi nulle) |
| Taux de vente nulle si stock veille ∈ [0,25] | **47,1 %** |
| Taux de vente nulle si stock veille ∈ [300,1000] | **54,5 %** |
| Zéros de la table analytique associés à une rupture (stock veille ≤ 0) | **0 / 59 786 (0,00 %)** |

**Le sens de la relation est inverse de ce que prédirait une censure par
rupture** : le taux de zéro est le plus *bas*, pas le plus haut, quand le stock
est faible — signature d'une sélection inverse (le stock baisse parce que les
ventes ont été fortes), pas d'une contrainte d'offre.

> **Ce constat contredit la description narrative du dictionnaire** (« si le
> stock tombe à 0, les ventes s'arrêtent ») **sans contredire les données
> elles-mêmes** : le réapprovisionnement, réactif le jour même, empêche
> précisément que cette situation soit jamais enregistrée dans `niveau_stock`.
> Question à poser au data engineer (§15) : le réapprovisionnement est-il
> réellement instantané dans le simulateur, ou `fact_stock` ne capture-t-il
> qu'un état post-réappro qui masque une contrainte réelle survenue en cours
> de journée ?

**Impact sur les 50,77 % de zéros : nul, mesuré, pas supposé.** L'hypothèse de
censure ne peut pas être confirmée par cette livraison. Cela ne prouve pas
l'absence de rupture en général — cela prouve que **cette table ne permet pas
de la détecter**.

---

## 8. Validation du lancement et du SCD

**`launch_date` reste absente.** Aucun changement par rapport au diagnostic du
matin. La distinction demandée est maintenue sans modification :

- `product_id` = identifiant stable de série (300 produits, 1 version chacun) ;
- `produit_key` = clé de jointure de version (identique à `product_id` en
  cardinalité tant qu'aucune historisation SCD n'a eu lieu) ;
- `valid_from`/`valid_to`/`is_current` = validité de version, **exposée sous
  `date_debut_validite`**, jamais renommée `date_lancement` ;
- 0 chevauchement, 0 trou, 0 version courante multiple, 0 sans version
  courante, 100 % des ventes rattachées à une version valide — **inchangé**.

---

## 9. Validation des commandes

**`order_id` reste absent.** `vente_id` demeure la seule clé de ligne. Le grain
de `fact_ventes` (1 ligne = 1 produit vendu dans une commande) est confirmé par
le nouveau dictionnaire lui-même — qui décrit `fact_transactions` comme
« 1 ligne par produit dans une commande » sans jamais prétendre que `vente_id`
équivaut à une commande. Le nommage `nombre_lignes_vente` (déjà en usage)
reste correct ; `nombre_commandes` demeure **incalculable**.

---

## 10. Validation des événements web

**`session_id`, `event_timestamp`, `referral_source` restent absents** du
schéma métier. Seul changement : `device` → `appareil` (renommage cosmétique,
sans rôle dans le pipeline actuel). Aucune donnée de recommandation
séquentielle n'est débloquée par cette livraison.

---

## 11. Faisabilité forecasting — mise à jour

### A. Ventes observées
**Inchangé : faisable, qualité bonne à l'horizon agrégé** (cf.
`reports/11_verdict_faisabilite.md`). Le stock, désormais disponible, a été
intégré comme variable explicative légitime (`stock_disponible_lag1`,
indicateurs de rupture, décalés) — sans levier de gain démontré pour l'instant
(corrélation quasi nulle), mais sans risque de fuite.

### B. Demande non contrainte
**Reste non réalisable — mais pour une raison différente de celle identifiée
le matin.** Ce n'était pas « donnée manquante », c'est maintenant « donnée
présente mais sans signal de censure détectable ». La distinction entre
ventes observées et demande réelle **ne peut toujours pas être établie**, et
cette livraison ne permet pas de trancher si c'est parce que la censure
n'existe réellement pas dans ce jeu de données, ou parce qu'elle est masquée
par la définition de `niveau_stock` (post-réappro).

### Réconciliation au grain `product_id × date`

```
SUM(fact_ventes.quantite)          = 155 751
SUM(table_analytique.quantite_vendue_observee) = 155 751
écart : 0 — global, par produit (0/300 en écart), par mois (0/18 en écart)
```

**Aucune fuite détectée** : `stock_fin_jour` (contemporain) n'est jamais
utilisé comme variable explicative — seul `stock_disponible_lag1` (stock de
la veille) l'est, vérifié par 9 tests dédiés (`tests/test_stock_features.py`).

---

## 12. Faisabilité pricing

**Inchangée.** `cost_xof`/`cout_xof`, prix catalogue, prix payé (reconstitué),
promotion sont **toujours** les seules sources disponibles ; `fact_stock`
n'apporte rien à l'objectif pricing dans l'immédiat (pas de contrainte de
stock mesurable à intégrer dans une recommandation de remise). Le verdict du
rapport précédent tient sans changement : A (descriptif) et B (effet des
remises, encadré) faisables ; C (prix optimal causal) toujours bloqué, et
**toujours pour une raison structurelle** (le prix catalogue ne varie pour
aucun produit) — aucune donnée reçue ni attendue ne débloque C.

---

## 13. Modifications apportées au projet

| # | Modification | Fichier | Raison |
|---|---|---|---|
| 1 | Archivage complet de l'ancien cache avant ré-extraction | `data/archive/v1_2026-08-13_pre_stock/` | ne pas mélanger ancienne/nouvelle livraison |
| 2 | Ajout de `fact_stock` à la configuration | `config/config.yaml` | nouvelle table |
| 3 | Rôle `stock_level` + table logique `stock` dans le moteur de mapping | `src/data/mapping.py` | reconnaître `niveau_stock` sans le deviner par nom seul |
| 4 | Repli automatique vers le pooler dans **tous** les pipelines (pas seulement le script d'inspection) | `src/data/connection.py` | l'hôte direct ne résout toujours pas depuis ce poste |
| 5 | **Correction de bug** : `coerce_datetime_columns` ne gérait que les chaînes ISO (REST), pas les objets `datetime.date` natifs renvoyés par psycopg2 | `src/data/coercion.py` | le passage au backend PostgreSQL direct a fait échouer silencieusement la détection de `valid_from` |
| 6 | Nouveau module de features stock, strictement décalé (`lag1`), avec masque de censure | `src/features/stock.py` | tâche #12, désormais réalisable |
| 7 | Intégration du stock dans la table analytique | `src/pipelines/prepare.py` | 12 nouvelles colonnes, 0 ligne perdue |

**Aucune donnée Supabase modifiée. Aucune écriture émise** (toutes les
connexions restent en lecture seule, vérifié par `tests/test_postgres_readonly.py`
et `tests/test_connection_guards.py`).

**Point non traité, signalé et non résolu silencieusement** : le dépôt n'est
**pas** un dépôt git (`Is a git repository: false`). Aucun checkpoint git n'a
donc pu être créé avant les modifications, contrairement à ce que demande la
procédure. Je ne l'ai pas initialisé de ma propre initiative — c'est une
décision de structure de projet qui te revient.

---

## 14. Tests

| | Avant cette livraison | Après adaptation |
|---|---:|---:|
| Total | 87 | **103** |
| Ajoutés | — | **16** (`test_coercion.py` ×7, `test_stock_features.py` ×9) |
| Modifiés | — | **1**, avec justification (`test_promotions_dans_les_fenetres_declarees` : colonnes `start_date`/`end_date` renommées `date_debut`/`date_fin` côté source ; détection tolérante aux deux conventions ajoutée pour ne pas re-casser au prochain renommage) |
| Supprimés | — | 0 |
| Succès | — | **103 / 103** |
| Échecs | — | **0** |
| Avertissements | — | 0 |

**Aucun test n'a été affaibli.** Le test modifié vérifie exactement la même
propriété (toute vente promue tombe dans la fenêtre déclarée) ; seule la
résolution du nom de colonne a été rendue tolérante.

`scripts/validate_dataset.py` (14 contrôles) : **0 échec.**
`scripts/validate_stock.py` : 7 sections, aucune anomalie bloquante, 1 mineure
signalée (§7, 0,105 % d'incohérence de réconciliation stock/ventes).

---

## 15. Questions encore ouvertes au data engineer

**Sur le stock (nouveau)**

1. Le réapprovisionnement est-il réellement **instantané le jour même** dans
   le générateur, ou `niveau_stock` ne capture-t-il que l'état de fin de
   journée **après** un réappro qui aurait pu survenir trop tard pour servir
   toute la demande ? C'est la question qui détermine si l'absence totale de
   censure mesurée est réelle ou un artefact de la table.
2. Les 123 lignes (0,105 %) où la réconciliation stock/ventes ne boucle pas
   exactement (`delta < 0`, écart de 1 à 3 unités) — erreur du générateur,
   ventes non comptabilisées dans le mouvement de stock, ou autre mouvement
   (casse, retour fournisseur) ?
3. `initial_stock` (annoncée dans le dictionnaire d'origine) reste absente :
   comment le stock de chaque produit est-il initialisé à son lancement ?

**Toujours en attente depuis le rapport du matin**

4. `launch_date` — non livrée.
5. `order_id` — non livré.
6. `session_id` / `event_timestamp` / `referral_source` — non livrés ; la
   recommandation séquentielle reste hors de portée.
7. Où sont `HANDOFF_DATA_SCIENTIST.md` et `create_star_schema.sql`, référencés
   par les nouveaux documents mais introuvables ?
8. Le document d'architecture (`.docx`) sera-t-il mis à jour pour inclure
   `FACT_STOCK` ? Il ne mentionne toujours que 6 tables.

**À ne toujours pas fournir**

9. `popularity_score` — non livré, et c'est un atout à préserver.

---

## 16. Décision finale

# ✅ CONFORME AVEC RÉSERVES NON BLOQUANTES

| Réserve | Gravité | Impact | Correction | Responsable | Bloquante |
|---|---|---|---|---|---|
| `fact_stock` ne montre aucun signal de censure mesurable | **importante** | l'objectif forecasting B (demande non contrainte) reste hors de portée, pour une raison différente de celle identifiée le matin | clarifier la logique de réappro avec le data engineer (question 1) | data engineer | non — n'empêche pas de livrer A |
| Document d'architecture non synchronisé avec le nouveau dictionnaire | mineure | risque de confusion documentaire, pas de risque technique | mise à jour du `.docx` | data engineer | non |
| 0,105 % d'incohérence de réconciliation stock/ventes | mineure | négligeable sur l'agrégat, à surveiller si le volume augmente | aucune action requise à ce stade | — | non |
| Fichiers `HANDOFF_DATA_SCIENTIST.md` / `create_star_schema.sql` référencés mais absents | mineure | aucune preuve documentaire supplémentaire de la sémantique des colonnes | transmission des fichiers | data engineer | non |
| Dépôt non versionné avec git | mineure | pas de checkpoint possible avant modification | décision côté projet | toi | non |
| `launch_date`, `order_id`, `session_id`/`event_timestamp` toujours absents | inchangée depuis ce matin | limites déjà actées dans `reports/11_verdict_faisabilite.md` | livraison future | data engineer | non pour A/B/pricing A/B ; oui pour forecasting B et recommandation |

**Conséquence pratique : aucun changement au verdict de faisabilité du
2026-08-13 matin.** Le stock est intégré proprement dans le pipeline
(12 nouvelles colonnes, aucune fuite, 103/103 tests, 0/14 contrôles en échec,
réconciliation exacte), mais n'apporte aujourd'hui aucun gain démontré au
forecasting des ventes observées, et ne débloque pas la demande non
contrainte. Le pricing est inchangé.

**Conformément à la règle de décision de la consigne** : les datasets ont été
adaptés, les audits et tests relancés. **Je m'arrête ici, avant tout
entraînement**, dans l'attente de ta validation.
