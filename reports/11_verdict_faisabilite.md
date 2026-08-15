# 11 — Verdict de faisabilité avec la base actuelle

_Établi le 2026-08-13 à partir de mesures réelles :
`scripts/test_signal.py` (backtest exploratoire h=30, 6 fenêtres) et
`scripts/inspect_postgres_full.py`. Aucun modèle présenté ici n'est un livrable._

---

## 0. Le résultat qui commande tout le reste

Backtest des baselines, WAPE moyen sur 6 fenêtres glissantes, **selon le niveau
d'agrégation de la prévision** :

| Modèle | jour × produit | semaine × produit | **h=30 × produit** | jour × catégorie | jour total |
|---|---:|---:|---:|---:|---:|
| MoyenneProduitJour | 1,111 | 0,497 | **0,263** | 0,239 | 0,116 |
| MoyenneProduit | 1,102 | 0,497 | 0,264 | 0,251 | 0,154 |
| Moyenne28j | 1,088 | 0,521 | 0,320 | 0,236 | 0,118 |
| SeasonalNaive7 | 1,324 | 0,654 | 0,500 | 0,277 | 0,085 |
| **Zéro partout** | **1,000** | 1,000 | 1,000 | 1,000 | 1,000 |

**Au grain jour × produit, toutes les baselines sont battues par « prédire zéro
partout ».** Ce n'est pas une anomalie : avec 50,77 % de zéros et une moyenne de
1,32 unité, la prévision qui minimise l'erreur absolue est la **médiane
conditionnelle**, qui vaut 0 pour la majorité des couples produit-jour. WAPE et
MAE sont minimisés par la médiane, RMSE par la moyenne — et de fait, en RMSE, la
moyenne produit fait **1,80 contre 2,22 pour le zéro, soit −19 %**.

**Conclusion méthodologique : au grain journalier produit, la prévision
ponctuelle est dégénérée. La valeur du modèle apparaît dès qu'on agrège.** À
l'horizon métier réel — la quantité cumulée sur 30 jours par produit, qui est
exactement ce dont dépend un réapprovisionnement — le WAPE tombe à **0,263 avec
une simple moyenne produit × jour de semaine**, soit près de quatre fois mieux
que le zéro.

C'est ce qui rend le forecasting **faisable et utile dès maintenant**, à
condition d'énoncer la cible correctement.

---

## 1. Forecasting

### Signal mesuré

| Indicateur | Valeur |
|---|---|
| Part de variance expliquée — niveau produit | 7,42 % |
| — produit × jour de semaine | 9,40 % |
| — produit × mois | 11,13 % |
| — jour de semaine seul | 0,55 % |
| — promotion seule | 0,24 % |
| Effet week-end | **+25,5 %** |
| Amplitude mensuelle (déc. / mars) | **facteur 1,62** |
| Effet promotion | **+21,7 %** |
| Part de zéros | 50,77 % |
| Stabilité inter-fenêtres (écart-type WAPE / moyenne) | 2 à 3 % |

Les effets calendaires et promotionnels sont **réels, stables et connus à
l'avance**. Le bruit de comptage domine au jour le jour, mais s'annule par
agrégation.

### A. Prévision des **ventes observées**

| | |
|---|---|
| **Faisable** | ✅ **OUI** |
| **Cible exacte** | `quantite_vendue_observee` — quantité vendue par produit et par jour, agrégée sur l'horizon |
| **Données utilisées** | 546 j × 300 produits, calendrier (fériés SN, Ramadan, Korité, Tabaski, Magal), promotions planifiées, prix catalogue et attendu, retards de quantité, web décalé, catégorie/marque |
| **Colonnes manquantes** | `stock_daily` (IMPORTANT), `launch_date` (IMPORTANT), les autres UTILE ou HORS PÉRIMÈTRE |
| **Hypothèses** | la politique de réapprovisionnement reste comparable à celle de l'historique ; le calendrier promotionnel futur est connu |
| **Limites** | les ruptures passées sont incorporées au comportement appris : le modèle prévoit ce qui *se vendra* dans un régime d'offre similaire, non ce qui *serait demandé* |
| **Modèles** | baselines (moyenne produit × jour, SNaive, Croston/TSB), LightGBM Poisson/Tweedie, modèle hurdle |
| **Métriques** | **RMSE / déviance de Poisson au grain jour** ; **WAPE, MAE, biais sur la quantité cumulée à l'horizon** ; MASE ; ventilation ABC/catégorie/promo |
| **Confiance** | **élevée** sur h=30 agrégé par produit ; **faible** sur la prévision ponctuelle jour × produit |
| **Valeur métier** | **réelle et immédiate** : réapprovisionnement, planification, budget |

