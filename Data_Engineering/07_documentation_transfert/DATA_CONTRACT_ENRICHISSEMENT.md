# Réponse à la demande du 15 août — enrichissement fact_ventes / fact_evenements_web

Réponses aux questions de cadrage, à valider avant implémentation. Comme ce système est
un jeu de données **synthétique** (pas un vrai tracking e-commerce), c'est nous qui
définissons ces règles — donc autant les documenter clairement une bonne fois.

## Réponses aux questions de cadrage

**Règle de début et de fin d'une session**
Une session commence au premier événement d'un visiteur. Elle se termine après **30
minutes d'inactivité** (norme courante, ex. Google Analytics) — le prochain événement
après ce délai ouvre une nouvelle session. Cette règle est déjà implicitement respectée
dans la génération actuelle des événements (les vues précédant un achat sont regroupées
dans une fenêtre de quelques dizaines de minutes) ; elle sera rendue explicite dans les
nouvelles données.

**Rattachement d'une session anonyme au client après connexion**
Toute session contenant un achat est, par définition, rattachée à un `client_key` connu
(on ne simule pas d'achat invité anonyme). Les sessions de navigation pure sans achat
seront désormais réparties entre visiteurs connus (`client_key` rempli) et visiteurs
anonymes (`anonymous_id` rempli, `client_key` vide) — environ 35% des sessions de
navigation seront anonymes, pour refléter le fait que tous les visiteurs ne sont pas
connectés. Il n'y a pas de vraie notion de "connexion en cours de session" dans ce
simulateur : une session est soit anonyme de bout en bout, soit connue de bout en bout.

**Définition exacte d'une commande et de ses lignes**
Une commande (`order_id`) = un panier validé en une seule fois par un client, à une
date donnée. Chaque ligne de `fact_ventes` = un produit + une quantité dans ce panier.
Plusieurs lignes peuvent désormais partager le même `order_id` (1 à 4 produits
différents par panier, distribution réaliste avec la majorité des paniers à 1-2
produits).

**Gestion des annulations et des retours**
Nouveau champ `order_status` sur `fact_ventes` : `confirmee` (~95%), `annulee` (~3%,
annulée avant expédition), `retournee` (~2%, retournée après livraison). Les lignes
annulées/retournées sont **conservées** dans la table (pas supprimées) pour permettre
l'analyse des annulations elles-mêmes — le data scientist doit filtrer sur
`order_status = 'confirmee'` pour les analyses de demande réelle.

**Fuseau horaire**
UTC pour le stockage (`event_timestamp` en ISO 8601 avec offset explicite). Le
marché simulé étant Dakar (UTC+0, pas d'heure d'été), l'heure UTC correspond à l'heure
locale — mais le champ reste explicitement marqué UTC pour éviter toute ambiguïté si
le système est réutilisé sur un autre marché.

**Date à partir de laquelle ces champs sont fiables**
100% du champ historique (2025-02-01 → 2026-07-31) sera régénéré avec ces champs
complets — pas de période partielle, puisqu'on repart de la simulation.

## Champs confirmés disponibles / ajoutés

| Champ demandé | Disponible ? | Note |
|---|---|---|
| `fact_ventes.order_id` (partagé par panier) | ✅ ajouté | |
| `fact_ventes.order_status` | ✅ ajouté | confirmee / annulee / retournee |
| `fact_evenements_web.event_id` | ✅ déjà présent | |
| `fact_evenements_web.session_id` | ✅ ré-ajouté | existait en Silver, avait été perdu en construisant le Gold |
| `fact_evenements_web.event_timestamp` (avec fuseau) | ✅ ajouté | actuellement seul `date_key` était conservé, perte de la précision horaire |
| `fact_evenements_web.event_type` | ✅ déjà présent | **limite honnête** : le simulateur ne modélise que 3 étapes (view / add_to_cart / purchase), pas de "clic" distinct d'une "vue" — les fusionner serait artificiel |
| `fact_evenements_web.client_key` | ✅ déjà présent | rempli uniquement pour visiteurs connus |
| `fact_evenements_web.anonymous_id` | ✅ ajouté | rempli uniquement pour visiteurs anonymes (mutuellement exclusif avec client_key) |
| `fact_evenements_web.produit_key` | ✅ déjà présent | |
| `fact_evenements_web.order_id` (lien achat → commande) | ✅ ajouté | uniquement rempli sur les événements `purchase` |
| `fact_evenements_web.quantity` | ✅ ajouté | uniquement sur les événements `purchase` (reflète la quantité achetée) |
| Canal, appareil, source de trafic | ✅ appareil + source déjà présents | **limite honnête** : un seul canal simulé ("web"), pas d'app mobile distincte |
| Indicateur bot / test / interne | ✅ ajouté | `est_bot` — ~1% des sessions simulées comme trafic bot pour donner un vrai signal filtrable |

## Délai

Implémentation en 2 jours (dans le délai déjà annoncé). On avance étape par étape :
1. Ce document de cadrage (fait)
2. Régénération de `fact_transactions` avec paniers + statuts
3. Régénération de `web_events` avec session/timestamp/anonymous_id/bot
4. Reconstruction du schéma en étoile (uniquement `fact_ventes` et `fact_evenements_web` — les 5 autres tables ne bougent pas)
5. Mise à jour Supabase (ALTER TABLE + réimport de ces 2 tables seulement)
6. Mise à jour de la documentation (data dictionary, handoff, guide tables/modèles)
