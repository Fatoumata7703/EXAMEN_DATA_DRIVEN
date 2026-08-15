# 13 — Validation de fact_stock

_Sortie de `python scripts/validate_stock.py`._

```
==============================================================================
1. GRAIN ET UNICITÉ
==============================================================================
  lignes                          : 117,763
  couples (produit, date) distincts : 117,763
  doublons produit-date           : 0  <- doit être 0
  produits distincts              : 300 / 300
  dates : 2025-02-01 -> 2026-07-31 (546 jours)

==============================================================================
2. COUVERTURE PRODUIT-DATE
==============================================================================
  grille théorique complète (300 x 546 j) : 163,800
  lignes fact_stock                                           : 117,763
  écart                                                       : +46,037

  jours de stock par produit : min 35 | médiane 464 | max 546
  produits avec dernière date < 2026-07-31 : 0

  --- Comparaison avec valid_from (dim_produit) ---
  écart (1ère date stock - valid_from) : médiane 0 j, min 0, max 365
  produits où stock démarre EXACTEMENT à valid_from : 180 / 300

  --- Comparaison avec la première vente observée ---
  écart (1ère vente - 1ère date stock) : médiane 0 j, min 0, max 21
  ventes AVANT la première date de stock connue : 0 produit(s)

==============================================================================
3. VALEURS DE STOCK
==============================================================================
  min 21 | médiane 150 | max 499 | moyenne 166.8
  valeurs négatives : 0  <- doit être 0
  valeurs nulles    : 0 (0.00%)
  valeurs manquantes: 0

==============================================================================
4. TROUS TEMPORELS PAR PRODUIT
==============================================================================
  produits avec au moins un trou : 0
  nombre total de trous          : 0

==============================================================================
5. RELATION STOCK <-> VENTES (censure de la demande)
==============================================================================
  produit-jours avec stock_fin_jour = 0           : 0
  ventes POSITIVES un jour où stock_fin_jour = 0   : 0
    -> plausible si niveau_stock est le stock de FIN de journée : les
       ventes du jour ont pu épuiser le stock (vente puis stock=0 le soir).
    part de ces cas / total produit-jours à stock nul : 0.00%

  --- Disponibilité en DÉBUT de journée (proxy = stock de la veille) ---
  produit-jours avec stock_veille <= 0 (rupture probable en entrée de journée) : 0 (0.00%)
  taux de disponibilité (stock_veille > 0)                                    : 100.00%
  ventes positives malgré stock_veille <= 0 : 0 (0.00% des jours en rupture)
    -> un réapprovisionnement peut intervenir EN COURS de journée J : la vente
       est alors possible même si le stock de fin J-1 était nul.

  --- Zéros de vente : avec vs sans rupture (stock_veille <= 0) ---
  zéros AVEC rupture (stock_veille <= 0) : 0
  zéros SANS rupture (stock_veille > 0)  : 59,640
  total zéros observés dans fact_stock (grille stock) : 59,640

==============================================================================
6. SÉQUENCES DE RUPTURE
==============================================================================
  aucune séquence de stock nul détectée.

==============================================================================
7. IMPACT SUR LE TAUX DE ZÉROS DE LA CIBLE (117 763 lignes, 50,77 %)
==============================================================================
  lignes de la table analytique jointes à un stock_veille connu : 117,463 / 117,763 (99.75%)
  zéros de la cible                          : 59,786
  dont avec stock_veille connu                : 59,640
  dont CENSURÉS (stock_veille <= 0)           : 0 (0.00% des zéros documentés)
  dont zéros SANS rupture apparente           : 59,640

  -> sur les 59,786 zéros de la table analytique, 0 (0.00% du total) sont associés à un stock de veille nul ou négatif : ce sont des candidats à la censure, PAS une preuve d'absence de demande.
```
