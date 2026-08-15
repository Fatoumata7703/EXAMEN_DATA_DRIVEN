# 06 — Documentation du data engineer vs données réelles

_Sortie brute de `python scripts/diagnostic_sources.py`._

```
==============================================================================
A. ANALYSE SCD TYPE 2
==============================================================================

--- dim_produit ---
  lignes                       : 300
  cles de substitution (produit_key) : 300
  identifiants metier (product_id) : 300
  versions par identifiant     : min 1 | median 1 | max 1
  identifiants a >1 version    : 0
  is_current = True            : 300
  valid_to renseigne           : 0
  identifiants a >1 version courante : 0
  identifiants sans version courante : 0
  valid_to anterieur a valid_from    : 0
  chevauchements de fenetres         : 0
  trous entre versions               : 0

--- dim_client ---
  lignes                       : 5,000
  cles de substitution (client_key) : 5,000
  identifiants metier (customer_id) : 5,000
  versions par identifiant     : min 1 | median 1 | max 1
  identifiants a >1 version    : 0
  is_current = True            : 5,000
  valid_to renseigne           : 0
  identifiants a >1 version courante : 0
  identifiants sans version courante : 0
  valid_to anterieur a valid_from    : 0
  chevauchements de fenetres         : 0
  trous entre versions               : 0

  CONSEQUENCE : dim_produit compte 1 version par produit et dim_client
  1 version par client. Le SCD2 est en place STRUCTURELLEMENT mais AUCUNE
  historisation n'a encore eu lieu. La jointure temporelle est donc
  aujourd'hui equivalente a une jointure simple -- ce qui cessera d'etre
  vrai des le premier changement de prix ou de segment.

  ventes dans la fenetre de validite de leur version : 85,419 / 85,419 (100.00%)

==============================================================================
B. VARIABLES ANNONCEES PAR LE DICTIONNAIRE vs REELLEMENT PRESENTES
==============================================================================
  variable source                        table cible            statut
  dim_products.product_id                dim_produit.product_id presente
  dim_products.product_name              dim_produit.product_name presente
  dim_products.category                  dim_produit.categorie  presente
  dim_products.brand                     dim_produit.marque     presente
  dim_products.base_price_xof            dim_produit.prix_base_xof presente
  dim_products.cost_xof                  dim_produit.cout_xof   presente
  dim_products.popularity_score          dim_produit            ABSENTE
  dim_products.launch_date               dim_produit            ABSENTE
  dim_products.initial_stock             dim_produit            ABSENTE
  dim_customers.region                   dim_client.region      presente
  dim_customers.age_bracket              dim_client.age_bracket presente
  dim_customers.signup_date              dim_client             ABSENTE
  dim_customers.loyalty_segment          dim_client.segment_fidelite presente
  dim_customers.full_name                dim_client             ABSENTE
  fact_transactions.order_id             fact_ventes            ABSENTE
  fact_transactions.quantity             fact_ventes.quantite   presente
  fact_transactions.unit_price_xof       fact_ventes            ABSENTE
  fact_transactions.discount_pct_applied fact_ventes            ABSENTE
  fact_transactions.order_date           fact_ventes.date_key   presente
  stock_daily.stock_level                -                      TABLE ABSENTE
  web_events.session_id                  fact_evenements_web    ABSENTE
  web_events.event_timestamp             fact_evenements_web    ABSENTE
  web_events.referral_source             fact_evenements_web    ABSENTE
  web_events.device                      fact_evenements_web.device presente
  web_events.event_type                  fact_evenements_web.type_event presente

  -> 12 variable(s) source absente(s) du warehouse.

==============================================================================
C. RECONCILIATION DES ANOMALIES ANNONCEES
==============================================================================
  Le jeu Raw n'est PAS accessible : la reconciliation porte sur ce qui
  reste observable dans le warehouse (etat final), pas sur le detail des
  lignes rejetees.

  anomalie annoncee                           volume Raw  etat dans Supabase
  doublons exacts fact_transactions                 ~425  0 doublon (vente_id unique sur 85,419)
  quantites negatives                                ~85  0 quantite <= 0
  FK orphelines P99999                                42  0 cle orpheline
  categories en MAJUSCULES                            15  0 categorie en majuscules (8 distinctes)
  nulls region / age_bracket                         ~3%  region 0.00% | age 0.00%
  timestamps web desordonnes                         ~1%  INVERIFIABLE (event_timestamp absent, seul date_key subsiste)

  --- Reconciliation arithmetique des volumes ---
    volume Raw annonce (~)            : 86 000
    - doublons exacts                 :   -425
    - quantites negatives             :    -85
    - FK orphelines P99999            :    -42
    = attendu apres nettoyage         : ~85 448
    volume reel dans fact_ventes      : 85,419
    ecart                             : +29
    -> l'ecart tient a l'imprecision du '~86 000' annonce ; il ne peut
       etre leve qu'avec le compte EXACT du fichier Raw.

  region : 11 modalites -> ['Touba', 'Louga', 'Saint-Louis', 'Diourbel', 'Dakar', 'Mbour', 'Thies', 'Rufisque', 'Kaolack', 'Ziguinchor', 'Non renseigné']
  age_bracket : 6 modalites -> ['25-34', '35-44', '18-24', '45-54', '55+', 'Non renseigné']
  segment_fidelite : 4 modalites -> ['occasionnel', 'nouveau', 'regulier', 'vip']

==============================================================================
D. GRAIN DES VENTES ET NOMMAGE
==============================================================================
  vente_id unique                    : True
  lignes                             : 85,419
  couples (client, date) distincts   : 83,985
  client-jour avec >1 ligne          : 1,414 (max 3 lignes)
  -> order_id est ABSENT : impossible de reconstituer une commande.
     Un meme client peut avoir plusieurs lignes le meme jour, qui peuvent
     appartenir a une seule commande multi-produits ou a plusieurs.
     `n_transactions` doit donc etre renomme `nombre_lignes_vente`.

==============================================================================
E. PRIX PAYE, REMISE ET MARGE
==============================================================================
  prix_unitaire_paye = montant_net_xof / quantite  (reconstitue exactement)
    min 485 | median 31,426 | max 457,915 XOF

  remise appliquee vs remise planifiee (points de pourcentage) :
    median +0.000 | p5 -1.767 | p95 +1.767
    |ecart| <= 2 pts : 99.95%
    -> le bruit de +-2 % identifie precedemment est un ECART ENTRE LE PRIX
       PAYE ET LE PRIX CATALOGUE REMISE, non une incoherence : le
       dictionnaire confirme que unit_price_xof est 'le prix reellement
       paye'. Il est donc porteur d'information pour le pricing.

  lignes SANS promotion : remise appliquee mediane +0.000 pts (etendue -2.01 / +2.02)

  cout_xof present : OUI -> marge calculable
    marge unitaire mediane : 9,831 XOF
    taux de marge : median 26.3% | p5 9.6% | p95 47.4%
    lignes a marge negative : 1,237

  --- Variation de prix par produit (faisabilite de l'elasticite) ---
    niveaux de prix distincts par produit : median 229 | min 16 | max 743
    amplitude max/min par produit : median 1.384 | p95 1.486
    produits dont le PRIX CATALOGUE varie : 0 / 300
    -> le prix catalogue est FIXE (une seule version SCD par produit).
       Seules les promotions font varier le prix paye : l'elasticite ne
       sera identifiable que via l'effet promotionnel.

==============================================================================
F. IMPACT ESTIME DU STOCK MANQUANT
==============================================================================
  lignes de la table analytique     : 117,763
  lignes annoncees pour stock_daily : ~118 000
  ecart                             : +237
  -> la proximite des deux volumes indique que stock_daily couvre le meme
     grain produit x jour sur la meme fenetre. C'est un indice fort que la
     borne launch_date est proche de la borne actuellement reconstituee.

  zeros actuels : 59,786 (50.77%)
  Sans stock_daily, il est IMPOSSIBLE de partitionner ces zeros entre :
    - absence de demande (vrai zero, exploitable) ;
    - rupture de stock (demande censuree, a masquer ou ponderer).
  Le dictionnaire indique que les ventes s'ARRETENT quand le stock atteint 0.
  Une part inconnue des 50,77 % de zeros est donc de la censure, et non de
  la demande nulle. Tout modele entraine sur ces zeros apprend partiellement
  la contrainte d'offre.
```
