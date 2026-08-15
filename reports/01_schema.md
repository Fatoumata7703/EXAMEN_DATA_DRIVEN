# 01 — Schéma réel découvert

_Généré le 2026-08-13 21:37 — backend `postgres`, schéma `public`._

## Vue d'ensemble

| table | lignes | colonnes | cle_primaire |
| --- | --- | --- | --- |
| fact_evenements_web | 374792 | 6 | event_id |
| fact_stock | 117763 | 3 | produit_key, date_key |
| fact_ventes | 85419 | 7 | vente_id |
| dim_client | 5000 | 8 | client_key |
| dim_date | 546 | 7 | date_key |
| dim_produit | 300 | 10 | produit_key |
| dim_promotion | 120 | 7 | promo_key |



## Détail des colonnes

### `dim_client` — 5,000 lignes

| column_name | data_type | udt_name | is_nullable | column_default |
| --- | --- | --- | --- | --- |
| client_key | text | text | NO |  |
| customer_id | text | text | NO |  |
| region | text | text | YES |  |
| age_bracket | text | text | YES |  |
| segment_fidelite | text | text | YES |  |
| valid_from | date | date | YES |  |
| valid_to | date | date | YES |  |
| is_current | boolean | bool | YES | true |



**Échantillon :**

| client_key | customer_id | region | age_bracket | segment_fidelite | valid_from | valid_to | is_current |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CLI000000 | C000001 | Saint-Louis | 25-34 | nouveau | 2026-04-10 |  | True |
| CLI000001 | C000002 | Mbour | 35-44 | regulier | 2026-01-08 |  | True |
| CLI000002 | C000003 | Thies | 55+ | regulier | 2024-01-09 |  | True |
| CLI000003 | C000004 | Dakar | 25-34 | regulier | 2025-10-09 |  | True |
| CLI000004 | C000005 | Thies | 25-34 | nouveau | 2026-02-15 |  | True |



### `dim_date` — 546 lignes

| column_name | data_type | udt_name | is_nullable | column_default |
| --- | --- | --- | --- | --- |
| date_key | text | text | NO |  |
| date_complete | date | date | NO |  |
| annee | integer | int4 | YES |  |
| mois | integer | int4 | YES |  |
| jour | integer | int4 | YES |  |
| jour_semaine | text | text | YES |  |
| est_weekend | boolean | bool | YES |  |



**Échantillon :**

| date_key | date_complete | annee | mois | jour | jour_semaine | est_weekend |
| --- | --- | --- | --- | --- | --- | --- |
| 20250201 | 2025-02-01 | 2025 | 2 | 1 | Saturday | True |
| 20250202 | 2025-02-02 | 2025 | 2 | 2 | Sunday | True |
| 20250203 | 2025-02-03 | 2025 | 2 | 3 | Monday | False |
| 20250204 | 2025-02-04 | 2025 | 2 | 4 | Tuesday | False |
| 20250205 | 2025-02-05 | 2025 | 2 | 5 | Wednesday | False |



### `dim_produit` — 300 lignes

| column_name | data_type | udt_name | is_nullable | column_default |
| --- | --- | --- | --- | --- |
| produit_key | text | text | NO |  |
| product_id | text | text | NO |  |
| product_name | text | text | YES |  |
| categorie | text | text | YES |  |
| marque | text | text | YES |  |
| prix_base_xof | numeric | numeric | YES |  |
| cout_xof | numeric | numeric | YES |  |
| valid_from | date | date | YES |  |
| valid_to | date | date | YES |  |
| is_current | boolean | bool | YES | true |



**Échantillon :**

| produit_key | product_id | product_name | categorie | marque | prix_base_xof | cout_xof | valid_from | valid_to | is_current |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| PRD000000 | P00001 | Teranga Console #1 | Electronique & High-Tech | Teranga | 211520.0 | 152550.0 | 2025-09-27 |  | True |
| PRD000001 | P00002 | Baobab Jouet eveil #2 | Bebe & Enfant | Baobab | 46030.0 | 29095.0 | 2026-02-05 |  | True |
| PRD000002 | P00003 | Cauri Protection ecran #3 | Telephonie & Accessoires | Cauri | 226420.0 | 153995.0 | 2025-02-07 |  | True |
| PRD000003 | P00004 | Atlas Service a the #4 | Maison & Cuisine | Atlas | 9530.0 | 6047.0 | 2024-05-28 |  | True |
| PRD000004 | P00005 | Nova Chargeur solaire #5 | Electronique & High-Tech | Nova | 404580.0 | 296655.0 | 2024-06-24 |  | True |



### `dim_promotion` — 120 lignes

| column_name | data_type | udt_name | is_nullable | column_default |
| --- | --- | --- | --- | --- |
| promo_key | text | text | NO |  |
| promotion_id | text | text | NO |  |
| portee | text | text | YES |  |
| cible | text | text | YES |  |
| remise_pct | integer | int4 | YES |  |
| date_debut | date | date | YES |  |
| date_fin | date | date | YES |  |



