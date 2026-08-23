-- ============================================================================
-- fact_exposition_reco — v4 (21 août)
-- Si la v3 est déjà en base : drop table if exists fact_exposition_reco;
-- ============================================================================

create table fact_exposition_reco (
    recommendation_id                text primary key,
    slate_id                          text not null,
    experiment_id                     text not null,
    assignment_id                      text not null,
    client_key                         text references dim_client (client_key),
    anonymous_id                        text,
    session_id                          text not null,
    model_version                        text not null,   -- déterminé par experiment_group, jamais aléatoire
    model_score                          numeric not null, -- score réellement calculé par le modèle correspondant
    produit_key                         text references dim_produit (produit_key),
    rank                                 int not null,     -- dérivé du tri par model_score, jamais aléatoire
    impression_timestamp                 timestamptz not null,
    viewed_after_impression              boolean not null default false,  -- remplace "clicked" (pas de clic distinct dans la source)
    view_timestamp                       timestamptz,
    added_to_cart_after                   boolean not null default false,
    add_to_cart_timestamp                 timestamptz,
    purchased_after                        boolean not null default false,
    purchase_timestamp                     timestamptz,
    experiment_group                       text not null,
    group_assignment_propensity            numeric not null,  -- P(assigné à ce groupe)
    session_selection_probability           numeric not null,  -- P(session échantillonnée)
    product_exposure_probability            numeric not null   -- P(ce produit exposé | slate)
);
create index idx_fer4_produit on fact_exposition_reco (produit_key);
create index idx_fer4_client on fact_exposition_reco (client_key);
create index idx_fer4_session on fact_exposition_reco (session_id);
create index idx_fer4_slate on fact_exposition_reco (slate_id);
