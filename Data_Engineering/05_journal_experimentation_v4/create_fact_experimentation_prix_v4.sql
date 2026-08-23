-- ============================================================================
-- fact_experimentation_prix — v4 (21 août)
-- Si la v3 est déjà en base : drop table if exists fact_experimentation_prix;
-- ============================================================================

create table fact_experimentation_prix (
    decision_id                    text primary key,
    experiment_id                  text not null,
    produit_key                    text references dim_produit (produit_key),
    decision_timestamp             timestamptz not null,
    treatment_group                text not null,
    eligible_for_discount          boolean not null,
    discount_proposed              int not null,
    discount_applied               int not null,
    prix_applique_xof              numeric not null,   -- recalculé APRÈS éligibilité, à partir de discount_applied
    propensity_score                numeric not null,
    product_impressions             int not null,       -- recalculé depuis fact_exposition_reco v4
    stock_at_decision                int not null,       -- clôture J-1
    categorie                        text,
    classe_abc                       text,               -- warm-up 90 jours inclusif
    cold_start_warmup                boolean not null,   -- explicite : aucune vente pendant le warm-up
    units_sold_window_7j             int not null,
    revenue_window_xof_7j            numeric not null,
    margin_window_xof_7j             numeric not null,   -- nouveau : (prix_applique - cout) x unités
    fenetre_observation_debut        timestamptz not null,
    fenetre_observation_fin          timestamptz not null,
    statut_experience                 text not null default 'synthetic_academic_experiment'
);
create index idx_fep4_produit on fact_experimentation_prix (produit_key);
create index idx_fep4_experiment on fact_experimentation_prix (experiment_id);
create index idx_fep4_treatment on fact_experimentation_prix (treatment_group);
