# 09 — Statut définitif des sources (inspection SQL directe)

_Établi le 2026-08-13 par `scripts/inspect_postgres_full.py`, en transaction
`READ ONLY`, SELECT uniquement, `ROLLBACK` final. Aucun identifiant n'est
reproduit ici. Sortie brute : `reports/08_inspection_postgres.md`._

---

## 1. Contexte de connexion

| Élément | Valeur |
|---|---|
| Chaîne de connexion | lue depuis `$SUPABASE_CONNECTION_STRING` (valeur jamais exposée) |
| Mode | **pooler** (voir §1.1) |
| PostgreSQL | **17.6** |
| Base | `postgres` |
| Rôle | `postgres` — **non superuser**, membre de `pg_read_all_data`, `pg_monitor`, `service_role`… |
| `rolbypassrls` | **true** |
| `current_schema()` | `public` |
| `search_path` | `"$user", public, extensions` |
| `transaction_read_only` | **on** |
| Catalogues système | lisibles (668 objets) |
| Réglages appliqués | `statement_timeout=60s`, `lock_timeout=5s`, `idle_in_transaction_session_timeout=120s` — **tous acceptés** |

### 1.1 Pourquoi le pooler et non la connexion directe

L'hôte `db.<ref>.supabase.co` **ne résout ni en A ni en AAAA** depuis ce poste,
alors que la résolution DNS générale fonctionne ; la pile IPv6 locale est par
ailleurs indisponible. Supabase réserve la connexion directe à l'IPv6 : la voie
IPv4 est le pooler.

Repli implémenté dans `resolve_reachable_url()` : si l'hôte direct ne résout
pas, la connexion bascule sur `$SUPABASE_POOLER_HOST` avec l'utilisateur
`postgres.<ref>`. Le nom d'hôte du pooler et son port sont des **valeurs
publiques**, stockées en clair dans `.env` ; le mot de passe est repris de la
chaîne d'origine et jamais journalisé.

---

## 2. Schémas réellement présents

| Schéma | Catégorie | USAGE | Objets |
|---|---|---|---:|
| `public` | **APPLICATIF** | ✅ | **6** |
| `auth` | interne Supabase | ✅ | 23 |
| `storage` | Supabase Storage | ✅ | 8 |
| `realtime` | interne Supabase | ✅ | 3 |
| `extensions`, `vault` | interne Supabase | ✅ | 2 chacun |
| `graphql`, `graphql_public`, `pgbouncer` | interne Supabase | ✅ | 0 |

**Un seul schéma applicatif : `public`.** Aucun schéma `raw`, `bronze`,
`silver`, `gold`, `staging`, `analytics` ou `dwh` **n'existe** dans l'instance.

> **Ce que change l'accès SQL direct.** L'API REST renvoyait `HTTP 406` pour ces
> schémas — un code ambigu qui signifie « non exposé par PostgREST » et ne
> permettait pas de conclure entre « existe mais masqué » et « n'existe pas ».
> `pg_namespace` tranche : **ils n'existent pas**.

---

## 3. Objets du schéma `public`

6 tables, aucune vue, aucune vue matérialisée, aucune foreign table, aucune
partition, aucune fonction métier.

| Table | Lignes (exactes) | RLS | SELECT |
|---|---:|---|---|
| `fact_evenements_web` | 374 792 | activée | ✅ |
| `fact_ventes` | 85 419 | activée | ✅ |
| `dim_client` | 5 000 | activée | ✅ |
| `dim_date` | 546 | activée | ✅ |
| `dim_produit` | 300 | activée | ✅ |
| `dim_promotion` | 120 | activée | ✅ |

Comptages exacts **identiques** à ceux obtenus par l'API REST : aucune
divergence.

### Contraintes déclarées — confirmées en SQL

5 clés primaires et 7 clés étrangères, strictement identiques à ce que
l'OpenAPI annonçait :