**Échantillon :**

| promo_key | promotion_id | portee | cible | remise_pct | date_debut | date_fin |
| --- | --- | --- | --- | --- | --- | --- |
| PRM0000 | PROMO0001 | category | Electronique & High-Tech | 15 | 2025-03-02 | 2025-03-07 |
| PRM0001 | PROMO0002 | category | Electronique & High-Tech | 10 | 2025-09-14 | 2025-09-23 |
| PRM0002 | PROMO0003 | category | Telephonie & Accessoires | 5 | 2026-04-30 | 2026-05-07 |
| PRM0003 | PROMO0004 | product | P00049 | 5 | 2026-02-19 | 2026-02-27 |
| PRM0004 | PROMO0005 | category | Telephonie & Accessoires | 15 | 2025-07-20 | 2025-07-25 |



### `fact_evenements_web` — 374,792 lignes

| column_name | data_type | udt_name | is_nullable | column_default |
| --- | --- | --- | --- | --- |
| event_id | text | text | NO |  |
| produit_key | text | text | YES |  |
| client_key | text | text | YES |  |
| date_key | text | text | YES |  |
| type_event | text | text | NO |  |
| appareil | text | text | YES |  |



**Échantillon :**

| event_id | produit_key | client_key | date_key | type_event | appareil |
| --- | --- | --- | --- | --- | --- |
| E000000001 | PRD000169 | CLI004383 | 20250918 | view | desktop |
| E000000002 | PRD000169 | CLI004383 | 20250918 | add_to_cart | desktop |
| E000000003 | PRD000169 | CLI004383 | 20250918 | purchase | desktop |
| E000000004 | PRD000132 | CLI003877 | 20260304 | view | mobile |
| E000000005 | PRD000132 | CLI003877 | 20260304 | add_to_cart | mobile |



### `fact_stock` — 117,763 lignes

| column_name | data_type | udt_name | is_nullable | column_default |
| --- | --- | --- | --- | --- |
| produit_key | text | text | NO |  |
| date_key | text | text | NO |  |
| niveau_stock | integer | int4 | NO |  |



**Échantillon :**

| produit_key | date_key | niveau_stock |
| --- | --- | --- |
| PRD000003 | 20250201 | 390 |
| PRD000004 | 20250201 | 274 |
| PRD000005 | 20250201 | 482 |
| PRD000006 | 20250201 | 196 |
| PRD000008 | 20250201 | 335 |



### `fact_ventes` — 85,419 lignes

| column_name | data_type | udt_name | is_nullable | column_default |
| --- | --- | --- | --- | --- |
| vente_id | text | text | NO |  |
| produit_key | text | text | YES |  |
| client_key | text | text | YES |  |
| date_key | text | text | YES |  |
| promo_key | text | text | YES |  |
| quantite | integer | int4 | NO |  |
| montant_net_xof | numeric | numeric | NO |  |



**Échantillon :**

| vente_id | produit_key | client_key | date_key | promo_key | quantite | montant_net_xof |
| --- | --- | --- | --- | --- | --- | --- |
| T00059853 | PRD000091 | CLI003087 | 20260325 |  | 2 | 26266.0 |
| T00084360 | PRD000299 | CLI003820 | 20260725 |  | 1 | 162268.0 |
| T00033138 | PRD000230 | CLI002465 | 20251106 |  | 1 | 11486.0 |
| T00070490 | PRD000011 | CLI001179 | 20260518 | PRM0095 | 2 | 13116.0 |
| T00060979 | PRD000282 | CLI000625 | 20260330 |  | 1 | 150796.0 |



## Clés étrangères déclarées

| source_table | source_column | target_table | target_column | constraint_name |
| --- | --- | --- | --- | --- |
| fact_evenements_web | client_key | dim_client | client_key | fact_evenements_web_client_key_fkey |
| fact_evenements_web | date_key | dim_date | date_key | fact_evenements_web_date_key_fkey |
| fact_evenements_web | produit_key | dim_produit | produit_key | fact_evenements_web_produit_key_fkey |
| fact_stock | date_key | dim_date | date_key | fact_stock_date_key_fkey |
| fact_stock | produit_key | dim_produit | produit_key | fact_stock_produit_key_fkey |
| fact_ventes | client_key | dim_client | client_key | fact_ventes_client_key_fkey |
| fact_ventes | date_key | dim_date | date_key | fact_ventes_date_key_fkey |
| fact_ventes | produit_key | dim_produit | produit_key | fact_ventes_produit_key_fkey |
| fact_ventes | promo_key | dim_promotion | promo_key | fact_ventes_promo_key_fkey |



## Mapping proposé (colonne réelle -> rôle métier)

> Cette table est une **proposition heuristique**, pas une vérité. Toute correction se fait dans `config/config.yaml` (section `schema_mapping`), qui est toujours prioritaire.

