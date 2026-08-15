# 08 — Inspection PostgreSQL directe

_Sortie de `python scripts/inspect_postgres_full.py`. Transaction READ ONLY, SELECT uniquement, identifiants jamais exposés._

```
==============================================================================
INSPECTION POSTGRESQL DIRECTE — TRANSACTION READ ONLY
==============================================================================
  chaîne de connexion lue depuis : $SUPABASE_CONNECTION_STRING
  (valeur jamais affichée, journalisée ni écrite)
  mode de connexion              : pooler
  session read-only      : ACTIVE
  réglages appliqués     : ['statement_timeout', 'lock_timeout', 'idle_in_transaction_session_timeout']

==============================================================================
1. CONTEXTE DE CONNEXION
==============================================================================
  version PostgreSQL   : PostgreSQL 17.6
  base courante        : postgres
  rôle courant         : postgres
  current_schema()     : public
  search_path          : "\$user", public, extensions
  transaction_read_only: on
  port                 : 5432 (connexion directe)
  superuser            : False
  contourne les RLS    : True
  membre des rôles     : ['pg_monitor', 'pg_signal_backend', 'pg_read_all_data', 'pg_create_subscription', 'anon', 'authenticated', 'service_role', 'authenticator', 'supabase_privileged_role']
  lecture des catalogues : OUI (674 objets visibles)

==============================================================================
2. INVENTAIRE DES SCHÉMAS
==============================================================================
  schéma                     catégorie            USAGE    objets
  auth                       interne Supabase     True         23
  extensions                 interne Supabase     True          2
  graphql                    interne Supabase     True          0
  graphql_public             interne Supabase     True          0
  pgbouncer                  interne Supabase     True          0
  public                     APPLICATIF           True          7
  realtime                   interne Supabase     True          3
  storage                    Supabase Storage     True          8
  vault                      interne Supabase     True          2

  -> schémas applicatifs : ['public']

==============================================================================
3. RECHERCHE DES SOURCES MANQUANTES (tous schémas non système)
==============================================================================
  Objets dont le nom évoque une source recherchée : 2
    auth.audit_log_entries                  table                ~-1 lignes
    public.fact_stock                         table                ~117,763 lignes

  Colonnes dont le nom évoque une variable recherchée : 13
    auth.audit_log_entries.payload                  json
    auth.mfa_amr_claims.session_id               uuid
    auth.refresh_tokens.session_id               uuid
    auth.saml_providers.metadata_url             text
    auth.saml_providers.metadata_xml             text
    public.fact_stock.niveau_stock             integer
    realtime.messages.binary_payload           bytea
    realtime.messages.payload                  jsonb
    storage.objects.metadata                 jsonb
    storage.objects.user_metadata            jsonb
    storage.s3_multipart_uploads.metadata                 jsonb
    storage.s3_multipart_uploads.user_metadata            jsonb
    storage.vector_indexes.metadata_configuration   jsonb

==============================================================================
4. OBJETS DES SCHÉMAS APPLICATIFS
==============================================================================

  --- schéma `public` : 7 objet(s) ---
    objet                      type                 est. RLS    SELECT  commentaire
    dim_client                 table               5,000 True   True    
    dim_date                   table                 546 True   True    
    dim_produit                table                 300 True   True    
    dim_promotion              table                 120 True   True    
    fact_evenements_web        table             374,792 True   True    
    fact_stock                 table             117,763 True   True    
    fact_ventes                table              85,419 True   True    

==============================================================================
5. CONTRAINTES DÉCLARÉES (schémas applicatifs)
==============================================================================
  dim_client               PRIMARY KEY  PRIMARY KEY (client_key)
  dim_date                 PRIMARY KEY  PRIMARY KEY (date_key)
  dim_produit              PRIMARY KEY  PRIMARY KEY (produit_key)
  dim_promotion            PRIMARY KEY  PRIMARY KEY (promo_key)
  fact_evenements_web      FOREIGN KEY  FOREIGN KEY (produit_key) REFERENCES dim_produit(produit_key)
  fact_evenements_web      FOREIGN KEY  FOREIGN KEY (date_key) REFERENCES dim_date(date_key)
  fact_evenements_web      FOREIGN KEY  FOREIGN KEY (client_key) REFERENCES dim_client(client_key)
  fact_evenements_web      PRIMARY KEY  PRIMARY KEY (event_id)
  fact_stock               FOREIGN KEY  FOREIGN KEY (produit_key) REFERENCES dim_produit(produit_key)
  fact_stock               FOREIGN KEY  FOREIGN KEY (date_key) REFERENCES dim_date(date_key)
  fact_stock               PRIMARY KEY  PRIMARY KEY (produit_key, date_key)
  fact_ventes              FOREIGN KEY  FOREIGN KEY (produit_key) REFERENCES dim_produit(produit_key)
  fact_ventes              FOREIGN KEY  FOREIGN KEY (promo_key) REFERENCES dim_promotion(promo_key)
  fact_ventes              FOREIGN KEY  FOREIGN KEY (client_key) REFERENCES dim_client(client_key)
  fact_ventes              FOREIGN KEY  FOREIGN KEY (date_key) REFERENCES dim_date(date_key)
  fact_ventes              PRIMARY KEY  PRIMARY KEY (vente_id)

==============================================================================
6. FONCTIONS MÉTIER
==============================================================================
  0 fonction(s) dans les schémas applicatifs
  (aucune n'est exécutée : caractère lecture seule non garanti)

==============================================================================
7. SUPABASE STORAGE (métadonnées)
==============================================================================
  buckets visibles : 0
  objets : 0

==============================================================================
8. STATUT DÉFINITIF DES SOURCES BLOQUANTES
==============================================================================
  source recherchée                statut                   localisation
  stock_daily (table)              PRÉSENT ET LISIBLE       public.fact_stock
  launch_date (colonne)            ABSENT DE L'INSTANCE     —
  order_id (colonne)               ABSENT DE L'INSTANCE     —
  session_id (colonne)             PRÉSENT ET LISIBLE       auth.mfa_amr_claims.session_id, auth.refresh_tokens.session_id
  event_timestamp (colonne)        ABSENT DE L'INSTANCE     —
  referral_source (colonne)        ABSENT DE L'INSTANCE     —
  initial_stock (colonne)          ABSENT DE L'INSTANCE     —
  signup_date (colonne)            ABSENT DE L'INSTANCE     —
  popularity_score (colonne)       ABSENT DE L'INSTANCE     —
  quarantaine / rejets             ABSENT DE L'INSTANCE     —
  zones raw/bronze/silver/gold     ABSENT DE L'INSTANCE     —

==============================================================================
9. SCHÉMA PUBLIC — CONTRÔLE SQL DIRECT
==============================================================================
  table                        estimé      exact RLS    SELECT
  dim_client                    5,000      5,000 True   True
  dim_date                        546        546 True   True
  dim_produit                     300        300 True   True
  dim_promotion                   120        120 True   True
  fact_evenements_web         374,792    374,792 True   True
  fact_stock                  117,763    117,763 True   True
  fact_ventes                  85,419     85,419 True   True

  politiques RLS sur `public` : 0

==============================================================================
FIN — ROLLBACK de la transaction (aucune écriture émise)
==============================================================================
```
