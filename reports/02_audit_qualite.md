# 02 — Audit de qualité des données

_Généré le 2026-08-13 21:37._

**Bilan : 0 point(s) critique(s), 2 alerte(s) sur 26 contrôles.**

## Volumétrie

| table | lignes |
| --- | --- |
| fact_evenements_web | 374792 |
| fact_stock | 117763 |
| fact_ventes | 85419 |
| dim_client | 5000 |
| dim_date | 546 |
| dim_produit | 300 |
| dim_promotion | 120 |



## Fréquence et granularité observées

- Fréquence détectée : **D**
- Détail : `{"ecart_modal_jours": 1, "part_ecarts_1j": 1.0, "densite_jours_couverts": 1.0, "n_jours_distincts": 546}`
- Séries produit : **300**
- Amplitude de l'historique : **546 jours**
- Densité produit×jour observée (lignes présentes / cellules possibles) : **35.39%**

> Une densité faible signifie que la plupart des couples produit×jour n'ont **aucune ligne** de vente. Cela ne veut pas dire « vente = 0 » : cela peut aussi signifier produit non lancé, indisponible, ou en rupture. Le remplissage par zéro n'est donc appliqué qu'à l'intérieur de la fenêtre d'activité de chaque produit (`target.fill_policy: active_window`).

## Hypothèses retenues

- Date lue directement depuis `fact_ventes.date_key`.
- Clé de jointure produit retenue : `dim_produit.produit_key` (recouvrement des valeurs : 100.0%).
- Ventes enrichies par `dim_produit` sur `produit_key` : ['prix_base_xof', 'categorie', 'marque', 'product_name', 'valid_from'].
- Clé de jointure promotion retenue : `dim_promotion.promo_key` (recouvrement des valeurs : 100.0%).
- Ventes enrichies par `dim_promotion` sur `promo_key` : ['remise_pct', 'date_debut', 'date_fin'].
- Aucune colonne de statut exploitable : quantité nette = quantité brute (les quantités négatives éventuelles sont conservées telles quelles).

## Résultats des contrôles

### 🟠 valeurs_manquantes[dim_client]

1 colonne(s) entièrement vide(s) — valid_to — sans impact sur la cible, mais inutilisable(s) comme variable.

```
{
  "n_colonnes_avec_na": 1,
  "colonnes_obligatoires_incompletes": [],
  "colonnes_entierement_vides": [
    "valid_to"
  ]
}
```

| colonne | taux_na | n_na | interpretation |
| --- | --- | --- | --- |
| valid_to | 1 | 5000 | colonne entièrement vide (structurel) |
| client_key | 0 | 0 | — |
| region | 0 | 0 | — |
| customer_id | 0 | 0 | — |
| age_bracket | 0 | 0 | — |
| segment_fidelite | 0 | 0 | — |
| valid_from | 0 | 0 | — |
| is_current | 0 | 0 | — |



### 🟢 doublons[dim_client]

0 doublon(s) sur la ligne entière. Clé ['client_key'] unique.

```
{
  "doublons_ligne_entiere": 0,
  "n_lignes": 5000,
  "cle_testee": [
    "client_key"
  ],
  "doublons_sur_cle": 0
}
```


### 🟢 valeurs_manquantes[dim_date]

Aucune valeur manquante.

```
{
  "n_colonnes_avec_na": 0,
  "colonnes_obligatoires_incompletes": [],
  "colonnes_entierement_vides": []
}
```

| colonne | taux_na | n_na | interpretation |
| --- | --- | --- | --- |
| date_key | 0 | 0 | — |
| date_complete | 0 | 0 | — |
| annee | 0 | 0 | — |
| mois | 0 | 0 | — |
| jour | 0 | 0 | — |
| jour_semaine | 0 | 0 | — |
| est_weekend | 0 | 0 | — |



### 🟢 doublons[dim_date]

0 doublon(s) sur la ligne entière. Clé ['date_key'] unique.

```
{
  "doublons_ligne_entiere": 0,
  "n_lignes": 546,
  "cle_testee": [
    "date_key"
  ],
  "doublons_sur_cle": 0
}
```


### 🟠 valeurs_manquantes[dim_produit]

1 colonne(s) entièrement vide(s) — valid_to — sans impact sur la cible, mais inutilisable(s) comme variable.

```
{
  "n_colonnes_avec_na": 1,
  "colonnes_obligatoires_incompletes": [],
  "colonnes_entierement_vides": [
    "valid_to"
  ]
}
```

