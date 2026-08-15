"""Tests d'intégrité de la table analytique (non-régression).

Ces tests s'exécutent sur les artefacts réellement produits :
`data/processed/table_analytique.parquet` confronté à `data/raw/*.parquet`.
Ils sont ignorés si la préparation n'a pas encore été lancée.

Chaque test correspond à un contrôle de `scripts/validate_dataset.py` et vise
une régression précise déjà rencontrée.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.config.settings import PROJECT_ROOT
from src.data.build_dataset import parse_date_key

RAW = PROJECT_ROOT / "data" / "raw"
TABLE = PROJECT_ROOT / "data" / "processed" / "table_analytique.parquet"

pytestmark = pytest.mark.skipif(
    not TABLE.exists() or not (RAW / "fact_ventes.parquet").exists(),
    reason="Lancer d'abord : python -m src.pipelines.extract && python -m src.pipelines.prepare",
)


@pytest.fixture(scope="module")
def table() -> pd.DataFrame:
    df = pd.read_parquet(TABLE)
    df["unique_id"] = df["unique_id"].astype(str)
    df["ds"] = pd.to_datetime(df["ds"])
    return df


@pytest.fixture(scope="module")
def ventes() -> pd.DataFrame:
    df = pd.read_parquet(RAW / "fact_ventes.parquet")
    df["produit_key"] = df["produit_key"].astype(str)
    df["ds"] = parse_date_key(df["date_key"])
    return df


@pytest.fixture(scope="module")
def produits() -> pd.DataFrame:
    df = pd.read_parquet(RAW / "dim_produit.parquet")
    df["produit_key"] = df["produit_key"].astype(str)
    df["valid_from"] = pd.to_datetime(df["valid_from"]).dt.normalize()
    return df


@pytest.fixture(scope="module")
def promotions() -> pd.DataFrame:
    return pd.read_parquet(RAW / "dim_promotion.parquet")


# ---------------------------------------------------------------------------
# 1. Unicité
# ---------------------------------------------------------------------------
def test_pas_de_doublon_produit_date(table):
    doublons = table.duplicated(subset=["unique_id", "ds"]).sum()
    assert doublons == 0, f"{doublons} doublon(s) produit-date"


def test_une_ligne_par_couple(table):
    assert len(table) == table.groupby(["unique_id", "ds"]).ngroups


# ---------------------------------------------------------------------------
# 2. Conservation des quantités
# ---------------------------------------------------------------------------
def test_conservation_globale(table, ventes):
    assert float(table["y"].sum()) == pytest.approx(float(ventes["quantite"].sum()))


def test_conservation_par_produit(table, ventes):
    src = ventes.groupby("produit_key")["quantite"].sum()
    tab = table.groupby("unique_id")["y"].sum()
    ecart = (tab - src.reindex(tab.index).fillna(0)).abs()
    assert (ecart < 1e-6).all(), f"{int((ecart >= 1e-6).sum())} produit(s) en écart"


def test_conservation_par_mois(table, ventes):
    src = ventes.groupby(ventes["ds"].dt.to_period("M"))["quantite"].sum()
    tab = table.groupby(table["ds"].dt.to_period("M"))["y"].sum()
    ecart = (tab - src.reindex(tab.index).fillna(0)).abs()
    assert (ecart < 1e-6).all(), f"{int((ecart >= 1e-6).sum())} mois en écart"


# ---------------------------------------------------------------------------
# 3. Origine des zéros
# ---------------------------------------------------------------------------
def test_aucun_zero_sur_jour_avec_transaction(table):
    faux_zeros = ((table["y"] == 0) & (table["n_transactions"] > 0)).sum()
    assert faux_zeros == 0, f"{faux_zeros} ligne(s) à y=0 malgré une transaction"


def test_aucune_transaction_sans_quantite(table):
    incoherent = ((table["n_transactions"] > 0) & (table["y"] <= 0)).sum()
    assert incoherent == 0


def test_source_sans_quantite_nulle_ou_negative(ventes):
    """L'hypothèse « quantité nette = quantité brute » repose sur ce constat."""
    assert (ventes["quantite"] > 0).all(), (
        "La source contient des quantités nulles ou négatives : "
        "la définition de la cible doit être revue."
    )


# ---------------------------------------------------------------------------
# 4. Fenêtre d'activité
# ---------------------------------------------------------------------------
def test_aucune_ligne_avant_debut_validite(table, produits):
    debut = produits.set_index("produit_key")["valid_from"]
    avant = (table["ds"] < table["unique_id"].map(debut)).sum()
    assert avant == 0, f"{avant} ligne(s) antérieure(s) à valid_from"


def test_aucune_ligne_avant_le_debut_des_donnees(table, ventes):
    """On ne fabrique pas de zéros là où aucune observation n'existe."""
    debut_donnees = ventes["ds"].min()
    assert table["ds"].min() >= debut_donnees


def test_borne_gauche_est_max_validite_et_debut_donnees(table, produits, ventes):
    """Règle A : début = max(valid_from, première date des données), plafonné
    par la première vente observée du produit."""
    debut_donnees = ventes["ds"].min()
    validite = produits.set_index("produit_key")["valid_from"]
    premiere_vente = ventes.groupby("produit_key")["ds"].min()
    attendu = np.minimum(validite.clip(lower=debut_donnees), premiere_vente)
    obtenu = table.groupby("unique_id")["ds"].min()
    ecarts = (obtenu - attendu.reindex(obtenu.index)).dt.days.abs()
    assert (ecarts == 0).all(), (
        f"{int((ecarts != 0).sum())} produit(s) ne démarrent pas à la borne attendue "
        f"(écart max {ecarts.max()} j)"
    )