### B. Prévision de la **demande réelle non contrainte**

| | |
|---|---|
| **Faisable** | ❌ **NON, pas de façon défendable** |
| **Cible** | `demande_non_contrainte` — inobservable dans cette base |
| **Colonne manquante** | `stock_daily` — **BLOQUANTE** |
| **Pourquoi** | le dictionnaire indique que les ventes **s'arrêtent** quand le stock atteint 0. Une part inconnue des 59 786 zéros est de la demande censurée. Sans `stock_level`, il est impossible de savoir *lesquels* |
| **Ce qui est mesurable** | séquences de zéros : moyenne 2,18 j, médiane 2, **max 27 j**, aucune > 30 j ; 581 séquences > 7 j, 35 > 14 j |
| **Limite** | ce profil est peu compatible avec des ruptures prolongées, mais **des ruptures courtes et fréquentes resteraient totalement invisibles** |
| **À ne pas faire** | imputer une demande perdue par une méthode non validée ; présenter la prévision des ventes comme une prévision de la demande |

### Classement des colonnes manquantes — forecasting

| Colonne | Ventes observées (A) | Demande non contrainte (B) | Justification |
|---|---|---|---|
| `stock_daily` | **IMPORTANT** | 🔴 **BLOQUANT** | En A, les ventes observées sont cohérentes avec un régime d'offre inchangé ; le stock améliorerait la précision et permettrait un masque de censure. En B, il n'existe aucun substitut |
| `launch_date` | **IMPORTANT** | IMPORTANT | Approximation disponible (`valid_from`, écart médian 1 j sur 180 produits) mais fausse pour les 120 produits antérieurs au jeu de données ; affecte l'ancienneté et le démarrage à froid |
| `order_id` | UTILE | UTILE | La cible est une quantité, pas un nombre de commandes. Utile pour le panier et la désambiguïsation du nommage |
| `initial_stock` | UTILE | UTILE | Sans valeur propre tant que `stock_daily` est absente |
| `event_timestamp` | UTILE | UTILE | Le grain est journalier : l'ordre intra-journée n'apporte rien à cette cible |
| `referral_source` | UTILE | UTILE | Segmentation du trafic, gain marginal attendu |
| `session_id` | **HORS PÉRIMÈTRE** | HORS PÉRIMÈTRE | Indispensable à la recommandation, sans usage pour une quantité journalière |
| `signup_date` | **HORS PÉRIMÈTRE** | HORS PÉRIMÈTRE | Attribut client, sans lien avec la demande produit |
| `popularity_score` | **À REFUSER** | À REFUSER | Paramètre latent du générateur : fuite de conception |

---

## 2. Pricing

### Signal mesuré

| Indicateur | Valeur |
|---|---|
| Produits dont le **prix catalogue varie** | **0 / 300** |
| Produits exposés à ≥ 2 niveaux de remise | **288 / 300** |
| Produits exposés à ≥ 3 niveaux de remise | **263 / 300** |
| Niveaux de remise par produit (médiane) | 4 |
| Campagnes | 120, durée médiane 9 j |
| Produit-jours en promotion | 15 524 (13,2 %) — hors promotion 102 239 |
| Promotions concurrentes | 426 produit-jours |
| Amplitude du prix payé (max/min, médiane) | 1,384 |
| Amplitude **hors promotion** (bruit seul) | **1,0405** |
| Taux de marge | médiane 26,3 % (p5 9,6 %, p95 47,4 %) |
| Lignes à marge négative | 1 237 (**1,45 %**), remise médiane 25 %, 80 produits |

**Support commun par niveau de remise :**

| Remise | Produit-jours | Produits | y moyen |
|---:|---:|---:|---:|
| 0 % | 102 239 | 300 | 1,286 |
| 5 % | 3 801 | 218 | 1,190 |
| 10 % | 3 501 | 207 | 1,782 |
| 15 % | 3 573 | 227 | 1,444 |
| 20 % | 2 024 | 132 | 1,570 |
| 25 % | 1 405 | 116 | 2,228 |
| 30 % | 1 209 | 111 | 1,686 |
| **40 %** | **11** | **1** | 1,909 |

Relation croissante mais **non monotone**, et le niveau 40 % repose sur
**11 produit-jours d'un seul produit** : il est inexploitable.

### A. Analyse descriptive des promotions et des marges