| colonne | taux_na | n_na | interpretation |
| --- | --- | --- | --- |
| valid_to | 1 | 300 | colonne entièrement vide (structurel) |
| produit_key | 0 | 0 | — |
| product_id | 0 | 0 | — |
| product_name | 0 | 0 | — |
| marque | 0 | 0 | — |
| categorie | 0 | 0 | — |
| prix_base_xof | 0 | 0 | — |
| cout_xof | 0 | 0 | — |
| valid_from | 0 | 0 | — |
| is_current | 0 | 0 | — |



### 🟢 doublons[dim_produit]

0 doublon(s) sur la ligne entière. Clé ['produit_key'] unique.

```
{
  "doublons_ligne_entiere": 0,
  "n_lignes": 300,
  "cle_testee": [
    "produit_key"
  ],
  "doublons_sur_cle": 0
}
```


### 🟢 valeurs_manquantes[dim_promotion]

Aucune valeur manquante.

```
{
  "n_colonnes_avec_na": 0,
  "colonnes_obligatoires_incompletes": [],
  "colonnes_entierement_vides": []
}
```

| colonne | taux_na | n_na | interpretation |
| --- | --- | --- | --- |
| promo_key | 0 | 0 | — |
| promotion_id | 0 | 0 | — |
| portee | 0 | 0 | — |
| cible | 0 | 0 | — |
| remise_pct | 0 | 0 | — |
| date_debut | 0 | 0 | — |
| date_fin | 0 | 0 | — |



### 🟢 doublons[dim_promotion]

0 doublon(s) sur la ligne entière. Clé ['promo_key'] unique.

```
{
  "doublons_ligne_entiere": 0,
  "n_lignes": 120,
  "cle_testee": [
    "promo_key"
  ],
  "doublons_sur_cle": 0
}
```


### 🟢 valeurs_manquantes[fact_evenements_web]

Aucune valeur manquante.

```
{
  "n_colonnes_avec_na": 0,
  "colonnes_obligatoires_incompletes": [],
  "colonnes_entierement_vides": []
}
```

| colonne | taux_na | n_na | interpretation |
| --- | --- | --- | --- |
| event_id | 0 | 0 | — |
| produit_key | 0 | 0 | — |
| client_key | 0 | 0 | — |
| date_key | 0 | 0 | — |
| type_event | 0 | 0 | — |
| appareil | 0 | 0 | — |



### 🟢 doublons[fact_evenements_web]

0 doublon(s) sur la ligne entière. Clé ['event_id'] unique.

```
{
  "doublons_ligne_entiere": 0,
  "n_lignes": 374792,
  "cle_testee": [
    "event_id"
  ],
  "doublons_sur_cle": 0
}
```


### 🟢 valeurs_manquantes[fact_stock]

Aucune valeur manquante.

```
{
  "n_colonnes_avec_na": 0,
  "colonnes_obligatoires_incompletes": [],
  "colonnes_entierement_vides": []
}
```

| colonne | taux_na | n_na | interpretation |
| --- | --- | --- | --- |
| produit_key | 0 | 0 | — |
| date_key | 0 | 0 | — |
| niveau_stock | 0 | 0 | — |



### 🟢 doublons[fact_stock]

0 doublon(s) sur la ligne entière. Clé ['produit_key', 'date_key'] unique.

```
{
  "doublons_ligne_entiere": 0,
  "n_lignes": 117763,
  "cle_testee": [
    "produit_key",
    "date_key"
  ],
  "doublons_sur_cle": 0
}
```


### 🟢 valeurs_manquantes[fact_ventes]

1 colonne(s) avec des manquants ; pire cas promo_key = 84.3% (vide attendu (clé optionnelle)).

```
{
  "n_colonnes_avec_na": 1,
  "colonnes_obligatoires_incompletes": [],
  "colonnes_entierement_vides": []
}
```

| colonne | taux_na | n_na | interpretation |
| --- | --- | --- | --- |
| promo_key | 0.8434 | 72039 | vide attendu (clé optionnelle) |
| produit_key | 0 | 0 | colonne obligatoire |
| vente_id | 0 | 0 | — |
| client_key | 0 | 0 | — |
| date_key | 0 | 0 | colonne obligatoire |
| quantite | 0 | 0 | colonne obligatoire |
| montant_net_xof | 0 | 0 | colonne obligatoire |



### 🟢 doublons[fact_ventes]

0 doublon(s) sur la ligne entière. Clé ['vente_id'] unique.

