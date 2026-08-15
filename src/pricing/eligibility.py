"""Classification d'éligibilité pricing — trois groupes, jamais un résultat
forcé sur les 300 produits.

Seuils retenus (hypothèses explicites et documentées, configurables — jamais
un choix silencieux) :

* ``MIN_JOURS_PROMO`` / ``MIN_JOURS_HORS_PROMO`` = 30 : minimum pour une
  comparaison intra-produit à calendrier comparable (permet de couvrir au
  moins ~1 mois de chaque régime).
* ``MIN_NIVEAUX_REELS`` = 2 : sans au moins 2 niveaux de remise distincts, il
  n'existe aucune variation à l'intérieur du produit pour estimer un effet
  par niveau (un effet « promo vs pas promo » resterait possible mais pas un
  effet par niveau).
* ``MIN_VOLUME_TOTAL`` = 50 unités vendues sur toute la période : en dessous,
  le bruit de comptage domine (cohérent avec le seuil `min_nonzero_points`
  déjà utilisé côté forecasting, `config/config.yaml`).
* ``MIN_ETALEMENT_JOURS`` = 60 : les jours de promotion doivent s'étaler sur
  au moins 60 jours calendaires (du premier au dernier), pour éviter qu'une
  seule campagne concentrée sur quelques semaines ne soit confondue avec un
  effet remise stable dans le temps.
* ``MIN_MOIS_COUVERTS`` = 2 : les promotions doivent couvrir au moins 2 mois
  civils distincts (contrôle direct de la consigne « variation non
  exclusivement concentrée dans une seule période »).
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

MIN_JOURS_PROMO = 30
MIN_JOURS_HORS_PROMO = 30
MIN_NIVEAUX_REELS = 2
MIN_VOLUME_TOTAL = 50
MIN_ETALEMENT_JOURS = 60
MIN_MOIS_COUVERTS = 2

MIN_VOLUME_POOLING = 5  # en dessous, même le pooling catégorie n'a pas de sens (quasi aucune vente)


@dataclass
class EligibilityResult:
    table: pd.DataFrame  # unique_id, categorie, groupe, raison, + toutes les métriques de seuil

    def counts(self) -> pd.Series:
        return self.table["groupe"].value_counts()


def classify_eligibility(pricing: pd.DataFrame) -> EligibilityResult:
    rows = []
    for uid, g in pricing.groupby("unique_id"):
        categorie = g["categorie"].iloc[0]
        promo = g[g["en_promotion"] == True]  # noqa: E712
        non_promo = g[g["en_promotion"] == False]  # noqa: E712
        n_jours_promo = len(promo)
        n_jours_hors_promo = len(non_promo)
        n_niveaux_reels = promo["remise_planifiee_pct"].nunique()
        volume_total = float(g["quantite_vendue"].sum())
        if n_jours_promo > 0:
            etalement = (promo["ds"].max() - promo["ds"].min()).days + 1
            mois_couverts = promo["ds"].dt.to_period("M").nunique()
        else:
            etalement = 0
            mois_couverts = 0

        criteres = {
            "jours_promo_ok": n_jours_promo >= MIN_JOURS_PROMO,
            "jours_hors_promo_ok": n_jours_hors_promo >= MIN_JOURS_HORS_PROMO,
            "niveaux_reels_ok": n_niveaux_reels >= MIN_NIVEAUX_REELS,
            "volume_ok": volume_total >= MIN_VOLUME_TOTAL,
            "etalement_ok": etalement >= MIN_ETALEMENT_JOURS,
            "mois_couverts_ok": mois_couverts >= MIN_MOIS_COUVERTS,
        }

        if all(criteres.values()):
            groupe, raison = "eligible_individuel", "tous les critères individuels satisfaits"
        elif n_jours_promo >= 1 and volume_total >= MIN_VOLUME_POOLING:
            manquants = [k for k, v in criteres.items() if not v]
            groupe, raison = "eligible_pooling_categorie", f"historique individuel insuffisant ({', '.join(manquants)}), catégorie utilisée"
        else:
            if n_jours_promo == 0:
                raison = "aucune promotion observée"
            elif volume_total < MIN_VOLUME_POOLING:
                raison = f"volume total quasi nul ({volume_total:.0f} unités)"
            else:
                raison = "historique insuffisant même pour le pooling catégorie"
            groupe = "non_eligible"

        rows.append({
            "unique_id": uid, "categorie": categorie, "groupe": groupe, "raison": raison,
            "n_jours_promo": n_jours_promo, "n_jours_hors_promo": n_jours_hors_promo,
            "n_niveaux_reels": int(n_niveaux_reels), "volume_total": volume_total,
            "etalement_jours": etalement, "mois_couverts": mois_couverts,
            **criteres,
        })
    return EligibilityResult(table=pd.DataFrame(rows))
