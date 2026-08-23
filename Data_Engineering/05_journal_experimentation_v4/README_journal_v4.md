# Journal d'exposition et d'expérimentation — v4

## Correctif post-livraison (22 août) — bug réel trouvé par l'audit DS (`P-12`), confirmé et corrigé

L'audit indépendant de la DS (contrôle `P-12`, voir leur rapport final §6.3) a signalé
que `product_impressions` était **constante par produit sur toute la période** dans la
livraison v4 initiale — la variable n'a pas été utilisée telle quelle, la DS l'a
reconstruite elle-même. **Vérifié et confirmé exact** : requête de contrôle
(`select produit_key, count(distinct product_impressions) from
fact_experimentation_prix group by produit_key having count(distinct
product_impressions) = 1`) retournait bien 300/300 produits sur la donnée alors en
base.

**Cause racine identifiée** : bug d'unité dans le calcul du cumul strictement
antérieur. `pandas.Series.values.astype("int64")` sur une colonne datetime tz-aware
récente donne des timestamps en **microsecondes**, alors que `pandas.Timestamp.value`
(utilisé pour `decision_timestamp` dans la recherche binaire) est toujours en
**nanosecondes** — écart de facteur 1000. Résultat : la recherche binaire plaçait
systématiquement la date de décision tout à la fin du tableau trié des impressions,
renvoyant le total complet de la période au lieu du cumul avant décision — exactement
l'anomalie décrite par le contrôle `P-12`.

**Correction** : cast explicite en `datetime64[ns, UTC]` avant extraction, pour
garantir la même unité des deux côtés de la comparaison.

**Vérifié après correction** :
- 191/300 produits montrent désormais une vraie progression croissante dans le temps ;
- 92/300 produits restent à 0 partout — **légitime**, ce sont exactement les produits
  jamais présents dans `fact_exposition_reco_v4` (vérifié : correspondance exacte) ;
- 17/300 produits restent à une valeur constante non nulle — cas légitime (exposition
  concentrée en tout début de période pour ce produit, puis plus jamais revu) ;
- Tous les autres contrôles déjà validés (persistance du traitement, cohérence
  prix/discount, garde-fous, etc.) restent au vert après correction.

**Nouvelle empreinte** : `b65a40e97fa1e3d35b78c2558af52283302bd93185e034d0e6fcfdad8bef9163`
(remplace `db7463fd4c4bda4a292e4abc9bccd16fa8501ddf4651cb4a7da78622be11e52f`).

Ce correctif ne touche que `product_impressions` — `units_sold_window_7j`,
`revenue_window_xof_7j` et `margin_window_xof_7j` ne dépendent pas de cette variable
(calculés uniquement à partir de `discount_applied` et de la demande de base), donc
l'analyse de significativité (`analyse_significativite_v4.py`) reste valide sans
ré-exécution.


Réponse complète à l'audit du 20-21 août. Statut des deux tables : **`synthetic_academic_experiment`**
— données entièrement simulées, dans un cadre académique, aucune expérimentation réelle
en production. Ne jamais présenter les effets mesurés comme des résultats commerciaux réels.

## Lignage

| | fact_exposition_reco v4 | fact_experimentation_prix v4 |
|---|---|---|
| Script | `fact_exposition_reco_v4.py` | `fact_experimentation_prix_v4.py` |
| Seed | 47 | 48 |
| Lignes | 221 080 | 11 799 |
| Empreinte SHA256 | `93de084db8df66bdbd6875efd06fd07e19823b4a769d96a8c033db44d9871148` | `db7463fd4c4bda4a292e4abc9bccd16fa8501ddf4651cb4a7da78622be11e52f` |
| Entrées | dim_produit, fact_ventes, fact_evenements_web (Gold) | dim_produit, fact_stock, fact_exposition_reco_v4, dim_promotion (Gold) |

**Preuve de reproductibilité** : les deux scripts ont été ré-exécutés dans un
environnement propre avec la même seed — empreintes SHA256 **identiques au bit près**
entre les deux exécutions (vérifié, pas supposé).

## Tableau des anomalies — v3 vs v4

### fact_exposition_reco