```
{
  "doublons_ligne_entiere": 0,
  "n_lignes": 85419,
  "cle_testee": [
    "vente_id"
  ],
  "doublons_sur_cle": 0
}
```


### 🟢 couverture_temporelle

Historique du 2025-02-01 au 2026-07-31 (546 j), 546 jours distincts avec ventes (100.0% de couverture), écart modal entre jours = 1 j.

```
{
  "date_min": "2025-02-01T00:00:00",
  "date_max": "2026-07-31T00:00:00",
  "span_days": 546,
  "jours_distincts": 546,
  "taux_couverture_jours": 1.0,
  "ecart_modal_jours": 1,
  "n_dates_invalides": 0
}
```


### 🟢 ruptures_calendrier

Aucune rupture de plus d'un jour dans le calendrier global.


### 🟢 valeurs_negatives

0 valeur(s) négative(s) au total sur les colonnes numériques clés.

```
{
  "total_negatifs": 0
}
```

| role | colonne | n_negatifs | n_zeros | n_non_numerique | min | max | moyenne |
| --- | --- | --- | --- | --- | --- | --- | --- |
| quantite | quantite | 0 | 0 | 0 | 1 | 5 | 1.823 |
| montant | montant_net_xof | 0 | 0 | 0 | 499 | 2.284e+06 | 1.459e+05 |
| prix_unitaire | prix_dim | 0 | 0 | 0 | 660 | 4.49e+05 | 8.222e+04 |
| remise | remise_pct_dim | 0 | 0 | 0 | 5 | 40 | 14.95 |



### ⚪ retours_annulations

Aucune colonne de statut/retour identifiée : impossible de distinguer ventes valides, annulations et retours sans information métier complémentaire.


### 🟢 coherence_montants

Meilleure formule : « quantite x prix x (1 - remise/100) » — 100.0% des lignes concordent à ±5 %. Le ratio réel/attendu s'étale de 0.9800 à 1.0200 autour d'une médiane de 1.0000 : l'écart résiduel est un bruit multiplicatif borné, pas une incohérence de définition.

```
{
  "meilleure_formule": "quantite x prix x (1 - remise/100)",
  "taux_concordance_5pct": 1.0,
  "ratio_reel_sur_attendu": {
    "p0.1": 0.9800340522133939,
    "mediane": 1.0,
    "p99.9": 1.0199616122840691
  }
}
```

| formule | ≤0.5% | ≤1.0% | ≤2.0% | ≤5.0% | ≤10.0% | err_rel_mediane |
| --- | --- | --- | --- | --- | --- | --- |
| quantite x prix x (1 - remise/100) | 0.2493 | 0.4993 | 0.9902 | 1 | 1 | 0.01002 |
| quantite x prix | 0.2102 | 0.4206 | 0.8351 | 0.857 | 0.8842 | 0.01187 |
| quantite x prix x (1 - remise) | 0.2102 | 0.4206 | 0.8351 | 0.8434 | 0.8434 | 0.01187 |
| quantite x prix - remise | 0.2102 | 0.4206 | 0.8351 | 0.8571 | 0.8849 | 0.01187 |



### 🟢 integrite[ventes->produit]

0 clé(s) de fait sur 300 sans correspondance dans la dimension (0.00%).

```
{
  "n_cles_faits": 300,
  "n_orphelines": 0,
  "exemples": [],
  "n_cles_dimension": 300
}
```


### 🟢 integrite[ventes->client]

0 clé(s) de fait sur 5000 sans correspondance dans la dimension (0.00%).

```
{
  "n_cles_faits": 5000,
  "n_orphelines": 0,
  "exemples": [],
  "n_cles_dimension": 5000
}
```


### 🟢 integrite[ventes->promotion]

0 clé(s) de fait sur 97 sans correspondance dans la dimension (0.00%).

```
{
  "n_cles_faits": 97,
  "n_orphelines": 0,
  "exemples": [],
  "n_cles_dimension": 120
}
```


### 🟢 dates_lancement

Aucune vente antérieure à la date de mise en vente déclarée : la colonne est une véritable date de lancement, exploitable comme borne de début de série et comme variable d'âge produit. Délai médian entre lancement et première vente : 2 jour(s).

```
{
  "n_ventes_avant_lancement": 0,
  "taux": 0.0,
  "delai_median_jours": 2.0,
  "delai_max_jours": 372.0
}
```


### 🟢 fenetres_promotions

