# 11 — Recommendation avancée : audit des candidats

Statut : audit borné de couverture, sans nouveau ranker lourd ni modification des branches validées.

## Références verrouillées

- Recommandation générale officielle : `popularite_globale`, Recall@10 ≈ 0,0634, NDCG@10 ≈ 0,0363, couverture ≈ 6,22 %.
- Complément panier : Recall@10 ≈ 0,1006, NDCG@10 ≈ 0,0485, couverture ≈ 89,33 %. Ce système reste séparé du recommender général.

## Audit des candidats

Le générateur général déjà validé fournit un plafond candidat@50 inférieur observé de 0,6131 / 0,5834 / 0,5933 / 0,5964 sur les quatre fenêtres. Le gate prochain achat ≥0,50 est donc franchi au niveau candidat, sans injecter les cibles futures. Les sources sont globales, récentes, catégorie, item-item commandes, BM25/SVD/BPR implicites et web historique.

Les 22 460 commandes multi-produits sont conservées pour le complément panier. La métrique de référence end-to-end est publiée, mais le Recall@50 du candidat n’est pas réestimé dans cette étape bornée ; aucun seuil de 0,70 n’est revendiqué.

Le scénario sessionnel reste inutilisable : le diagnostic historique indique une cible déjà vue dans 100 % des cas et une exclusion des articles vus non appliquée. Aucune règle de restitution d’un article déjà présent n’est considérée comme recommandation.

## Ranking et décision

Aucun LightGBM LambdaRank, XGBoost ranking, CatBoostRanker, ALS/BPR ou modèle profond n’est relancé sur les mêmes données. Le prochain achat, le complément panier et la session ont des cibles et métriques strictement séparées. Les features doivent rester antérieures au cutoff ; aucun `purchase` futur ne peut entrer dans le ranking.

La popularité globale demeure le modèle officiel tant qu’un pilote hors échantillon n’apporte pas un gain NDCG stable, avec bootstrap client×fenêtre à IC95 % entièrement positif. Le complément panier reste un système métier indépendant ; aucune causalité ni personnalisation garantie n’est déduite.

## Protocole futur

Après de nouvelles données ou une définition sessionnelle corrigée, exécuter quatre fenêtres temporelles, tuning uniquement antérieur, checkpoints séquentiels, tests de fuite par perturbation, déterminisme, doublons Top-10, éligibilité, diversité, nouveauté, concentration et bootstrap à 95 %. Le reranking métier ne pourra réduire la pertinence de plus de 2 % hors scénario explicitement « découverte ».

## Artefacts

Métadonnées, couverture candidat et manifeste SHA-256 : `models/advanced/recommendation_ranking/`. Aucun write-back Supabase, déploiement, merge ou push n’est autorisé dans ce commit.
