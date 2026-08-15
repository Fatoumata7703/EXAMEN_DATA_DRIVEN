# 28 — Population éligible pricing

_Généré le 2026-08-14T16:02:21.208174+00:00. Seuils documentés dans `src/pricing/eligibility.py` (hypothèses explicites, pas de valeurs arbitraires cachées)._

## Répartition

| Groupe | Nombre de produits |
|---|---:|
| eligible_individuel | 218 |
| eligible_pooling_categorie | 70 |
| non_eligible | 12 |
| **Total** | **300** |

## Seuils appliqués

- Jours promo ≥ 30, jours hors promo ≥ 30
- Niveaux de remise réels ≥ 2, volume total ≥ 50 unités
- Étalement des promotions ≥ 60 jours calendaires, ≥ 2 mois civils distincts

## Détail par groupe et catégorie

| groupe                     | categorie                |   n_produits |
|:---------------------------|:-------------------------|-------------:|
| eligible_individuel        | Alimentation & Epicerie  |           28 |
| eligible_individuel        | Beaute & Soins           |           26 |
| eligible_individuel        | Bebe & Enfant            |           34 |
| eligible_individuel        | Electronique & High-Tech |           27 |
| eligible_individuel        | Maison & Cuisine         |           30 |
| eligible_individuel        | Mode & Vetements         |           25 |
| eligible_individuel        | Sport & Loisirs          |           17 |
| eligible_individuel        | Telephonie & Accessoires |           31 |
| eligible_pooling_categorie | Alimentation & Epicerie  |           11 |
| eligible_pooling_categorie | Beaute & Soins           |           13 |
| eligible_pooling_categorie | Bebe & Enfant            |            4 |
| eligible_pooling_categorie | Electronique & High-Tech |           12 |
| eligible_pooling_categorie | Maison & Cuisine         |            2 |
| eligible_pooling_categorie | Mode & Vetements         |            9 |
| eligible_pooling_categorie | Sport & Loisirs          |           12 |
| eligible_pooling_categorie | Telephonie & Accessoires |            7 |
| non_eligible               | Alimentation & Epicerie  |            1 |
| non_eligible               | Bebe & Enfant            |            4 |
| non_eligible               | Electronique & High-Tech |            3 |
| non_eligible               | Sport & Loisirs          |            1 |
| non_eligible               | Telephonie & Accessoires |            3 |

## Produits non éligibles (raison exacte)

| unique_id   | categorie                | raison                    |   n_jours_promo |   volume_total |
|:------------|:-------------------------|:--------------------------|----------------:|---------------:|
| PRD000034   | Bebe & Enfant            | aucune promotion observée |               0 |             56 |
| PRD000036   | Electronique & High-Tech | aucune promotion observée |               0 |             85 |
| PRD000040   | Bebe & Enfant            | aucune promotion observée |               0 |             49 |
| PRD000085   | Bebe & Enfant            | aucune promotion observée |               0 |             61 |
| PRD000117   | Telephonie & Accessoires | aucune promotion observée |               0 |            126 |
| PRD000141   | Sport & Loisirs          | aucune promotion observée |               0 |             34 |
| PRD000142   | Telephonie & Accessoires | aucune promotion observée |               0 |             58 |
| PRD000158   | Electronique & High-Tech | aucune promotion observée |               0 |             63 |
| PRD000177   | Bebe & Enfant            | aucune promotion observée |               0 |             42 |
| PRD000202   | Electronique & High-Tech | aucune promotion observée |               0 |             39 |
| PRD000242   | Telephonie & Accessoires | aucune promotion observée |               0 |            148 |
| PRD000256   | Alimentation & Epicerie  | aucune promotion observée |               0 |            145 |