100.00% des ventes promues tombent dans la fenêtre déclarée (13380 / 13380). La dimension promotion est donc fiable pour reconstruire un calendrier promotionnel produit×jour, y compris sur l'horizon futur.

```
{
  "taux_dans_fenetre": 1.0,
  "n_ventes_promues": 13380
}
```


### 🟢 periodes_atypiques

1 jour(s) atypique(s) sur 546 (|z robuste| > 3.0), soit 0.2% de l'historique.

```
{
  "n_atypiques": 1,
  "n_jours": 546
}
```

| date | total | z_robuste |
| --- | --- | --- |
| 2025-12-28 00:00:00 | 587 | 3.033 |



### 🟢 couverture_promotions

15.7% des lignes de vente sont en promotion ; 76.0% des jours et 96.0% des produits sont concernés au moins une fois.

```
{
  "part_lignes_promo": 0.15663962350296773,
  "part_jours_avec_promo": 0.76007326007326,
  "part_produits_promus": 0.96
}
```


## Typologie des séries

**Profil de demande (Syntetos-Boylan-Croston, seuils ADI=1.32 / CV²=0.49)**

| profil | n_series | part |
| --- | --- | --- |
| grumeleux | 166 | 0.5533 |
| intermittent | 129 | 0.43 |
| erratique | 4 | 0.01333 |
| regulier | 1 | 0.003333 |



**Statut de cycle de vie**

| statut | n_series | part |
| --- | --- | --- |
| actif | 283 | 0.9433 |
| nouveau_ou_trop_court | 17 | 0.05667 |



**Top 15 séries par volume**

| unique_id | total | n_jours_avec_vente | span_jours | taux_jours_sans_vente | adi | cv2 | profil_demande | statut_cycle_vie |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| PRD000070 | 1457 | 406 | 546 | 0.2564 | 1.345 | 0.5587 | grumeleux | actif |
| PRD000252 | 1453 | 405 | 545 | 0.2569 | 1.346 | 0.5477 | grumeleux | actif |
| PRD000127 | 1451 | 408 | 545 | 0.2514 | 1.336 | 0.5227 | grumeleux | actif |
| PRD000243 | 1395 | 408 | 546 | 0.2527 | 1.338 | 0.4643 | intermittent | actif |
| PRD000180 | 1368 | 399 | 545 | 0.2679 | 1.366 | 0.5719 | grumeleux | actif |
| PRD000095 | 1311 | 384 | 487 | 0.2115 | 1.268 | 0.5495 | erratique | actif |
| PRD000299 | 1276 | 390 | 546 | 0.2857 | 1.4 | 0.5056 | grumeleux | actif |
| PRD000173 | 1234 | 375 | 542 | 0.3081 | 1.445 | 0.5455 | grumeleux | actif |
| PRD000169 | 1221 | 383 | 546 | 0.2985 | 1.426 | 0.473 | intermittent | actif |
| PRD000275 | 1194 | 344 | 430 | 0.2 | 1.25 | 0.4912 | erratique | actif |
| PRD000215 | 1182 | 366 | 546 | 0.3297 | 1.492 | 0.4567 | intermittent | actif |
| PRD000191 | 1168 | 380 | 546 | 0.304 | 1.437 | 0.4831 | intermittent | actif |
| PRD000249 | 1165 | 380 | 545 | 0.3028 | 1.434 | 0.5702 | grumeleux | actif |
| PRD000222 | 1155 | 363 | 546 | 0.3352 | 1.504 | 0.5032 | grumeleux | actif |
| PRD000018 | 1152 | 358 | 546 | 0.3443 | 1.525 | 0.577 | grumeleux | actif |



## Série agrégée (tous produits)

| ds | y |
| --- | --- |
| 2026-07-17 00:00:00 | 347 |
| 2026-07-18 00:00:00 | 385 |
| 2026-07-19 00:00:00 | 441 |
| 2026-07-20 00:00:00 | 354 |
| 2026-07-21 00:00:00 | 325 |
| 2026-07-22 00:00:00 | 290 |
| 2026-07-23 00:00:00 | 359 |
| 2026-07-24 00:00:00 | 324 |
| 2026-07-25 00:00:00 | 390 |
| 2026-07-26 00:00:00 | 491 |
| 2026-07-27 00:00:00 | 364 |
| 2026-07-28 00:00:00 | 353 |
| 2026-07-29 00:00:00 | 332 |
| 2026-07-30 00:00:00 | 319 |
| 2026-07-31 00:00:00 | 311 |