```
dim_client.client_key            PRIMARY KEY
dim_date.date_key                PRIMARY KEY
dim_produit.produit_key          PRIMARY KEY
dim_promotion.promo_key          PRIMARY KEY
fact_ventes.vente_id             PRIMARY KEY
fact_evenements_web.event_id     PRIMARY KEY

fact_ventes.produit_key       → dim_produit.produit_key
fact_ventes.client_key        → dim_client.client_key
fact_ventes.date_key          → dim_date.date_key
fact_ventes.promo_key         → dim_promotion.promo_key
fact_evenements_web.produit_key → dim_produit.produit_key
fact_evenements_web.client_key  → dim_client.client_key
fact_evenements_web.date_key    → dim_date.date_key
```

**Aucune contrainte UNIQUE ni CHECK. Aucun commentaire de colonne** — ce qui
confirme définitivement qu'aucune preuve documentaire de la sémantique de
`valid_from` n'existe dans la base.

### RLS : l'explication définitive du blocage initial

**RLS activée sur les 6 tables, et 0 politique définie.** Une table avec RLS
active et sans politique **rejette toute lecture** pour un rôle qui ne la
contourne pas. C'est la cause exacte du constat du 2026-08-13 : la clé anon
voyait les 6 tables mais recevait 0 ligne. Le rôle `postgres` a
`rolbypassrls = true`, d'où l'accès complet.

---

## 4. Statut définitif des sources bloquantes

Recherche menée sur **tous les schémas non système**, par nom d'objet
(`pg_class`) et par nom de colonne (`pg_attribute`).

| Source | Statut | Preuve |
|---|---|---|
| `stock_daily` (et `stock`, `inventory`, `availability`, `rupture`) | 🔴 **ABSENTE DE L'INSTANCE** | aucun objet correspondant dans `pg_class` |
| `launch_date` / `date_lancement` | 🔴 **ABSENTE** | aucune colonne correspondante dans `pg_attribute` |
| `order_id` / `commande_id` | 🔴 **ABSENTE** | idem |
| `event_timestamp` | 🔴 **ABSENTE** | idem |
| `referral_source` | 🔴 **ABSENTE** | idem |
| `initial_stock` | 🔴 **ABSENTE** | idem |
| `signup_date` | 🔴 **ABSENTE** | idem |
| `popularity_score` | 🟢 **ABSENTE** (souhaitable) | fuite de conception écartée |
| `session_id` | 🔴 **ABSENTE du périmètre métier** | 2 occurrences trouvées, mais dans `auth.mfa_amr_claims` et `auth.refresh_tokens` — tables d'authentification Supabase, **sans rapport** avec le funnel web |
| Quarantaine / rejets / qualité | 🔴 **ABSENTS** | aucun objet `quarantine`, `reject`, `quality`, `great_expectation`, `dbt` |
| Zones `raw`/`bronze`/`silver`/`gold`/`staging` | 🔴 **ABSENTES** | ni schéma, ni table, ni vue, ni suffixe |

**Aucune colonne JSON/JSONB métier** n'existe qui pourrait masquer ces
variables : les seules colonnes `metadata`/`payload` trouvées appartiennent à
`auth`, `realtime` et `storage`.

---

## 5. Supabase Storage

**0 bucket, 0 objet.** Métadonnées lisibles avec le rôle courant — le résultat
est donc un constat, pas une limitation de privilège.

Aucun fichier Raw/Bronze/Silver/Gold n'est stocké dans le projet.

---

## 6. Traçabilité Raw → Silver → Gold

**L'architecture décrite dans le document du data engineer n'est pas observable
dans la base connectée.** Ni zone, ni table de quarantaine, ni rapport de
qualité, ni métadonnée dbt, ni log d'ingestion.

Conclusion factuelle : le pipeline décrit est **documenté mais non
matérialisé** dans cette instance. Seul son produit final — les 6 tables du
schéma `public` — est accessible.

---

## 7. Privilèges limitant encore l'inspection

**Aucun.** Le rôle courant lit les catalogues système, contourne les RLS, et
accède aux métadonnées de `storage`. Tous les réglages de sécurité de session
ont été acceptés. Aucune des absences constatées ne s'explique par un défaut de
privilège : **ce sont des absences réelles**.