| table_logique | table_reelle | role | colonne_retenue | score | justification | alternatives |
| --- | --- | --- | --- | --- | --- | --- |
| ventes | fact_ventes | date | date_key | 60 | motif `^date_id$|^id_date$|^date_key$|^date_sk$`, type inattendu (text) |  |
| ventes | fact_ventes | product_key | produit_key | 100 | motif `^(produit_id|id_produit|product_id|id_product|produit_key|product_key)$` |  |
| ventes | fact_ventes | client_key | client_key | 100 | motif `^(client_id|id_client|customer_id|id_customer|client_key)$` |  |
| ventes | fact_ventes | promotion_key | promo_key | 75 | motif `(promotion|promo).*(id|key|sk|code)` |  |
| ventes | fact_ventes | quantity | quantite | 110 | motif `^(quantite|quantity|qte|qty)$`, type numérique |  |
| ventes | fact_ventes | amount | montant_net_xof | 105 | motif `montant_(total|ttc|ht|net|ligne)`, type numérique |  |
| ventes | fact_ventes | unit_price |  |  | aucun candidat |  |
| ventes | fact_ventes | discount |  |  | aucun candidat |  |
| ventes | fact_ventes | status |  |  | aucun candidat |  |
| ventes | fact_ventes | return_flag |  |  | aucun candidat |  |
| ventes | fact_ventes | cancel_flag |  |  | aucun candidat |  |
| ventes | fact_ventes | line_id | vente_id | 100 | motif `^(vente_id|id_vente|ligne_id|id_ligne|sale_id|transaction_id|line_id)$` |  |
| ventes | fact_ventes | order_id |  |  | aucun candidat |  |
| produit | dim_produit | product_key | product_id | 100 | motif `^(produit_id|id_produit|product_id|id_product|produit_key|product_key)$` | produit_key (100) |
| produit | dim_produit | label | product_name | 70 | motif `(libelle|designation|nom_|name)` |  |
| produit | dim_produit | category | categorie | 100 | motif `^(categorie|category|famille|rayon)$` |  |
| produit | dim_produit | subcategory |  |  | aucun candidat |  |
| produit | dim_produit | brand | marque | 100 | motif `^(marque|brand|fabricant|manufacturer)$` |  |
| produit | dim_produit | unit_price | prix_base_xof | 70 | motif `(prix|price)`, type numérique |  |
| produit | dim_produit | launch_date |  |  | aucun candidat |  |
| date | dim_date | date | jour | 80 | motif `^(date|ds|jour|day)$`, type inattendu (integer) | date_complete (70), date_key (60) |
| date | dim_date | line_id |  |  | aucun candidat |  |
| promotion | dim_promotion | promotion_key | promotion_id | 100 | motif `^(promotion_id|id_promotion|promo_id|id_promo|promotion_key)$` | promo_key (75) |
| promotion | dim_promotion | product_key |  |  | aucun candidat |  |
| promotion | dim_promotion | start_date | date_debut | 110 | motif `(date).*(debut|start|from)`, type date |  |
| promotion | dim_promotion | end_date | date_fin | 110 | motif `(date).*(fin|end|to)`, type date |  |
| promotion | dim_promotion | discount_rate | remise_pct | 110 | motif `(remise|reduction|discount).*(taux|pct|rate|pourcentage)`, type numérique |  |
| promotion | dim_promotion | label |  |  | aucun candidat |  |
| web | fact_evenements_web | date | date_key | 60 | motif `^date_id$|^id_date$|^date_key$|^date_sk$`, type inattendu (text) |  |
| web | fact_evenements_web | product_key | produit_key | 100 | motif `^(produit_id|id_produit|product_id|id_product|produit_key|product_key)$` |  |
| web | fact_evenements_web | client_key | client_key | 100 | motif `^(client_id|id_client|customer_id|id_customer|client_key)$` |  |
| web | fact_evenements_web | event_type | type_event | 100 | motif `^(type_evenement|event_type|type_event|evenement|event|action|type)$` | event_id (60) |
| web | fact_evenements_web | session_key |  |  | aucun candidat |  |
| web | fact_evenements_web | line_id | event_id | 95 | motif `^(event_id|id_event|evenement_id|id_evenement)$` |  |
| client | dim_client | client_key | client_key | 100 | motif `^(client_id|id_client|customer_id|id_customer|client_key)$` | customer_id (100) |
| client | dim_client | label |  |  | aucun candidat |  |
| stock | fact_stock | product_key | produit_key | 100 | motif `^(produit_id|id_produit|product_id|id_product|produit_key|product_key)$` |  |
| stock | fact_stock | date | date_key | 60 | motif `^date_id$|^id_date$|^date_key$|^date_sk$`, type inattendu (text) |  |
| stock | fact_stock | stock_level | niveau_stock | 100 | motif `^(niveau_stock|stock_level|stock_niveau|quantite_stock)$` |  |