def test_borne_droite_est_la_derniere_date_globale(table):
    fin = table["ds"].max()
    fins = table.groupby("unique_id")["ds"].max()
    assert (fins == fin).all(), "Toutes les séries doivent se terminer à la même date"


# ---------------------------------------------------------------------------
# 5. Colonnes et nommage
# ---------------------------------------------------------------------------
def test_colonnes_obligatoires_presentes(table):
    attendues = {
        "unique_id",
        "ds",
        "y",
        "product_id",
        "categorie",
        "marque",
        "prix_catalogue",
        "date_debut_validite",
        "age_produit_jours",
        "en_promotion",
        "remise_pct",
    }
    manquantes = attendues - set(table.columns)
    assert not manquantes, f"Colonnes absentes : {sorted(manquantes)}"


def test_product_id_et_categorie_sont_distincts(table, produits):
    """Régression : `categorie` avait été renommée en `product_id`."""
    assert set(table["product_id"].unique()) <= set(produits["product_id"].unique())
    assert set(table["categorie"].unique()) <= set(produits["categorie"].unique())
    assert table["product_id"].nunique() == table["unique_id"].nunique()


def test_categorie_nest_pas_un_identifiant_produit(table):
    """La catégorie compte bien moins de modalités qu'il n'y a de produits."""
    assert table["categorie"].nunique() < table["unique_id"].nunique()


def test_pas_de_colonne_nommee_date_lancement(table):
    """La signification de valid_from n'est pas prouvée : le nom doit rester neutre."""
    assert "date_lancement" not in table.columns


def test_age_produit_coherent(table):
    age = table["age_produit_jours"].dropna()
    assert (age >= 0).all()
    ecart = (table["ds"] - table["date_debut_validite"]).dt.days
    # L'âge est écrêté à 0 pour les produits dont la validité précède les données.
    assert (table["age_produit_jours"] == ecart.clip(lower=0)).all()


# ---------------------------------------------------------------------------
# 6. Remplissage : ce qui doit être à zéro, et ce qui ne doit pas l'être
# ---------------------------------------------------------------------------
def test_remplissage_zero_limite_aux_compteurs(table):
    zeros = table[table["y"] == 0]
    assert (zeros["ca"] == 0).all()
    assert (zeros["n_transactions"] == 0).all()
    # Le prix réalisé n'est pas observable sans vente : il doit rester manquant.
    assert zeros["prix_realise"].isna().all()
    # Le prix catalogue est un attribut de dimension : jamais remis à zéro.
    assert (zeros["prix_catalogue"] > 0).all()


def test_attributs_dimension_jamais_manquants(table):
    for col in ("categorie", "marque", "prix_catalogue", "product_id"):
        assert table[col].notna().all(), f"{col} contient des valeurs manquantes"


def test_indicateur_disponibilite_web(table):
    """Distingue « aucun événement » de « aucune donnée web »."""
    assert "web_data_observed" in table.columns
    observed = table["web_data_observed"] == 1
    # Hors couverture, les compteurs doivent être manquants et non nuls.
    assert table.loc[~observed, "web_total"].isna().all()
    assert table.loc[observed, "web_total"].notna().all()


# ---------------------------------------------------------------------------
# 7. Promotions
# ---------------------------------------------------------------------------
def test_remises_proviennent_de_la_dimension(table, promotions):
    taux_table = set(table.loc[table["en_promotion"] == 1, "remise_pct"].unique())
    taux_dim = set(promotions["remise_pct"].astype(float).unique())
    assert taux_table <= taux_dim


def test_pas_de_remise_hors_promotion(table):
    assert ((table["en_promotion"] == 0) & (table["remise_pct"] != 0)).sum() == 0


def test_promotions_couvrent_les_jours_sans_vente(table):
    """Le calendrier promo doit exister indépendamment des ventes : s'il était
    dérivé de fact_ventes, aucun jour sans vente ne serait marqué en promotion."""
    promo_sans_vente = ((table["en_promotion"] == 1) & (table["y"] == 0)).sum()
    assert promo_sans_vente > 0, (
        "Aucun produit-jour en promotion sans vente : le calendrier promotionnel "
        "semble reconstruit à partir des ventes plutôt que de dim_promotion."
    )


def test_promotions_dans_les_fenetres_declarees(table, ventes, promotions):
    """Toute vente rattachée à une promotion tombe dans sa fenêtre déclarée.

    Colonnes `date_debut`/`date_fin` depuis la livraison du 2026-08-13
    (renommées côté source ; c'étaient `start_date`/`end_date` auparavant —
    voir reports/12_conformite_nouvelle_livraison.md §5). Détection tolérante
    aux deux conventions pour ne pas re-casser au prochain renommage.
    """
    promo = promotions.copy()
    start_col = "date_debut" if "date_debut" in promo.columns else "start_date"
    end_col = "date_fin" if "date_fin" in promo.columns else "end_date"
    promo[start_col] = pd.to_datetime(promo[start_col])
    promo[end_col] = pd.to_datetime(promo[end_col])
    v = ventes[ventes["promo_key"].notna()].merge(promo, on="promo_key", how="left")
    dedans = (v["ds"] >= v[start_col]) & (v["ds"] <= v[end_col])
    assert dedans.all()
