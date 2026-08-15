# 19 — Vérification de la couche opérationnelle

```
==============================================================================
A. CHECKPOINTS BRUTS INCHANGÉS (preuve d'immutabilité)
==============================================================================
  [OK] 42 checkpoints identiques bit à bit entre original et snapshot.
  lignes opérationnelles chargées : 355,145

==============================================================================
B. SCHÉMA DES CHECKPOINTS BRUTS (rejet des anciens formats incompatibles)
==============================================================================
  [OK] Tous les checkpoints bruts portent le schéma attendu.

==============================================================================
C. PRÉDICTIONS NON FINIES — NaN ET +/-Inf, brutes ET finales
==============================================================================
  y_pred_raw non finies : 7976 (NaN=7976, Inf=0)
  [OK] Toutes les prédictions brutes non finies sont couvertes par un repli documenté.
  [OK] 0 prédiction finale non finie.

==============================================================================
D. DOUBLONS ET COUVERTURE EXACTE
==============================================================================
  [OK] 0 doublon (fenêtre, modèle, unique_id, ds).
  [OK] 100 % des observations attendues couvertes, pour chaque (fenêtre, modèle).

==============================================================================
E. REPLIS DOCUMENTÉS ET model_effective
==============================================================================
  [OK] 16,466 replis, tous avec fallback_type et fallback_reason renseignés.
  [OK] model_effective renseigné sur 100 % des lignes.

==============================================================================
F. PRODUIT ABSENT DU TRAIN JAMAIS CLASSÉ « NAIVE »
==============================================================================
  [OK] 6,125 lignes cold-start, toutes classées ColdStartZero (jamais Naive).

==============================================================================
G. COHÉRENCE DES TAUX DE STATUT (somme = 100 %)
==============================================================================
  [OK] Somme des statuts = 100 % pour tous les modèles.

==============================================================================
H. MODÈLE REQUIS JAMAIS ÉCRASÉ
==============================================================================
  [OK] model_requested préserve les 7 noms de modèles d'origine.

==============================================================================
BILAN
==============================================================================
  Tous les contrôles passent. Les résultats opérationnels peuvent être interprétés.
```
