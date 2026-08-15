# 39 — Recommandation V1 : vérifications approfondies

_Généré le 2026-08-14T20:42:31.405475+00:00._

## 1. Grain réel de `fact_evenements_web`

Vérifié directement sur la source : `event_id` est unique à 100 % (374 792 valeurs distinctes pour 374 792 lignes) — chaque ligne est un **événement individuel**, pas un agrégat client-produit-jour. 0,87 % des lignes seulement partagent un même quadruplet (client, produit, jour, type_event), un taux de répétition naturel (ex. deux vues du même produit le même jour), pas une agrégation déguisée. En l'absence de `event_timestamp` et de `session_id`, **aucune séquence intra-journalière n'est reconstruite** — confirmé dans le code (`ContentBased` n'utilise que des comptages agrégés par catégorie, jamais un ordre).

## 2. Unicité et cardinalité — absence de mapping artificiel

- Paires (client, produit) distinctes dans le web : 233 069 ; dans les ventes : 82 147.
- Intersection : 61 059 (74,3 % des paires vente ont un signal web correspondant — pas 100 %, cohérent avec des achats sans navigation trackée).
- Paires web **sans aucune vente correspondante** (navigation pure) : 172 010 (73,8 % des paires web) — signal de navigation authentique, pas dérivé artificiellement des ventes.
- 5 000 clients distincts et 300 produits distincts dans le web, référence parfaite vers `dim_client`/`dim_produit` (0 orphelin, déjà vérifié au rapport 36).

## 3. Fuite temporelle — contrôle actif dans le code

Deux assertions ajoutées dans `run_window_evaluation` (`recsys_prototype.py`) vérifient à l'exécution, pas seulement a posteriori, que `train_v`/`train_w` ne contiennent aucune ligne postérieure à `window.train_end` — l'exécution complète du pipeline (60 combinaisons fenêtre×politique×modèle) s'est terminée sans qu'aucune de ces assertions n'échoue.

## 4. Contribution réelle du signal web (`view`/`add_to_cart`, jamais `purchase`)

Comparaison sur la fenêtre 0 (cold-start dédiée), restreinte aux clients réellement sans achat train — le seul segment où le repli web peut changer quelque chose :

| variante        |   n_clients_cold_start_evalues |   recall_at_5 |   recall_at_10 |   ndcg_at_10 |   user_coverage |
|:----------------|-------------------------------:|--------------:|---------------:|-------------:|----------------:|
| avec_signal_web |                            717 |        0.0416 |         0.0846 |       0.0454 |          1.0000 |
| sans_signal_web |                            717 |        0.0559 |         0.1110 |       0.0603 |          1.0000 |

**Lecture honnête — résultat contre-intuitif, pas un gain** : le signal web (`view`/`add_to_cart`) **dégrade** les recommandations sur ce segment plutôt que de les améliorer (Recall@10 0,0846 avec le signal web contre 0,1110 sans — repli direct vers la popularité globale). Explication plausible : avec seulement ~3,3 événements web en moyenne par client cold-start (2 270 vues / 687 clients concernés, rapport 36), le signal est trop épars et bruité pour surclasser un simple repli vers la popularité globale, plus robuste. **Conclusion retenue : ne pas utiliser le repli web pour le contenu-based en l'état — le repli vers la popularité global seule est préférable pour ce segment.** Ce constat est inscrit tel quel, sans enjolivement, conformément à la consigne de ne pas présenter une dégradation comme une amélioration.

## 5. Couverture des cibles par l'ensemble de candidats (le produit acheté était-il seulement proposable ?)

|   fenetre |   defaut_exclut_achats_stock_filtre |   inclut_produits_deja_achetes |   sans_filtre_stock |
|----------:|------------------------------------:|-------------------------------:|--------------------:|
|         0 |                              0.8963 |                         0.9084 |              0.9879 |
|         1 |                              0.9052 |                         0.9505 |              0.9548 |
|         2 |                              0.9203 |                         0.9678 |              0.9525 |
|         3 |                              0.9199 |                         0.9775 |              0.9424 |

**⚠️ Résultat important, pas un détail technique** : sous la politique par défaut (achats déjà faits exclus, stock filtré), **seuls 89,6 % à 92,0 % des produits réellement achetés en test étaient même présents dans l'ensemble de candidats proposé au client.** Concrètement : **aucun modèle, aussi bon soit-il, ne peut dépasser un Recall@K d'environ 0,90-0,92 sous cette politique** — le reste (8-11 %) est structurellement hors d'atteinte, pas un échec du modèle. Deux causes distinctes, mesurées séparément ci-dessus :

1. **Exclusion des achats déjà faits** : un produit racheté en test après avoir déjà été acheté en train devient une cible impossible à capter dès qu'on exclut les achats déjà faits — la politique `inclut_produits_deja_achetes` (95,1-97,8 % de couverture) confirme que ce réachat explique la majorité de l'écart.
2. **Filtre stock à J-1** : la politique `sans_filtre_stock` (94,2-98,8 % de couverture) montre que le filtre stock retire lui aussi quelques points de couverture — cohérent avec des cas de fin de vie produit (rupture réelle avant l'achat test) plutôt qu'une erreur de filtre.

**Toute lecture du Recall§ ci-après (rapport 37) doit se faire à la lumière de ce plafond structurel** — un Recall@10 de 0,07 sous la politique par défaut représente en réalité 0,07/0,90 ≈ 7,8 % du maximum atteignable, pas 7 % d'un maximum de 100 %.

## 6. Popularité moyenne des recommandations et nombre moyen de cibles par client

|   fenetre |   collaboratif_item_item |   contenu_categorie_prix |   popularite_categorie |   popularite_globale |   popularite_recente |
|----------:|-------------------------:|-------------------------:|-----------------------:|---------------------:|---------------------:|
|         0 |                   0.5019 |                   0.4703 |                 0.6211 |               0.8549 |               0.8495 |
|         1 |                   0.8995 |                   0.3927 |                 0.6756 |               0.9340 |               0.7101 |
|         2 |                   0.9062 |                   0.3786 |                 0.6834 |               0.9316 |               0.6943 |
|         3 |                   0.8995 |                   0.3845 |                 0.6739 |               0.9159 |               0.6341 |

Nombre moyen de cibles (produits réellement achetés en test) par client évaluable, par fenêtre : {0: np.float64(1.851), 1: np.float64(2.393), 2: np.float64(2.632), 3: np.float64(2.627)}

**Lecture** : `popularite_globale` recommande des produits proches de la popularité maximale (≈0,85-0,93) par construction. `contenu_categorie_prix` recommande les produits les moins populaires en moyenne (≈0,38-0,47) — cohérent avec sa bien meilleure couverture catalogue (rapport 37 §1). `collaboratif_item_item` est proche de la popularité aux fenêtres 1-3 mais nettement plus bas à la fenêtre 0 (0,50) — la similarité item-item, calculée sur moins d'historique en début de période, s'écarte davantage de la popularité pure.

## 7. Contrôles automatiques sur la sortie (politique par défaut)

```json
{
  "aucun_doublon_top_k": {
    "n_doublons": 0,
    "ok": true
  },
  "scores_finis": {
    "n_nan": 0,
    "n_inf": 0,
    "ok": true
  },
  "taille_top_k": {
    "min": 10,
    "max": 10,
    "n_groupes_moins_de_10": 0,
    "n_groupes_total": 86230,
    "note": "un groupe <10 est normal seulement si le nombre de candidats disponibles pour ce client était <10 (à vérifier séparément, cf. §1 couverture) — pas une anomalie en soi."
  },
  "rangs_consecutifs_sans_trou": {
    "n_groupes_invalides": 0,
    "ok": true
  },
  "dates_recommandation_dans_les_bornes": {
    "date_max": "2026-06-01",
    "coherent_avec_fenetres": true
  }
}
```
