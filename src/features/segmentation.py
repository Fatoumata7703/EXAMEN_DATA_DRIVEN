"""Segmentation des séries : ADI/CV² (profil de demande), ABC (valeur), XYZ (régularité).

Ces classes servent trois usages :

1. **Diagnostic** : savoir ce que l'on cherche à prévoir avant de choisir un modèle.
2. **Stratégie hybride** : router chaque série vers le modèle adapté à son profil.
3. **Restitution** : ventiler les métriques de backtesting par classe, une erreur
   sur un produit de classe A n'ayant pas le même coût que sur un produit C.

La classification ADI/CV² suit Syntetos, Boylan & Croston (2005) et se calcule
**sur la grille complétée** (zéros inclus dans la fenêtre d'activité) : calculée
sur les seuls jours de vente, elle sous-estimerait mécaniquement l'intermittence.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


@dataclass
class SegmentationConfig:
    adi_threshold: float = 1.32
    cv2_threshold: float = 0.49
    abc_thresholds: tuple[float, float] = (0.8, 0.95)
    xyz_thresholds: tuple[float, float] = (0.5, 1.0)
    min_history_days: int = 90
    min_nonzero_points: int = 12
    inactive_days: int = 60


def compute_series_features(
    table: pd.DataFrame,
    id_col: str = "unique_id",
    date_col: str = "ds",
    value_col: str = "y",
    revenue_col: str | None = "ca",
) -> pd.DataFrame:
    """Statistiques descriptives par série, sur la grille complétée."""
    df = table[[id_col, date_col, value_col] + ([revenue_col] if revenue_col else [])].copy()
    df[date_col] = pd.to_datetime(df[date_col])
    last_date = df[date_col].max()

    grouped = df.groupby(id_col)
    out = pd.DataFrame(
        {
            "debut": grouped[date_col].min(),
            "fin": grouped[date_col].max(),
            "n_jours": grouped[date_col].size(),
            "total": grouped[value_col].sum(),
            "moyenne": grouped[value_col].mean(),
            "ecart_type": grouped[value_col].std(),
            "maximum": grouped[value_col].max(),
        }
    )
    if revenue_col:
        out["ca"] = grouped[revenue_col].sum()

    nonzero = df[df[value_col] > 0]
    nz = nonzero.groupby(id_col)[value_col]
    out["n_jours_vente"] = nz.size().reindex(out.index).fillna(0).astype(int)
    out["taille_demande_moy"] = nz.mean().reindex(out.index)
    out["taille_demande_ecart"] = nz.std().reindex(out.index)
    out["derniere_vente"] = (
        nonzero.groupby(id_col)[date_col].max().reindex(out.index)
    )

    out["taux_jours_sans_vente"] = 1 - out["n_jours_vente"] / out["n_jours"]
    out["jours_inactivite"] = (last_date - out["derniere_vente"]).dt.days

    # ADI : intervalle moyen entre deux demandes non nulles.
    out["adi"] = out["n_jours"] / out["n_jours_vente"].replace(0, np.nan)
    # CV² : dispersion relative des tailles de demande (jours non nuls seulement).
    out["cv2"] = (
        out["taille_demande_ecart"] / out["taille_demande_moy"].replace(0, np.nan)
    ) ** 2
    # Coefficient de variation de la série complète : base de la classe XYZ.
    out["cv_serie"] = out["ecart_type"] / out["moyenne"].replace(0, np.nan)
    return out.reset_index()


def classify(
    features: pd.DataFrame, config: SegmentationConfig | None = None
) -> pd.DataFrame:
    """Ajoute les classes de profil, de cycle de vie, ABC et XYZ."""
    cfg = config or SegmentationConfig()
    df = features.copy()

    def _profile(row: pd.Series) -> str:
        adi, cv2 = row["adi"], row["cv2"]
        if pd.isna(adi) or pd.isna(cv2):
            return "indetermine"
        if adi < cfg.adi_threshold and cv2 < cfg.cv2_threshold:
            return "regulier"
        if adi >= cfg.adi_threshold and cv2 < cfg.cv2_threshold:
            return "intermittent"
        if adi < cfg.adi_threshold and cv2 >= cfg.cv2_threshold:
            return "erratique"
        return "grumeleux"

    df["profil_demande"] = df.apply(_profile, axis=1)

    def _lifecycle(row: pd.Series) -> str:
        if row["jours_inactivite"] is not pd.NaT and row["jours_inactivite"] > cfg.inactive_days:
            return "inactif"
        if row["n_jours"] < cfg.min_history_days:
            return "nouveau"
        if row["n_jours_vente"] < cfg.min_nonzero_points:
            return "historique_insuffisant"
        return "actif"

    df["statut"] = df.apply(_lifecycle, axis=1)

    # --- ABC sur le chiffre d'affaires (à défaut, sur le volume) ----------
    value_col = "ca" if "ca" in df.columns and df["ca"].notna().any() else "total"
    df = df.sort_values(value_col, ascending=False)
    total = df[value_col].sum()
    df["part_cumulee"] = df[value_col].cumsum() / total if total else np.nan
    a_max, b_max = cfg.abc_thresholds
    df["classe_abc"] = np.where(
        df["part_cumulee"] <= a_max, "A", np.where(df["part_cumulee"] <= b_max, "B", "C")
    )

    # --- XYZ sur la régularité (coefficient de variation) ----------------
    x_max, y_max = cfg.xyz_thresholds
    df["classe_xyz"] = np.where(
        df["cv_serie"] <= x_max, "X", np.where(df["cv_serie"] <= y_max, "Y", "Z")
    )
    df["classe_abc_xyz"] = df["classe_abc"] + df["classe_xyz"]

    # --- Modèle recommandé a priori (confirmé/infirmé par le backtesting) -
    def _strategy(row: pd.Series) -> str:
        if row["statut"] == "nouveau" or row["n_jours"] < cfg.min_history_days:
            return "demarrage_a_froid"
        if row["statut"] == "historique_insuffisant":
            return "demarrage_a_froid"
        if row["profil_demande"] in ("intermittent", "grumeleux"):
            return "intermittent"
        return "standard"

    df["groupe_strategie"] = df.apply(_strategy, axis=1)
    return df.sort_values("unique_id").reset_index(drop=True)


def segmentation_summary(classified: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Tableaux de synthèse prêts pour le rapport."""
    out: dict[str, pd.DataFrame] = {}
    for col in ("profil_demande", "statut", "classe_abc", "classe_xyz", "groupe_strategie"):
        if col not in classified.columns:
            continue
        agg = (
            classified.groupby(col)
            .agg(
                n_series=("unique_id", "size"),
                volume=("total", "sum"),
                ca=("ca", "sum") if "ca" in classified.columns else ("total", "sum"),
                taux_zero_moyen=("taux_jours_sans_vente", "mean"),
            )
            .reset_index()
        )
        agg["part_series"] = agg["n_series"] / agg["n_series"].sum()
        agg["part_volume"] = agg["volume"] / agg["volume"].sum()
        out[col] = agg.sort_values("volume", ascending=False)

    if {"classe_abc", "classe_xyz"}.issubset(classified.columns):
        out["matrice_abc_xyz"] = (
            classified.pivot_table(
                index="classe_abc", columns="classe_xyz", values="unique_id", aggfunc="size"
            )
            .fillna(0)
            .astype(int)
            .reset_index()
        )
    return out