| | |
|---|---|
| **Faisable** | ✅ **OUI, sans réserve** |
| **Données** | `cout_xof`, `prix_base_xof`, `montant_net_xof`, `quantite`, calendrier promotionnel validé (rappel 100 %, précision 100 %) |
| **Variation exploitable** | sans objet — descriptif |
| **Hypothèses** | prix payé = `montant_net_xof / quantite` (exact) |
| **Limites** | aucune de nature méthodologique |
| **Publiable** | CA, marge, taux de marge par produit/catégorie/campagne ; produits et catégories à marge négative ; couverture promotionnelle ; profil de remise |
| **Non publiable** | toute interprétation causale d'un écart de performance entre périodes |

### B. Estimation de l'effet des remises sur les ventes

| | |
|---|---|
| **Faisable** | ✅ **OUI, en V1 encadrée** |
| **Variation exploitable** | 7 niveaux de remise, 288 produits exposés à ≥ 2, **le niveau 40 % exclu** (support insuffisant) |
| **Hypothèses** | l'affectation des campagnes est indépendante de la demande latente — **non vérifiable** sans le générateur |
| **Limites** | biais de sélection des campagnes ; ruptures non observables (une rupture pendant une promotion biaise l'effet vers le bas) ; effet mesuré sur les seuls jours avec vente |
| **Mesure exploratoire** | pente log-log intra-produit **−0,383**, sans contrôle du calendrier ni de la sélection. **Indicative du signal, pas un résultat publiable** |
| **Publiable** | uplift par niveau de remise, en intra-produit, avec intervalle de confiance, contrôles calendaires, et la mention explicite « association observationnelle » |
| **Non publiable** | une élasticité présentée comme un effet causal ; une extrapolation hors des niveaux observés |

### C. Recommandation d'un prix optimal généralisable **hors promotions**

| | |
|---|---|
| **Faisable** | ❌ **NON** |
| **Cause** | **le prix catalogue ne varie pour aucun des 300 produits.** Hors promotion, l'amplitude du prix payé est de 1,0405 — c'est le bruit de ±2 %, dont la corrélation avec la quantité est de **+0,001** |
| **Conséquence** | il n'existe **aucun support empirique** en dehors de la grille {0, 5, 10, 15, 20, 25, 30 %}. Recommander un prix arbitraire reviendrait à extrapoler hors du domaine observé |
| **Point capital** | **ce blocage n'est pas dû à une colonne manquante.** Le dictionnaire décrit `base_price_xof` comme un prix catalogue unique par produit : même en recevant **toutes** les sources, cette variation n'existerait pas. Le scénario 3 ne le débloque pas |
| **Ce qui reste possible** | un **simulateur de remise sous contraintes de marge**, restreint aux niveaux observés, présenté comme une simulation |

### Classement des colonnes — pricing

| Colonne | A (descriptif) | B (effet remise) | C (prix optimal) |
|---|---|---|---|
| `cost_xof` | ✅ **DISPONIBLE** | ✅ disponible | ✅ disponible |
| Prix catalogue | ✅ **DISPONIBLE** | ✅ disponible | ✅ disponible |
| Prix payé | ✅ **DISPONIBLE** (reconstitué) | ✅ disponible | ✅ disponible |
| Promotion / remise appliquée | ✅ **DISPONIBLE** (calendrier validé) | ✅ disponible | ✅ disponible |
| `stock_daily` | UTILE | **IMPORTANT** — une rupture en promotion biaise l'effet vers le bas | IMPORTANT |
| `launch_date` | UTILE | UTILE | UTILE |
| `order_id` | UTILE | UTILE | UTILE |
| **Variation du prix catalogue** | — | — | 🔴 **BLOQUANT — et non fournissable** |

**Une V1 pricing sérieuse est possible sans `stock_daily`**, à condition de se
limiter aux objectifs A et B et d'assumer explicitement le caractère
observationnel de B.

---

## 3. Trois scénarios

### Scénario 1 — Base actuelle uniquement

| | |
|---|---|
| **Livrables** | Prévision de la quantité vendue par produit à 7/14/30/90 j, avec intervalles ; tableau de bord promotions et marges ; simulateur de remise sous contrainte de marge minimale ; backtest complet ventilé |
| **Modèles** | baselines, LightGBM Poisson/Tweedie, hurdle, Croston/TSB ; effet remise en intra-produit avec contrôles |
| **Fiabilité** | **bonne** à l'horizon agrégé (WAPE 0,263 dès la baseline) ; **faible** au jour × produit ; **observationnelle** pour l'effet remise |
| **Risques** | confondre ventes et demande ; sur-interpréter l'effet remise ; extrapoler hors de la grille de remises |
| **Complexité** | faible — socle déjà en place |
| **Restrictions de communication** | dire « quantité vendue prévue », jamais « demande » ; qualifier l'effet remise d'association ; ne publier aucun prix optimal |

### Scénario 2 — Base actuelle + `stock_daily` + `launch_date`

| | |
|---|---|
| **Gain** | partition des zéros entre demande nulle et rupture ; masque `jour_censure_stock` ; features stock décalées ; **estimation de la demande non contrainte** ; ancienneté produit réelle ; effet remise débiaisé des ruptures |
| **Modèles supplémentaires** | modèle de demande entraîné hors jours censurés, ou pondéré ; comparaison des trois stratégies de censure |
| **Fiabilité** | **nettement supérieure** — c'est le saut qualitatif principal |
| **Risques** | méthode de dé-censure à valider ; ne pas imputer de demande fictive |
| **Complexité** | moyenne — l'intégration est déjà spécifiée (tâche #12) |
| **Restrictions** | la demande non contrainte reste une **estimation**, à publier avec son incertitude |

### Scénario 3 — Toutes les sources du dictionnaire

| | |
|---|---|
| **Gain supplémentaire** | `session_id` + `event_timestamp` → **recommandation séquentielle** (aujourd'hui impossible) ; `order_id` → panier, nombre de commandes ; `referral_source` → attribution ; réconciliation Raw exacte |
| **Fiabilité** | maximale sur le périmètre couvert |
| **Ce que cela ne débloque PAS** | ❌ **le prix optimal hors promotions** : `base_price_xof` reste un prix catalogue unique par produit. Aucune source du dictionnaire ne crée de variation tarifaire |
| **Risques** | recevoir `popularity_score` — **à refuser explicitement** |
| **Complexité** | élevée si un vrai pipeline Raw→Gold doit être rejoué |

---

## 4. Verdict

| Cas d'usage | Faisable maintenant ? | Qualité attendue | Données manquantes bloquantes | Données seulement utiles |
|---|---|---|---|---|
| **Forecasting — ventes observées (h=30, agrégé produit)** | ✅ **OUI** | **Bonne** (WAPE 0,263 dès la baseline) | aucune | `stock_daily`, `launch_date`, `order_id`, web détaillé |
| **Forecasting — ventes observées (jour × produit, ponctuel)** | ⚠️ oui, mais dégénéré sous MAE/WAPE | **Faible** — piloter par RMSE/Poisson | aucune | idem |
| **Forecasting — demande non contrainte** | ❌ **NON** | — | **`stock_daily`** | `launch_date`, `initial_stock` |
| **Pricing A — promotions et marges** | ✅ **OUI** | **Bonne** | aucune | `stock_daily`, `order_id` |
| **Pricing B — effet des remises** | ✅ **OUI, encadré** | **Moyenne** (observationnel) | aucune | **`stock_daily`** (important) |
| **Pricing C — prix optimal hors promo** | ❌ **NON** | — | **variation du prix catalogue** (non fournissable) | — |
| **Recommandation séquentielle** | ❌ **NON** | — | **`session_id`, `event_timestamp`** | `referral_source` |

### Réponses directes

**Pouvons-nous commencer le forecasting maintenant ?**
**Oui.** Sur la cible « quantité vendue observée », avec l'horizon agrégé comme
livrable principal. Le signal est mesuré, stable entre fenêtres, et une simple
moyenne produit × jour de semaine atteint déjà un WAPE de 0,263 à h=30.

**Pouvons-nous produire une V1 pricing maintenant ?**
**Oui, pour les objectifs A et B.** Analyse descriptive complète des marges et
promotions, et effet des remises en intra-produit présenté comme une
association. **Non pour l'objectif C** — et aucune donnée manquante ne le
débloquera.

**Devons-nous attendre le data engineer ?**
**Non pour démarrer. Oui pour la demande non contrainte.** Les scénarios 1 et 2
sont séquentiels, pas exclusifs : le travail du scénario 1 est intégralement
réutilisable.

**Que devons-nous demander impérativement ?**
1. `stock_daily` — seul moyen de passer des ventes à la demande ;
2. `launch_date` — ancienneté commerciale réelle ;
3. `session_id` + `event_timestamp` — **uniquement si** la recommandation est
   dans le périmètre attendu.

**Qu'est-ce qui peut être ajouté plus tard ?**
`order_id`, `referral_source`, `signup_date`, `initial_stock`, les artefacts de
quarantaine. Aucun ne bloque forecasting ni pricing.
