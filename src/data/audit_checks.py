"""Contrôles de qualité des données pour l'audit (phase 1).

Chaque contrôle est défensif : si la colonne nécessaire n'a pas été identifiée
dans le schéma réel, le contrôle renvoie un statut ``non_applicable`` plutôt que
d'échouer ou d'inventer une valeur.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np
import pandas as pd

from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


@dataclass
class CheckResult:
    name: str
    status: str  # ok | alerte | critique | non_applicable
    summary: str
    details: dict[str, Any] = field(default_factory=dict)
    table: pd.DataFrame | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "name": self.name,
            "status": self.status,
            "summary": self.summary,
            "details": _jsonable(self.details),
        }
        if self.table is not None and not self.table.empty:
            payload["table_preview"] = _jsonable(
                self.table.head(50).to_dict(orient="records")
            )
        return payload


def _jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return None if np.isnan(obj) else float(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (pd.Timestamp,)):
        return obj.isoformat()
    if obj is pd.NaT:
        return None
    if isinstance(obj, float) and np.isnan(obj):
        return None
    return obj


# ---------------------------------------------------------------------------
# Contrôles génériques (toutes tables)
# ---------------------------------------------------------------------------
def check_missing_values(
    df: pd.DataFrame,
    table: str,
    required_columns: Sequence[str] | None = None,
    expected_sparse: Sequence[str] | None = None,
) -> CheckResult:
    """Taux de valeurs manquantes, avec une sévérité qui distingue les cas.

    Un taux élevé n'est pas un défaut en soi :

    * une colonne **entièrement vide** est un fait structurel (ex. la date de fin
      de validité d'une dimension SCD2 dont toutes les lignes sont courantes) ;
    * une clé étrangère **optionnelle** (ex. la promotion appliquée à une vente)
      est vide par construction sur la majorité des lignes.

    Seules les colonnes déclarées ``required_columns`` — celles sans lesquelles
    la modélisation est impossible — déclenchent un statut critique.
    """
    if df.empty:
        return CheckResult(f"valeurs_manquantes[{table}]", "critique", "Table vide.")
    required = set(required_columns or [])
    sparse_ok = set(expected_sparse or [])

    na_rate = df.isna().mean().sort_values(ascending=False)
    detail = pd.DataFrame(
        {
            "colonne": na_rate.index,
            "taux_na": na_rate.to_numpy(),
            "n_na": df.isna().sum().reindex(na_rate.index).to_numpy(),
        }
    )
    detail["interpretation"] = [
        "colonne obligatoire"
        if c in required
        else "vide attendu (clé optionnelle)"
        if c in sparse_ok
        else "colonne entièrement vide (structurel)"
        if r >= 1.0
        else "—"
        for c, r in zip(detail["colonne"], detail["taux_na"])
    ]

    with_na = detail[detail["taux_na"] > 0]
    breached = with_na[with_na["colonne"].isin(required)]
    fully_empty = with_na[(with_na["taux_na"] >= 1.0) & (~with_na["colonne"].isin(sparse_ok))]

    if with_na.empty:
        status, summary = "ok", "Aucune valeur manquante."
    elif not breached.empty:
        status = "critique"
        summary = (
            f"{len(breached)} colonne(s) OBLIGATOIRE(s) incomplète(s) : "
            + ", ".join(f"{r.colonne} ({r.taux_na:.1%})" for r in breached.itertuples())
        )
    elif not fully_empty.empty:
        status = "alerte"
        summary = (
            f"{len(fully_empty)} colonne(s) entièrement vide(s) — "
            f"{', '.join(fully_empty['colonne'])} — sans impact sur la cible, "
            "mais inutilisable(s) comme variable."
        )
    else:
        top = with_na.iloc[0]
        status = "ok" if top["colonne"] in sparse_ok else "alerte"
        summary = (
            f"{len(with_na)} colonne(s) avec des manquants ; pire cas "
            f"{top['colonne']} = {top['taux_na']:.1%} ({top['interpretation']})."
        )
    return CheckResult(
        f"valeurs_manquantes[{table}]",
        status,
        summary,
        {
            "n_colonnes_avec_na": int(len(with_na)),
            "colonnes_obligatoires_incompletes": list(breached["colonne"]),
            "colonnes_entierement_vides": list(fully_empty["colonne"]),
        },
        detail,
    )


def check_duplicates(
    df: pd.DataFrame, table: str, key_columns: Sequence[str] | None = None
) -> CheckResult:
    if df.empty:
        return CheckResult(f"doublons[{table}]", "non_applicable", "Table vide.")
    n_full = int(df.duplicated().sum())
    details: dict[str, Any] = {"doublons_ligne_entiere": n_full, "n_lignes": int(len(df))}
    status = "ok" if n_full == 0 else "alerte"
    summary = f"{n_full} doublon(s) sur la ligne entière."

    if key_columns:
        usable = [c for c in key_columns if c in df.columns]
        if usable:
            n_key = int(df.duplicated(subset=usable).sum())
            details["cle_testee"] = usable
            details["doublons_sur_cle"] = n_key
            if n_key > 0:
                status = "critique"
                summary += f" {n_key} doublon(s) sur la clé {usable}."
            else:
                summary += f" Clé {usable} unique."
    return CheckResult(f"doublons[{table}]", status, summary, details)


# ---------------------------------------------------------------------------
# Contrôles sur la table de faits ventes
# ---------------------------------------------------------------------------
def check_date_coverage(df: pd.DataFrame, date_col: str) -> CheckResult:
    if date_col not in df.columns:
        return CheckResult("couverture_temporelle", "non_applicable", "Colonne date absente.")
    dates = pd.to_datetime(df[date_col], errors="coerce")
    valid = dates.dropna()
    if valid.empty:
        return CheckResult("couverture_temporelle", "critique", "Aucune date exploitable.")
    dmin, dmax = valid.min(), valid.max()
    span_days = (dmax - dmin).days + 1
    distinct = valid.dt.normalize().nunique()
    coverage = distinct / span_days if span_days else 0.0
    # Détection de la fréquence dominante des dates distinctes
    unique_days = pd.Series(sorted(valid.dt.normalize().unique()))
    gaps = unique_days.diff().dt.days.dropna()
    modal_gap = int(gaps.mode().iloc[0]) if not gaps.empty else 0
    status = "ok" if coverage > 0.9 else ("alerte" if coverage > 0.5 else "critique")
    return CheckResult(
        "couverture_temporelle",
        status,
        f"Historique du {dmin.date()} au {dmax.date()} ({span_days} j), "
        f"{distinct} jours distincts avec ventes ({coverage:.1%} de couverture), "
        f"écart modal entre jours = {modal_gap} j.",
        {
            "date_min": dmin,
            "date_max": dmax,
            "span_days": span_days,
            "jours_distincts": int(distinct),
            "taux_couverture_jours": float(coverage),
            "ecart_modal_jours": modal_gap,
            "n_dates_invalides": int(dates.isna().sum()),
        },
    )


def check_calendar_gaps(df: pd.DataFrame, date_col: str, min_gap: int = 2) -> CheckResult:
    """Trous dans le calendrier global des ventes (jours consécutifs sans aucune vente)."""
    if date_col not in df.columns:
        return CheckResult("ruptures_calendrier", "non_applicable", "Colonne date absente.")
    days = pd.to_datetime(df[date_col], errors="coerce").dt.normalize().dropna().unique()
    if len(days) < 2:
        return CheckResult("ruptures_calendrier", "non_applicable", "Trop peu de dates.")
    series = pd.Series(sorted(days))
    gaps = series.diff().dt.days
    holes = pd.DataFrame(
        {
            "debut_trou": series.shift(1)[gaps > min_gap],
            "fin_trou": series[gaps > min_gap],
            "jours_sans_vente": gaps[gaps > min_gap] - 1,
        }
    ).dropna()
    if holes.empty:
        return CheckResult(
            "ruptures_calendrier", "ok", "Aucune rupture de plus d'un jour dans le calendrier global."
        )
    return CheckResult(
        "ruptures_calendrier",
        "alerte",
        f"{len(holes)} rupture(s) de calendrier ; la plus longue = "
        f"{int(holes['jours_sans_vente'].max())} jours consécutifs sans aucune vente.",
        {"n_ruptures": int(len(holes)), "max_jours": int(holes["jours_sans_vente"].max())},
        holes.sort_values("jours_sans_vente", ascending=False).head(20),
    )


def check_negative_and_zero(df: pd.DataFrame, columns: dict[str, str]) -> CheckResult:
    """Valeurs négatives / nulles sur quantité, montant, prix, remise."""
    rows = []
    for role, col in columns.items():
        if not col or col not in df.columns:
            continue
        series = pd.to_numeric(df[col], errors="coerce")
        rows.append(
            {
                "role": role,
                "colonne": col,
                "n_negatifs": int((series < 0).sum()),
                "n_zeros": int((series == 0).sum()),
                "n_non_numerique": int(series.isna().sum() - df[col].isna().sum()),
                "min": float(series.min()) if series.notna().any() else None,
                "max": float(series.max()) if series.notna().any() else None,
                "moyenne": float(series.mean()) if series.notna().any() else None,
            }
        )
    if not rows:
        return CheckResult("valeurs_negatives", "non_applicable", "Aucune colonne numérique identifiée.")
    detail = pd.DataFrame(rows)
    total_neg = int(detail["n_negatifs"].sum())
    status = "ok" if total_neg == 0 else "alerte"
    return CheckResult(
        "valeurs_negatives",
        status,
        f"{total_neg} valeur(s) négative(s) au total sur les colonnes numériques clés."
        + (" Les quantités/montants négatifs signalent probablement des retours."
           if total_neg else ""),
        {"total_negatifs": total_neg},
        detail,
    )


def check_returns_and_cancellations(
    df: pd.DataFrame,
    status_col: str | None,
    return_col: str | None,
    quantity_col: str | None,
) -> CheckResult:
    details: dict[str, Any] = {}
    tables: list[pd.DataFrame] = []
    messages: list[str] = []

    if status_col and status_col in df.columns:
        counts = df[status_col].astype("string").value_counts(dropna=False)
        share = (counts / len(df)).rename("part")
        table = pd.concat([counts.rename("n"), share], axis=1).reset_index(names="valeur")
        tables.append(table.assign(colonne=status_col))
        details["modalites_statut"] = counts.to_dict()
        messages.append(
            f"Colonne de statut `{status_col}` : {len(counts)} modalité(s) -> "
            + ", ".join(f"{k} ({v})" for k, v in counts.head(8).items())
        )

    if return_col and return_col in df.columns:
        counts = df[return_col].astype("string").value_counts(dropna=False)
        details["modalites_retour"] = counts.to_dict()
        messages.append(
            f"Colonne de retour `{return_col}` : " + ", ".join(f"{k} ({v})" for k, v in counts.head(8).items())
        )

    if quantity_col and quantity_col in df.columns:
        qty = pd.to_numeric(df[quantity_col], errors="coerce")
        n_neg = int((qty < 0).sum())
        details["lignes_quantite_negative"] = n_neg
        if n_neg:
            messages.append(
                f"{n_neg} ligne(s) à quantité négative — candidat naturel pour des retours."
            )

    if not messages:
        return CheckResult(
            "retours_annulations",
            "non_applicable",
            "Aucune colonne de statut/retour identifiée : impossible de distinguer "
            "ventes valides, annulations et retours sans information métier complémentaire.",
        )
    combined = pd.concat(tables, ignore_index=True) if tables else None
    return CheckResult("retours_annulations", "ok", " | ".join(messages), details, combined)


def check_amount_consistency(
    df: pd.DataFrame,
    quantity_col: str | None,
    price_col: str | None,
    amount_col: str | None,
    discount_col: str | None = None,
    tolerance: float = 0.01,
) -> CheckResult:
    """Vérifie quantité x prix (- remise) ≈ montant."""
    if not (quantity_col and price_col and amount_col):
        return CheckResult(
            "coherence_montants",
            "non_applicable",
            "Colonnes quantité / prix / montant non toutes identifiées.",
        )
    missing = [c for c in (quantity_col, price_col, amount_col) if c not in df.columns]
    if missing:
        return CheckResult("coherence_montants", "non_applicable", f"Colonnes absentes : {missing}")

    qty = pd.to_numeric(df[quantity_col], errors="coerce")
    price = pd.to_numeric(df[price_col], errors="coerce")
    amount = pd.to_numeric(df[amount_col], errors="coerce")
    brut = qty * price

    scenarios: dict[str, pd.Series] = {"quantite x prix": brut}
    if discount_col and discount_col in df.columns:
        disc = pd.to_numeric(df[discount_col], errors="coerce").fillna(0)
        # La remise peut être un taux (0-1), un pourcentage (0-100) ou un montant.
        scenarios["quantite x prix x (1 - remise)"] = brut * (1 - disc)
        scenarios["quantite x prix x (1 - remise/100)"] = brut * (1 - disc / 100)
        scenarios["quantite x prix - remise"] = brut - disc

    # Une tolérance unique donne un verdict trompeur : un jeu de données peut
    # contenir un bruit multiplicatif faible mais systématique (arrondis,
    # variation de prix autour du prix catalogue). On mesure donc la
    # concordance à plusieurs tolérances et on décrit la distribution du ratio.
    tolerances = sorted({0.005, 0.01, 0.02, 0.05, 0.10, tolerance})
    rows = []
    best_name, best_ratio, best_score = None, None, -1.0
    for name, expected in scenarios.items():
        denom = amount.abs().replace(0, np.nan)
        rel_err = (expected - amount).abs() / denom
        entry: dict[str, Any] = {"formule": name}
        for tol in tolerances:
            entry[f"≤{tol:.1%}"] = float((rel_err <= tol).mean())
        entry["err_rel_mediane"] = float(rel_err.median()) if rel_err.notna().any() else None
        rows.append(entry)
        score = float((rel_err <= 0.05).mean())
        if score > best_score:
            best_name, best_score = name, score
            best_ratio = (amount / expected.replace(0, np.nan)).dropna()

    detail = pd.DataFrame(rows).sort_values("err_rel_mediane")
    status = "ok" if best_score > 0.95 else ("alerte" if best_score > 0.5 else "critique")

    details: dict[str, Any] = {
        "meilleure_formule": best_name,
        "taux_concordance_5pct": best_score,
    }
    summary = (
        f"Meilleure formule : « {best_name} » — {best_score:.1%} des lignes "
        f"concordent à ±5 %."
    )
    if best_ratio is not None and len(best_ratio):
        q = best_ratio.quantile([0.001, 0.5, 0.999])
        details["ratio_reel_sur_attendu"] = {
            "p0.1": float(q.loc[0.001]),
            "mediane": float(q.loc[0.5]),
            "p99.9": float(q.loc[0.999]),
        }
        spread = float(q.loc[0.999] - q.loc[0.001])
        if best_score > 0.95 and spread < 0.15:
            summary += (
                f" Le ratio réel/attendu s'étale de {q.loc[0.001]:.4f} à "
                f"{q.loc[0.999]:.4f} autour d'une médiane de {q.loc[0.5]:.4f} : "
                "l'écart résiduel est un bruit multiplicatif borné, pas une "
                "incohérence de définition."
            )
    return CheckResult("coherence_montants", status, summary, details, detail)


def check_referential_integrity(
    fact: pd.DataFrame, fact_key: str | None, dim: pd.DataFrame, dim_key: str | None, label: str
) -> CheckResult:
    if not fact_key or not dim_key or fact_key not in fact.columns or dim_key not in dim.columns:
        return CheckResult(f"integrite[{label}]", "non_applicable", "Clés non identifiées.")
    fact_values = fact[fact_key].dropna().unique()
    dim_values = set(dim[dim_key].dropna().unique())
    orphans = [v for v in fact_values if v not in dim_values]
    rate = len(orphans) / max(len(fact_values), 1)
    status = "ok" if not orphans else ("alerte" if rate < 0.05 else "critique")
    return CheckResult(
        f"integrite[{label}]",
        status,
        f"{len(orphans)} clé(s) de fait sur {len(fact_values)} sans correspondance "
        f"dans la dimension ({rate:.2%}).",
        {
            "n_cles_faits": int(len(fact_values)),
            "n_orphelines": int(len(orphans)),
            "exemples": [str(v) for v in orphans[:10]],
            "n_cles_dimension": int(len(dim_values)),
        },
    )


# ---------------------------------------------------------------------------
# Contrôles au niveau série (produit x temps)
# ---------------------------------------------------------------------------
def series_profile(
    daily: pd.DataFrame,
    id_col: str = "unique_id",
    date_col: str = "ds",
    value_col: str = "y",
) -> pd.DataFrame:
    """Profil par série : longueur, densité, intermittence (ADI, CV²), activité."""
    if daily.empty:
        return pd.DataFrame()

    d = daily.copy()
    d[date_col] = pd.to_datetime(d[date_col])
    global_max = d[date_col].max()

    grouped = d.groupby(id_col)[date_col]
    profile = pd.DataFrame(
        {
            "premiere_vente": grouped.min(),
            "derniere_vente": grouped.max(),
            "n_jours_avec_vente": grouped.nunique(),
        }
    )
    profile["span_jours"] = (
        profile["derniere_vente"] - profile["premiere_vente"]
    ).dt.days + 1
    profile["jours_depuis_derniere_vente"] = (global_max - profile["derniere_vente"]).dt.days

    stats = d.groupby(id_col)[value_col].agg(
        total="sum", moyenne="mean", ecart_type="std", maximum="max", minimum="min"
    )
    profile = profile.join(stats)

    # Part de jours sans vente à l'intérieur de la fenêtre d'activité du produit
    profile["taux_jours_sans_vente"] = 1 - (
        profile["n_jours_avec_vente"] / profile["span_jours"].clip(lower=1)
    )

    # ADI : intervalle moyen entre deux demandes ; CV² sur les demandes non nulles
    nonzero = d[d[value_col] > 0]
    demand_stats = nonzero.groupby(id_col)[value_col].agg(
        n_demandes="count", moyenne_demande="mean", ecart_demande="std"
    )
    profile = profile.join(demand_stats)
    profile["adi"] = profile["span_jours"] / profile["n_demandes"].replace(0, np.nan)
    profile["cv2"] = (
        profile["ecart_demande"] / profile["moyenne_demande"].replace(0, np.nan)
    ) ** 2
    return profile.reset_index()


def classify_series(
    profile: pd.DataFrame,
    adi_threshold: float = 1.32,
    cv2_threshold: float = 0.49,
    min_history_days: int = 90,
    min_nonzero_points: int = 12,
    inactive_days: int = 60,
) -> pd.DataFrame:
    """Classification Syntetos-Boylan-Croston + statut de cycle de vie."""
    if profile.empty:
        return profile

    p = profile.copy()

    def _sbc(row: pd.Series) -> str:
        adi, cv2 = row.get("adi"), row.get("cv2")
        if pd.isna(adi) or pd.isna(cv2):
            return "indetermine"
        if adi < adi_threshold and cv2 < cv2_threshold:
            return "regulier"
        if adi >= adi_threshold and cv2 < cv2_threshold:
            return "intermittent"
        if adi < adi_threshold and cv2 >= cv2_threshold:
            return "erratique"
        return "grumeleux"

    p["profil_demande"] = p.apply(_sbc, axis=1)

    def _lifecycle(row: pd.Series) -> str:
        if row["span_jours"] < min_history_days:
            return "nouveau_ou_trop_court"
        if row.get("n_demandes", 0) < min_nonzero_points:
            return "historique_insuffisant"
        if row["jours_depuis_derniere_vente"] > inactive_days:
            return "inactif_ou_abandonne"
        return "actif"

    p["statut_cycle_vie"] = p.apply(_lifecycle, axis=1)
    p["modelisable_ml"] = (p["statut_cycle_vie"] == "actif") & (
        p["profil_demande"].isin(["regulier", "erratique", "grumeleux", "intermittent"])
    )
    return p


def check_atypical_periods(
    daily_total: pd.DataFrame, date_col: str = "ds", value_col: str = "y", z_threshold: float = 3.0
) -> CheckResult:
    """Jours atypiques sur le total agrégé (score z robuste, base MAD)."""
    if daily_total.empty or len(daily_total) < 30:
        return CheckResult("periodes_atypiques", "non_applicable", "Historique trop court.")
    s = daily_total.set_index(date_col)[value_col].sort_index()
    median = s.median()
    mad = (s - median).abs().median()
    if mad == 0:
        return CheckResult("periodes_atypiques", "non_applicable", "Dispersion nulle (MAD=0).")
    z = 0.6745 * (s - median) / mad
    outliers = s[z.abs() > z_threshold]
    detail = pd.DataFrame(
        {"date": outliers.index, "total": outliers.to_numpy(), "z_robuste": z[z.abs() > z_threshold].to_numpy()}
    ).sort_values("z_robuste", key=lambda c: c.abs(), ascending=False)
    # Un seuil à 3 écarts robustes désigne mécaniquement quelques points sur un
    # historique long : on n'alerte que si leur part dépasse 1 %.
    share = len(outliers) / len(s)
    status = "ok" if share <= 0.01 else ("alerte" if share <= 0.05 else "critique")
    return CheckResult(
        "periodes_atypiques",
        status,
        f"{len(outliers)} jour(s) atypique(s) sur {len(s)} (|z robuste| > {z_threshold}), "
        f"soit {len(outliers)/len(s):.1%} de l'historique.",
        {"n_atypiques": int(len(outliers)), "n_jours": int(len(s))},
        detail.head(30),
    )


def check_launch_dates(
    sales: pd.DataFrame,
    date_col: str,
    product_col: str,
    launch_dates: pd.Series,
) -> CheckResult:
    """Vérifie qu'aucune vente n'est antérieure à la date de mise en vente.

    Enjeu direct pour la cible : si aucune vente ne précède la date déclarée,
    celle-ci est une **vraie date de lancement** et peut servir à la fois de
    borne de remplissage des zéros et de variable « âge du produit ».
    Dans le cas contraire, c'est une date technique et il faut lui préférer la
    date de première vente observée.
    """
    if launch_dates is None or launch_dates.empty:
        return CheckResult("dates_lancement", "non_applicable", "Aucune date de lancement disponible.")
    df = sales[[product_col, date_col]].dropna()
    if df.empty:
        return CheckResult("dates_lancement", "non_applicable", "Aucune vente exploitable.")
    launch = df[product_col].map(launch_dates)
    known = launch.notna()
    if not known.any():
        return CheckResult(
            "dates_lancement", "non_applicable", "Aucune correspondance produit -> date de lancement."
        )
    before = (df.loc[known, date_col] < launch[known]).sum()
    rate = float(before / known.sum())
    first_sale = df.groupby(product_col)[date_col].min()
    delay = (first_sale - first_sale.index.map(launch_dates)).dt.days.dropna()
    if before == 0:
        status = "ok"
        summary = (
            "Aucune vente antérieure à la date de mise en vente déclarée : la colonne "
            "est une véritable date de lancement, exploitable comme borne de début "
            "de série et comme variable d'âge produit. "
            f"Délai médian entre lancement et première vente : {delay.median():.0f} jour(s)."
        )
    else:
        status = "critique" if rate > 0.01 else "alerte"
        summary = (
            f"{int(before)} vente(s) ({rate:.2%}) antérieures à la date déclarée : "
            "il s'agit d'une date technique, pas d'une date de lancement. "
            "Utiliser la date de première vente observée."
        )
    return CheckResult(
        "dates_lancement",
        status,
        summary,
        {
            "n_ventes_avant_lancement": int(before),
            "taux": rate,
            "delai_median_jours": float(delay.median()) if len(delay) else None,
            "delai_max_jours": float(delay.max()) if len(delay) else None,
        },
    )


def check_promotion_windows(
    sales: pd.DataFrame,
    date_col: str,
    promo_key_col: str,
    start_col: str,
    end_col: str,
) -> CheckResult:
    """Vérifie que les ventes marquées en promotion tombent bien dans la fenêtre.

    Si la cohérence est totale, la dimension promotion peut servir à
    **reconstruire un calendrier promotionnel futur** — une variable exogène
    connue à l'avance, donc utilisable en prévision sans fuite.
    """
    needed = [promo_key_col, start_col, end_col, date_col]
    if any(c not in sales.columns for c in needed):
        return CheckResult("fenetres_promotions", "non_applicable", "Colonnes de promotion incomplètes.")
    promo = sales[sales[promo_key_col].notna()]
    if promo.empty:
        return CheckResult("fenetres_promotions", "non_applicable", "Aucune vente rattachée à une promotion.")
    start = pd.to_datetime(promo[start_col], errors="coerce")
    end = pd.to_datetime(promo[end_col], errors="coerce")
    day = pd.to_datetime(promo[date_col], errors="coerce")
    inside = ((day >= start) & (day <= end))
    rate = float(inside.mean())
    status = "ok" if rate > 0.99 else ("alerte" if rate > 0.9 else "critique")
    summary = (
        f"{rate:.2%} des ventes promues tombent dans la fenêtre déclarée "
        f"({int(inside.sum())} / {len(promo)})."
    )
    if rate > 0.99:
        summary += (
            " La dimension promotion est donc fiable pour reconstruire un calendrier "
            "promotionnel produit×jour, y compris sur l'horizon futur."
        )
    return CheckResult(
        "fenetres_promotions",
        status,
        summary,
        {"taux_dans_fenetre": rate, "n_ventes_promues": int(len(promo))},
    )


def check_promotion_coverage(
    sales: pd.DataFrame, promo_flag_col: str, date_col: str, product_col: str
) -> CheckResult:
    if promo_flag_col not in sales.columns:
        return CheckResult("couverture_promotions", "non_applicable", "Indicateur de promotion absent.")
    flag = sales[promo_flag_col].fillna(0).astype(float) > 0
    share_lines = float(flag.mean())
    by_day = sales.assign(_f=flag).groupby(date_col)["_f"].max()
    share_days = float(by_day.mean()) if len(by_day) else 0.0
    by_product = sales.assign(_f=flag).groupby(product_col)["_f"].max()
    share_products = float(by_product.mean()) if len(by_product) else 0.0
    status = "ok" if share_lines > 0.01 else "alerte"
    return CheckResult(
        "couverture_promotions",
        status,
        f"{share_lines:.1%} des lignes de vente sont en promotion ; "
        f"{share_days:.1%} des jours et {share_products:.1%} des produits sont concernés "
        f"au moins une fois.",
        {
            "part_lignes_promo": share_lines,
            "part_jours_avec_promo": share_days,
            "part_produits_promus": share_products,
        },
    )
