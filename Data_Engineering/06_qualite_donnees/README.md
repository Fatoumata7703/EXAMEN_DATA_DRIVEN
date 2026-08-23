# Suite great_expectations — qualité des données

Remplace les règles codées à la main (`run_dq_checkpoint` dans `pipeline/transforms.py`)
par une vraie suite `great_expectations`, sans changer où le gate qualité s'exécute
dans le pipeline (toujours entre Bronze et Silver).

**Mise à jour (16 août)** : les règles sur `fact_transactions`/`stock_daily`/`web_events`
ont été réécrites pour correspondre aux données v3 (paniers réels, corrections d'audit
du data scientist) — les noms de colonnes ont changé (`produit_key` au lieu de
`product_id` dans web_events, `ligne_id_origine` comme clé unique de ligne au lieu de
`order_id` qui n'est plus unique par ligne, nouvelles colonnes `order_status`,
`quantite_vendue`, `quantite_reapprovisionnee`).

## ⚠️ Limite honnête de cette livraison

Ce script **n'a pas pu être exécuté** dans l'environnement où il a été écrit — pas
d'accès réseau pour installer `great_expectations`. Pour compenser :
- La syntaxe suit exactement la documentation officielle GX 1.x (API Fluent), vérifiée
  requête par requête sur `docs.greatexpectations.io/docs/core/`.
- Chaque règle a été testée en pandas pur (`dry_run_check.py`) sur les vraies données
  pour confirmer que les colonnes et seuils sont corrects (résultats ci-dessous).
- **Mais l'exécution réelle du script GX (`run_data_quality.py`) n'a pas été validée.**

**Si tu as une erreur en le lançant, montre-la-moi immédiatement** — on la corrige
ensemble plutôt que de deviner. Les erreurs les plus probables, vu l'historique de
l'API GX (beaucoup de changements entre versions) : un nom de méthode légèrement
différent selon la version exacte installée. Si ça arrive, dis-moi la version installée
(`pip show great_expectations`) et le message d'erreur complet.

## Installation et lancement

```bash
pip install great_expectations
python run_data_quality.py
```

Génère un site HTML dans `gx/uncommitted/data_docs/local_site/index.html` — ouvre-le
dans un navigateur, c'est un rapport visuel de chaque règle et de son résultat, une
bonne pièce à montrer pour la soutenance.

## Résultats attendus (vérifiés en pandas pur sur les données v3)

| Table | Règles | Anomalies attendues |
|---|---|---|
| dim_products | 4 | 15 lignes avec catégorie en casse anormale |
| dim_customers | 4 | 0 (les nulls sont sous le seuil de tolérance de 10%) |
| promotions | 3 | 0 |
| fact_transactions | 8 | 0 — toutes les anomalies connues (quantités négatives, FK orphelines) ont déjà été filtrées lors de la régénération v3 |
| stock_daily | 5 | 0 |
| web_events | 4 | 0 |

Si tes résultats diffèrent significativement de ce tableau, quelque chose s'est mal
exécuté — c'est le signal pour me montrer l'erreur plutôt que de continuer.

## Intégration dans le pipeline (pas encore faite)

Pour l'instant, `run_data_quality.py` est un script autonome qui valide les tables et
génère les Data Docs. Il ne remplace pas encore `run_dq_checkpoint()` dans le DAG Airflow
lui-même (qui a besoin d'un masque ligne par ligne pour séparer Silver/rejets, alors que
GX retourne plutôt un statut pass/fail par règle). L'étape suivante, si tu as le temps :
utiliser `unexpected_index_list` dans les résultats GX (avec `result_format=COMPLETE`,
déjà activé dans ce script) pour reconstruire ce même masque et brancher ça dans
`load_silver()`.
