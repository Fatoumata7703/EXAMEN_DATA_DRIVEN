-- ============================================================================
-- Schéma en étoile — Plateforme Pricing & Recommandation E-commerce
-- À coller dans Supabase > SQL Editor, puis charger les CSV via Table Editor
-- (Import data) dans CHAQUE table dans l'ordre : dimensions d'abord, faits ensuite.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- DIMENSIONS
-- ---------------------------------------------------------------------------

create table dim_produit (
    produit_key      text primary key,
    product_id       text not null,
    product_name     text,
    categorie        text,
    marque           text,
    prix_base_xof    numeric,
    cout_xof         numeric,
    valid_from       date,
    valid_to         date,
    is_current       boolean default true
);
create index idx_dim_produit_product_id on dim_produit (product_id);

create table dim_client (
    client_key        text primary key,
    customer_id       text not null,
    region            text,
    age_bracket       text,
    segment_fidelite  text,
    valid_from        date,
    valid_to          date,
    is_current        boolean default true
);
create index idx_dim_client_customer_id on dim_client (customer_id);

create table dim_date (
    date_key       text primary key,
    date_complete  date not null,
    annee          int,
    mois           int,
    jour           int,
    jour_semaine   text,
    est_weekend    boolean
);

create table dim_promotion (
    promo_key      text primary key,
    promotion_id   text not null,
    portee         text,
    cible          text,
    remise_pct     int,
    date_debut     date,
    date_fin       date
);

-- ---------------------------------------------------------------------------
-- TABLES DE FAITS
-- ---------------------------------------------------------------------------

create table fact_ventes (
    vente_id          text primary key,
    produit_key       text references dim_produit (produit_key),
    client_key        text references dim_client (client_key),
    date_key          text references dim_date (date_key),
    promo_key         text references dim_promotion (promo_key),  -- nullable : pas de promo
    quantite          int not null,
    montant_net_xof   numeric not null
);
create index idx_fact_ventes_produit on fact_ventes (produit_key);
create index idx_fact_ventes_client  on fact_ventes (client_key);
create index idx_fact_ventes_date    on fact_ventes (date_key);

create table fact_evenements_web (
    event_id      text primary key,
    produit_key   text references dim_produit (produit_key),
    client_key    text references dim_client (client_key),
    date_key      text references dim_date (date_key),
    type_event    text not null,
    appareil      text
);
create index idx_fact_web_produit on fact_evenements_web (produit_key);
create index idx_fact_web_client  on fact_evenements_web (client_key);
create index idx_fact_web_date    on fact_evenements_web (date_key);

-- fact_stock — ajoutée après coup (oubliée lors de la première conception du schéma).
-- Grain : 1 ligne = niveau de stock d'un produit à la fin d'une journée donnée.
create table fact_stock (
    produit_key   text references dim_produit (produit_key),
    date_key      text references dim_date (date_key),
    niveau_stock  int not null,
    primary key (produit_key, date_key)
);
create index idx_fact_stock_produit on fact_stock (produit_key);
create index idx_fact_stock_date    on fact_stock (date_key);

-- ---------------------------------------------------------------------------
-- Après création : Table Editor > sélectionner la table > Insert > Import data
-- from CSV, dans cet ordre : dim_produit, dim_client, dim_date, dim_promotion,
-- puis fact_ventes, fact_evenements_web (les faits référencent les dimensions,
-- donc elles doivent déjà exister).
--
-- Pour fact_evenements_web (374 792 lignes), l'import UI peut être lent : si
-- besoin, utilise plutôt psql en ligne de commande avec \copy, beaucoup plus
-- rapide pour les gros volumes :
--   \copy fact_evenements_web from 'fact_evenements_web.csv' with (format csv, header true)
-- (chaîne de connexion disponible dans Supabase > Project Settings > Database)
-- ============================================================================
