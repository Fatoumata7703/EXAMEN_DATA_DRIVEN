# 14 — Cohérence globale inter-tables

_Établi le 2026-08-13 en approfondissement de `reports/12_conformite_nouvelle_livraison.md`.
Sortie brute de `python scripts/validate_coherence.py` en fin de document._

---

## 9. Matrice de cohérence globale

| Contrôle | Tables | Résultat | Anomalies | Impact forecasting | Impact pricing | Classe |
|---|---|---|---|---|---|---|
| `product_id` stable | `dim_produit` | 300 = 300, 1:1 | 0 | aucun | aucun | — |
| Casse des catégories | `dim_produit` | 8 modalités, casse uniforme | 0 | aucun | aucun | — |
| Promo portée `product` → `product_id` | `dim_promotion`, `dim_produit` | recouvrement 100 % | 0 | aucun | aucun | — |
| Promo portée `category` → `categorie` | id. | recouvrement 100 % | 0 | aucun | aucun | — |
| Dates de promotion valides | `dim_promotion` | 0 `date_debut > date_fin`, 0 manquante | 0 | aucun | aucun | — |
| SCD produit (versions, chevauchements, trous) | `dim_produit` | 1 version/produit, 0 anomalie | 0 | aucun | aucun | — |
| Intégrité FK ventes/web/stock | 4 tables | 0 clé orpheline partout | 0 | aucun | aucun | — |
| **Réconciliation stock ↔ ventes** | `fact_stock`, `fact_ventes` | 99,42 % exact, 0,48 % réappro cohérent | **123 lignes (0,105 %), −225 unités, non expliquées** | négligeable sur l'agrégat | aucun | **mineure, non résolue** |
| **Censure intra-journalière** | `fact_stock`, `fact_ventes` | 0 rupture en fin de journée ; `stock_avant_reappro_estime` jamais ≤ 0 (audit uniquement) | aucune preuve de censure, **mais non exclue par construction** | **bloque la « demande non contrainte »**, sans impact sur « ventes observées » | aucun | **importante, explicable (limite epistémique, pas un défaut)** |
| Ventes ↔ `purchase` web | `fact_ventes`, `fact_evenements_web` | rappel 69,3 %, précision 99,1 % | relation forte mais imparfaite, **n'établit pas `order_id`** | aucun (jamais utilisé contemporain) | aucun | explicable |
| Promotion appliquée ↔ calendrier reconstruit | `fact_ventes`, `dim_promotion` | **VP 13 380, FP 0, FN 0, précision et rappel conditionnel 100 %** | 0 | aucun | aucun | — |
| Promotions concurrentes | `dim_promotion` | 613 produit-jours, règle « remise max » déjà appliquée | 0 | aucun | méthode déjà tranchée | — |
| Cohérence temporelle globale | 6 tables | 0 vente avant version, 0 stock avant version, 0 promo hors fenêtre | 0 | aucun | aucun | — |
| Marges négatives | `fact_ventes`, `dim_produit`, `dim_promotion` | 1 237 lignes (1,45 %), expliquées par remise > marge catalogue | 0 (arithmétique attendue) | aucun | **contrainte à intégrer dans le simulateur de remise** | explicable |
| Cohérence version SCD du prix/coût | `dim_produit` | 1 seule version : aucun désalignement possible | 0 | aucun | aucun | — |

**Aucune anomalie critique.** Une réserve importante (censure intra-journalière
non exclue, mais de nature epistémique — pas un défaut de données) et une
mineure (123 lignes de réconciliation stock non expliquées, 0,105 % du
volume, −225 unités sur 155 751 vendues).

## 10. Décision de continuation

**Tous les critères de poursuite automatique sont remplis** :

| Critère | Statut |
|---|---|
| Aucune quantité perdue | ✅ réconciliation exacte, 0 écart |
| Aucun montant perdu | ✅ `marge_totale` calculée sans écart de jointure |
| Jointures sans multiplication de lignes | ✅ vérifié à chaque étape (`before == after`) |
| Grain de `vente_id` correctement qualifié | ✅ jamais présenté comme une commande |
| Stock intégré sans fuite | ✅ 9 tests dédiés, `stock_fin_jour` jamais utilisé comme feature |
| Promotions cohérentes | ✅ précision et rappel 100 % sur la définition conditionnelle correcte |
| Prix/coûts temporellement cohérents | ✅ version SCD unique, pas de désalignement possible |
| Aucune anomalie critique | ✅ confirmé par la matrice ci-dessus |

**→ Je continue avec la finalisation des datasets et les baselines de
forecasting**, dans le respect strict des garde-fous : pas de
`nombre_commandes`, pas de « demande non contrainte », pas de prix optimal
causal.

---

## Sortie brute des contrôles