Distinction appliquée systématiquement :

| Cas | Occurrences |
|---|---|
| Objet lisible avec données | 6 tables `public` |
| Objet lisible mais vide | `storage.buckets`, `storage.objects` |
| Objet existant sans privilège | **aucun** |
| Objet inexistant | `stock_daily`, zones lake, quarantaine, colonnes manquantes |
| Résultat inconclusif | **aucun** |

---

## 8. Écarts entre l'inventaire PostgREST et l'inventaire SQL direct

| Point | PostgREST | SQL direct | Verdict |
|---|---|---|---|
| Tables du schéma `public` | 6 | 6 | identique |
| Comptages | exacts via `count=exact` | exacts via `count(*)` | identiques |
| Clés primaires / étrangères | via OpenAPI | via `pg_constraint` | **identiques** |
| Types de colonnes | formats OpenAPI | `format_type()` | cohérents |
| Autres schémas | `HTTP 406` — ambigu | `pg_namespace` | **tranché : inexistants** |
| Statut RLS | invisible | **activée, 0 politique** | **information nouvelle** |
| Storage | 0 bucket (API) | 0 bucket (SQL) | identique |
| Commentaires de colonnes | invisibles | **confirmés absents** | **information nouvelle** |
| Vues / matérialisées / foreign tables | invisibles | **aucune** | **information nouvelle** |
| Fonctions métier | invisibles | **aucune** | **information nouvelle** |

**Aucune conclusion antérieure n'est infirmée.** L'inspection SQL les confirme
toutes et lève les trois ambiguïtés qui subsistaient : l'inexistence des
schémas de zones, l'absence de commentaires, et la cause du blocage RLS.

---

## 9. Demandes finales au data engineer

**Bloquantes — sans elles, forecasting et pricing restent partiels**

1. **`stock_daily`** (`product_id`, `date`, `stock_level`) — ~118 000 lignes.
   Préciser : stock de fin de journée (le dictionnaire l'indique, à confirmer) ;
   moment d'application du réapprovisionnement ; `stock_level` peut-il être
   négatif ; couverture complète des 300 produits ; initialisation des
   nouveaux produits. **Sans elle, impossible de distinguer demande nulle et
   rupture** : le modèle apprend la contrainte d'offre.
2. **`dim_products.launch_date`** — seule ancienneté commerciale valide.
   `valid_from` ne peut en tenir lieu (le document d'architecture le dit
   explicitement).
3. **`fact_transactions.order_id`** — sans lui : ni nombre de commandes, ni
   panier moyen, ni analyse multi-produits.

**Importantes**

4. **`web_events.session_id` + `event_timestamp`** — la recommandation
   séquentielle en dépend **entièrement**. Le grain a été dégradé de
   `datetime` à `jour`. Perte volontaire ?
5. **`referral_source`** — attribution de canal.
6. **`dim_customers.signup_date`** — contrôle « événement antérieur à
   l'inscription ».
7. **Artefacts de qualité** — où sont les ~425 doublons, ~85 quantités
   négatives et 42 lignes `P99999` écartés ? Aucune table de quarantaine ni
   rapport `great_expectations` n'existe dans l'instance.
8. **Compte exact du fichier Raw** — pour lever l'écart de +29 lignes entre le
   volume attendu (~85 448) et le volume chargé (85 419).
9. **Convention `valid_to`** — inclusive ou exclusive ? Aucune ligne renseignée
   ne permet de trancher, et aucun commentaire de colonne n'existe.
10. **Le prix catalogue variera-t-il ?** Aujourd'hui figé sur les 300 produits :
    l'élasticité ne repose que sur les 7 niveaux de remise.

**À ne surtout pas fournir**

11. **`popularity_score`** — facteur de demande du générateur. Le recevoir
    introduirait une fuite de conception. Son absence actuelle est un atout.

**Point d'architecture, hors périmètre modélisation**

12. RLS activée sans aucune politique sur les 6 tables : toute lecture exige
    aujourd'hui la clé `service_role`. À arbitrer côté data engineer (créer des
    politiques de lecture, ou assumer un accès de service).