| # | Anomalie (audit v3) | Statut v3 | Correction v4 |
|---|---|---|---|
| 1-3 | Slates construits avec connaissance du futur de la session (fuite) | ❌ Non détecté par les contrôles v3 | Slate scoré exclusivement avec des informations strictement antérieures à `impression_timestamp` (popularité/affinité glissantes sur 4 semaines, décalées d'une semaine) |
| 3 | Échantillonnage différent achat/non-achat | ❌ | Taux unique de 25%, appliqué uniformément à toutes les sessions non-bot |
| 4-7 | `model_version` aléatoire, `model_score` non calculé, rang non dérivé du score | ❌ | Deux politiques réelles (`popularite_globale_v1` / `challenger_affinite_categorie_v1`), score effectivement calculé, rang = tri par score |
| 9-10 | "clicked" simulé, actions non filtrées sur l'après-impression | ❌ | `viewed_after_impression` (renommé, sémantique conforme à la source), actions conservées uniquement si postérieures à l'impression |
| 11 | Une seule probabilité, mal définie | ❌ | 3 probabilités distinctes : `group_assignment_propensity`, `session_selection_probability`, `product_exposure_probability` |

### fact_experimentation_prix

| # | Anomalie (audit v3) | Statut v3 | Correction v4 |
|---|---|---|---|
| 1 | `product_impressions` à revérifier | 🟡 Déjà correct en v3 | Recalculé depuis fact_exposition_reco v4 (cohérence en cascade) |
| 2 | Chevauchement promo vérifié au lundi seul | ❌ | Vérifié sur la fenêtre complète de 7 jours |
| 3-4 | Prix calculé avant l'éligibilité | ❌ | `prix_applique_xof` recalculé après éligibilité, à partir de `discount_applied` |
| 5 | Warm-up de 89 jours (erreur d'arithmétique) | ❌ | 90 jours exactement, vérifié par assertion dans le script |
| 6 | Plancher de demande silencieux | ❌ | `cold_start_warmup` explicite (147/300 produits, tous lancés après la fin du warm-up — vérifié) |
| 7 | Pas d'outcome de marge | ❌ | `margin_window_xof_7j` ajouté |
| 9-10 | Analyse au grain produit-semaine (pseudo-répliqué) | ❌ | Analyse séparée au grain produit (n=300) — voir `analyse_significativite_v4.py` |

## `fact_exposition_reco` v4 — détail des corrections

**Principe de construction** : un produit n'entre dans un slate que si son score,
calculé avec des données strictement antérieures à l'impression, le place dans le
top-5. Deux politiques réellement différentes :
- **Contrôle** (`popularite_globale_v1`) : popularité glissante sur les 4 semaines
  précédentes (pas cumulée depuis le début — un cumul depuis le début verrouille
  artificiellement les mêmes leaders sur toute la période, corrigé après un premier
  essai qui donnait une diversité trop faible).
- **Traitement** (`challenger_affinite_categorie_v1`) : affinité du client pour la
  catégorie (achats confirmés antérieurs), popularité glissante en repli pour les
  visiteurs sans historique ou anonymes.

**Vérifié** : 57 produits distincts montrés en contrôle, 208 en traitement — différence
réelle et mesurable entre les deux politiques (pas juste une étiquette).

**6 contrôles automatiques, tous à zéro** :
- 0 action retenue comme "après impression" alors qu'elle est antérieure ou simultanée
- 0 exposition sur session bot
- 0 produit dupliqué dans un même slate
- 0 rang dupliqué dans un même slate
- 0 client assigné à plusieurs groupes
- 0 incohérence `model_version` / `experiment_group`

## `fact_experimentation_prix` v4 — détail des corrections

**Warm-up** : 2025-02-01 → 2025-05-02, 90 jours exactement (vérifié par assertion).
**Cold start** : 147/300 produits n'ont aucune vente en warm-up — tous, sans exception,
sont lancés après la fin du warm-up (vérifié). Ce n'est pas un défaut de génération,
c'est une conséquence directe du calendrier de lancement des produits.

**9 contrôles automatiques, tous à zéro** : decision_id dupliqué, stock_at_decision
manquant, produit multi-groupes, discount_applied > discount_proposed, garde-fou violé,
prix_applique incohérent avec discount_applied, margin_window incohérente,
chevauchement de la fenêtre 7 jours avec une promo historique, statut_experience incorrect.

## Analyse de significativité (`analyse_significativite_v4.py`)

Grain d'analyse : **le produit** (n≈300, une observation par produit — moyenne de ses
décisions), pas le produit-semaine (n≈11 800, pseudo-répliqué : le même produit revient
chaque semaine avec le même groupe assigné, donc ses observations ne sont pas
indépendantes entre elles).

Pour chaque comparaison (5%/10%/15% vs contrôle) et chaque outcome (unités vendues,
revenu, marge) : bootstrap (10 000 tirages, IC à 95%), test de permutation (10 000
permutations), puis correction de Holm sur les 3 comparaisons de chaque famille.

**Résultat honnête** : à ce grain, **aucun effet n'est statistiquement significatif
après correction de Holm** (p ajustées entre 0,53 et 1,0). C'est un résultat attendu et
correct — l'effet qui semblait significatif en v3 (3,72 écarts-types) l'était en
grande partie parce que les ~13 000 lignes produit-semaine étaient traitées comme des
observations indépendantes, alors qu'elles ne le sont pas. Avec 300 produits
réellement indépendants, la taille d'échantillon ne permet pas de détecter un effet de
cette ampleur avec le niveau de bruit simulé. Ce n'est pas un échec du pipeline causal
— c'est la démonstration qu'il fonctionne correctement, y compris pour dire "non
significatif" quand c'est le résultat honnête.

## Limites assumées

- Élasticité de demande fixe (1,8) et bruit (15%) — paramètres synthétiques documentés, pas calibrés sur des données réelles.
- Popularité/affinité en résolution hebdomadaire, pas à la timestamp près — simplification computationnelle documentée.
- `product_exposure_probability` calculée via softmax sur les scores du top-5, pas sur tout le catalogue — propension locale au slate, pas globale.