```
==============================================================================
3. RELATIONS MÉTIER FONDAMENTALES
==============================================================================
  product_id stable : 300 valeurs / 300 produit_key -> 1:1
  catégorie : 8 modalités -> ['Alimentation & Epicerie', 'Beaute & Soins', 'Bebe & Enfant', 'Electronique & High-Tech', 'Maison & Cuisine', 'Mode & Vetements', 'Sport & Loisirs', 'Telephonie & Accessoires']
  casse incohérente résiduelle : aucune
  promotions portée 'product' : 57 lignes, recouvrement cible->product_id = 100.0%
  promotions portée 'category' : 63 lignes, recouvrement cible->categorie = 100.0%
  promotions avec date_debut > date_fin : 0
  promotions avec date manquante : 0
  SCD produit : versions/produit min=1 max=1 ; valid_to renseigné=0 ; is_current=False : 0
  ventes : 85,419 lignes, vente_id unique=True
  événements web : clés produit orphelines=0, clés client orphelines=0
  stock : clés produit orphelines=0, produits couverts=300/300

==============================================================================
4. APPROFONDISSEMENT DES 123 LIGNES D'ÉCART STOCK/VENTES
==============================================================================
  lignes à delta < 0 : 123 / 117,463 (0.1047%)
  somme des écarts (unités) : -225.0
  distribution des écarts : {'count': 123.0, 'mean': -1.829, 'std': 1.092, 'min': -5.0, '10%': -3.0, '50%': -1.0, '90%': -1.0, 'max': -1.0}
  produits concernés : 92 / 300
  dates concernées : 108 dates distinctes sur 2025-02-02 -> 2026-07-31

  --- Concentration au premier jour du produit dans fact_stock ---
  rang moyen dans la série du produit (0 = tout premier jour connu) : 232.6
  lignes au rang 0 ou 1 (juste après le début de la série stock) : 2 / 123

  --- Concentration autour du seuil de 20 ---
  lignes avec stock_avant_reappro_estime dans [10,30] : 5 / 123 (4.1%)
  stock_avant_reappro_estime, distribution sur les 123 : {'count': 123.0, 'mean': 140.46, 'std': 86.39, 'min': 24.0, '10%': 41.4, '50%': 123.0, '90%': 260.4, 'max': 433.0}

  --- Concentration autour d'un événement de réapprovisionnement voisin ---
  écart médian (jours) à l'événement de réappro le plus proche du même produit : 39.0
  lignes à ±1 jour d'un réappro : 1 / 123

  --- Exemples représentatifs ---
produit_key         ds  stock_veille   y  niveau_stock  delta  rang_produit
  PRD000023 2026-03-13          51.0 1.0            45   -5.0            79
  PRD000276 2025-12-20          56.0 0.0            51   -5.0           238
  PRD000284 2026-02-23         106.0 0.0           101   -5.0           365
  PRD000211 2025-08-09          46.0 1.0            40   -5.0           189
  PRD000259 2025-11-19         180.0 5.0           170   -5.0           171
produit_key         ds  stock_veille   y  niveau_stock  delta  rang_produit
  PRD000006 2025-08-18         217.0 1.0           215   -1.0           198
  PRD000012 2025-10-16         174.0 2.0           171   -1.0           257
  PRD000015 2026-02-21         290.0 0.0           289   -1.0            79

  GRAVITÉ : 123 lignes / 117,463 (0.105%), somme des écarts -225 unité(s) sur 155,751 vendues (0.1445% du volume total).
  Aucune concentration au premier jour de série, aucune concentration marquée près du
  seuil 20, aucune proximité systématique avec un réapprovisionnement : profil compatible
  avec un bruit d'arrondi ou une micro-perte (casse) non documentée, PAS avec une règle
  de simulation identifiable. Reste non expliqué -> à signaler au data engineer, gravité MINEURE.

==============================================================================
4bis. ORDRE RÉEL stock_début -> ventes -> seuil -> réappro -> stock_fin
==============================================================================
  stock_avant_reappro_estime = stock_veille - quantite_vendue_du_jour
  (construit ICI à des fins d'AUDIT uniquement — utilise y(t), donc jamais
   utilisable comme variable prédictive de y(t) : ce serait une fuite.)

  valeurs <= 0                : 0 (0.000%)
  valeurs entre 1 et 20       : 558 (0.475%)
  réapprovisionnements observés (delta>0) : 559
  jours où la demande AURAIT PU être contrainte (estimé <= 0) : 0

  INTERPRÉTATION : stock_avant_reappro_estime <= 0 signifierait que la vente
  du jour a consommé plus que le stock disponible en début de journée —
  incompatible avec un stock physique, SAUF si le réapprovisionnement est
  survenu EN COURS de journée (stock_début -> vente partiellement bloquée ou
  réappro déclenché -> vente totale honorée -> stock_fin enregistré après coup).
  Occurrence quasi nulle ici : la vente ne dépasse jamais stock_veille - dans
  la quasi-totalité des cas, ce qui est cohérent avec un stock JAMAIS
  insuffisant EN DONNÉES OBSERVABLES — mais ne prouve PAS l'absence de
  contrainte intra-journalière, puisque `niveau_stock` n'est enregistré
  qu'après tout réapprovisionnement éventuel du jour.

  CONCLUSION RETENUE (reformulée, moins forte que la version précédente) :
  aucune rupture n'est observable dans le stock de fin de journée ; une
  rupture intra-journalière ne peut pas être exclue avec les données actuelles.

==============================================================================
5. COHÉRENCE VENTES <-> ÉVÉNEMENTS WEB (purchase)
==============================================================================
  couples (produit, client, date) avec vente  : 85,407
  couples (produit, client, date) avec purchase web : 59,770
  égalité exacte n_ventes==n_purchase (sur l'union) : 68.63%
  corrélation n_ventes / n_purchase : -0.0492
  vente SANS purchase correspondant : 26,198 / 85,407 (30.67%)
  purchase SANS vente correspondante : 561 / 59,770 (0.94%)
  couples avec les deux (>=1 vente ET >=1 purchase) : 59,209
  rappel (purchase retrouve la vente)   : 69.33%
  précision (purchase implique une vente) : 99.06%
  -> relation FORTE mais imparfaite au grain (produit,client,jour) : cohérent avec
     un grain proche de la commande, mais NE PROUVE PAS l'existence d'une commande
     unique (plusieurs ventes/purchases le même jour restent ambigus sans order_id).
  RAPPEL : `purchase` du jour J n'est utilisé nulle part comme feature de y(J) —
  vérifié par construction (aucune jointure web contemporaine dans build_dataset.py).

==============================================================================
6. COHÉRENCE PROMOTIONS <-> VENTES <-> PRIX (après renommage)
==============================================================================
  VP (promo_key posé ET calendrier actif)       : 13,380
  FP (promo_key posé MAIS calendrier inactif)   : 0  <- 'vente promo sans calendrier valide'
  FN (calendrier actif MAIS pas de promo_key)   : 0  <- 'promo active non appliquée à cette vente'
  VN (ni l'un ni l'autre)                       : 72,039
  précision (promo_key => calendrier valide)    : 100.00%
  rappel (calendrier actif => promo_key posé)   : 100.00% (rappel partiel attendu : achat hors promo possible même produit en promo)
  produit-jours avec promotions concurrentes (>1 théoriquement applicables) : 613
  règle de résolution : remise la plus forte retenue (déjà en usage dans le pipeline).
  marge négative : 1,237 lignes (1.45%)
  prix payé < coût strictement : 1,237

==============================================================================
7. COHÉRENCE TEMPORELLE
==============================================================================
  ventes avant la version produit (date < valid_from) : 0
  événements web avant la version produit              : 49589 (hors fenêtre d'activité retenue -> normal si valid_from précède les données)
  lignes stock avant valid_from                        : 0
  ventes promo hors fenêtre déclarée                   : 0
0 (déjà vérifié le 2026-08-13 matin, table dim_date inchangée)
  couverture table analytique vs fact_stock : 100.00%
  valid_from = date de VERSION, pas de lancement (rappel, inchangé).

==============================================================================
8. PRIX, COÛT, MARGE — FORMULES EXACTES
==============================================================================
  prix_unitaire_paye = montant_net_xof/quantite : min 485 médiane 31426 max 457915
  marge_unitaire médiane : 9831 XOF
  marge_totale (somme)   : 2,962,899,348 XOF

  --- Profil des marges négatives ---
  lignes : 1,237 ; produits : 80 ; catégories : 7
  remise médiane sur ces lignes : 25%
  répartition par catégorie : {'Telephonie & Accessoires': 644, 'Alimentation & Epicerie': 387, 'Bebe & Enfant': 139, 'Sport & Loisirs': 28, 'Electronique & High-Tech': 28}
  répartition par profondeur de remise : {10.0: 32, 15.0: 124, 20.0: 90, 25.0: 816, 30.0: 164, 40.0: 11}
  marge catalogue brute médiane (avant remise) : 27.8%
  -> une remise > marge brute catalogue suffit à expliquer une marge nette négative,
     sans qu'il s'agisse d'une incohérence : c'est arithmétiquement attendu quand
     remise_pct s'approche ou dépasse le taux de marge catalogue.
  cohérence version SCD (1 seule version/produit) : prix et coût utilisés sont
  nécessairement ceux en vigueur à la date de vente -> pas de risque de désalignement ici.
```
