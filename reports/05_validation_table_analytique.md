# 05 — Validation de la table analytique

_Sortie brute de `python scripts/validate_dataset.py`._

```
==============================================================================
1. ORIGINE DES ZEROS
==============================================================================
  lignes fact_ventes                          : 85,419
  lignes avec quantite = 0                    : 0
  lignes avec quantite < 0                    : 0
  lignes avec quantite manquante              : 0
  quantite min / max                          : 1 / 5

  lignes table analytique                     : 117,763
  dont issues d'au moins une transaction      : 57,977
  dont creees ex nihilo (zeros de completion) : 59,786
  lignes y=0 AVEC transaction source          : 0  <- doit etre 0
  total lignes y=0                            : 59,786

  FORMULE : taux_zeros = n_zeros / n_lignes = 59,786 / 117,763 = 50.7681%
  Tous les y=0 proviennent de la completion : 59,786 == 59,786 -> OUI

==============================================================================
2. CONSERVATION DES VENTES
==============================================================================
  SUM(fact_ventes.quantite)      = 155,751
  SUM(table_analytique.y)        = 155,751
  difference                     = 0
  produits avec ecart non nul    : 0 / 300
  mois avec ecart non nul        : 0 / 18

==============================================================================
3. UNICITE DE LA TABLE
==============================================================================
  lignes totales                 : 117,763
  couples (produit, date) distincts : 117,763
  doublons produit-date          : 0
  produits                       : 300
  date min / max                 : 2025-02-01 / 2026-07-31

==============================================================================
4. PERIODE D'ACTIVITE
==============================================================================
  lignes anterieures a valid_from             : 0  <- doit etre 0
  ventes anterieures a valid_from             : 0  <- doit etre 0
  produits sans valid_from                    : 0
  ecart median premiere ligne - valid_from    : 0 j

  Queue de zeros apres la derniere vente (jours) :
    min 0 | median 1 | p95 4 | max 14
    produits avec queue de zeros > 30 j : 0
    produits avec queue de zeros > 60 j : 0
    produits avec queue de zeros > 90 j : 0

==============================================================================
6. JOURS MANQUANTS DANS LA DIMENSION DATE
==============================================================================
  date min / max                 : 2025-02-01 / 2026-07-31
  jours calendaires attendus     : 546
  jours presents dans dim_date   : 546
  dates manquantes               : 0
  ecarts entre jours consecutifs : min 1, max 1 -> consecutifs
  jours distincts AVEC transaction: 546
  -> dim_date couvre 546 jours calendaires consecutifs ; 546 d'entre eux portent au moins une vente

==============================================================================
8. PROMOTIONS
==============================================================================
                  y = 0  y > 0
sans promotion    52751  49488
promotion active   7035   8489

  produit-jours promo active & y=0 : 7,035
  produit-jours promo active & y>0 : 8,489
  produit-jours sans promo & y=0   : 52,751
  produit-jours sans promo & y>0   : 49,488

  remises distinctes dans dim_promotion : [np.int64(5), np.int64(10), np.int64(15), np.int64(20), np.int64(25), np.int64(30), np.int64(40)]
  remises distinctes dans la table      : [np.float64(5.0), np.float64(10.0), np.float64(15.0), np.float64(20.0), np.float64(25.0), np.float64(30.0), np.float64(40.0)]
  toutes issues de dim_promotion        : OUI
  remise non nulle hors promotion       : 0  <- doit etre 0

==============================================================================
9. PRODUITS LANCES A DES DATES DIFFERENTES (3 exemples reels)
==============================================================================
          valid_from 1ere_ligne_table 1ere_vente derniere_ligne  n_lignes
PRD000024 2024-02-02       2025-02-01 2025-02-02     2026-07-31       546
PRD000276 2025-04-26       2025-04-26 2025-04-26     2026-07-31       462
PRD000141 2026-06-27       2026-06-27 2026-06-27     2026-07-31        35

  ecart max |1ere_ligne - valid_from| : 365 j

==============================================================================
10. HISTORIQUE PAR PRODUIT ET INACTIVITE
==============================================================================
  jours d'historique : min 35 | mediane 464 | moyenne 392.5 | max 546
    produits avec < 30 jours : 0
    produits avec < 60 jours : 8
    produits avec < 90 jours : 17
    produits avec < 180 jours : 53

  jours depuis la derniere vente : min 0 | mediane 1 | max 14
    produits sans vente depuis > 30 j : 0
    produits sans vente depuis > 60 j : 0
    produits sans vente depuis > 90 j : 0

==============================================================================
11. STRUCTURE DES SEQUENCES DE ZEROS
==============================================================================
  nombre de sequences de zeros : 27,364
  longueur moyenne  : 2.18 jours
  mediane           : 2
  90e percentile    : 4
  maximum           : 27
    sequences > 7 j : 581
    sequences > 14 j : 35
    sequences > 30 j : 0
    sequences > 60 j : 0

  Produits aux plus longues sequences :
unique_id  longueur
PRD000181        27
PRD000201        24
PRD000118        23
PRD000201        22
PRD000248        21
PRD000125        20
PRD000048        19
PRD000288        18
PRD000131        18
PRD000166        18

==============================================================================
12. SENSIBILITE A LA REGLE DE FIN DE FENETRE
==============================================================================
  points reellement observes (produit-jour avec vente) : 57,977
  valid_to entierement vide : True
  borne gauche commune : max(valid_from, 2025-02-01) plafonnee par la 1ere vente

  scenario         lignes   taux zeros   produits
  A               117,763      50.77%        300   -> derniere date globale (ACTUEL, regle validee)
  B               117,362      50.60%        300   -> derniere vente du produit
  C               117,763      50.77%        300   -> valid_to (sinon date globale)

==============================================================================
7. VERIFICATION DU REMPLISSAGE PAR ZERO
==============================================================================
  lignes y=0 : 59,786

  Colonnes et leur etat sur les lignes y=0 :
    y                NaN=      0  min=0.0  max=0.0   [attendu: 0 (completion)]
    ca               NaN=      0  min=0.0  max=0.0   [attendu: 0]
    n_transactions   NaN=      0  min=0  max=0   [attendu: 0]
    prix_realise     NaN= 59,786  min=nan  max=nan   [attendu: NaN (non observable sans vente)]
    prix_catalogue   NaN=      0  min=660.0  max=448970.0   [attendu: valeur dimension (jamais 0)]
    en_promotion     NaN=      0  min=0  max=1   [attendu: 0 ou 1 selon calendrier]
    remise_pct       NaN=      0  min=0.0  max=40.0   [attendu: 0 hors promo, valeur dim_promotion sinon]
    categorie        NaN=      0  modalites=8   [attendu: attribut dimension]
    marque           NaN=      0  modalites=16   [attendu: attribut dimension]

  prix_catalogue mis a 0 sur lignes y=0    : 0  <- doit etre 0
  prix_realise renseigne sur lignes y=0    : 0  <- doit etre 0

  Evenements web sur lignes y=0 :
    colonnes : ['web_add_to_cart', 'web_purchase', 'web_view', 'web_total', 'web_data_observed']
    moyenne web_total sur y=0 : 1.232
    moyenne web_total sur y>0 : 4.341
    evenements web anterieurs au lancement du produit : 49,589
      -> ces evenements sont hors fenetre d'activite et donc absents de la table

==============================================================================
BILAN
==============================================================================
  Tous les controles structurels passent.
```
