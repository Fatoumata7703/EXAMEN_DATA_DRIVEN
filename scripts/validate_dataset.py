"""Validation exhaustive de la table analytique — 14 contrôles, chiffres réels.

    python scripts/validate_dataset.py            # rapport console + Markdown
    python scripts/validate_dataset.py --json     # sortie machine

Ce script ne modifie rien : il compare la table analytique construite
(`data/processed/table_analytique.parquet`) aux tables sources en cache
(`data/raw/*.parquet`) et signale toute divergence.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config.settings import PROJECT_ROOT  # noqa: E402
from src.data.build_dataset import parse_date_key  # noqa: E402

OUT = io.StringIO()


def say(text: str = "") -> None:
    print(text)
    OUT.write(text + "\n")


def load() -> dict[str, pd.DataFrame]:
    raw = PROJECT_ROOT / "data" / "raw"
    return {
        "ventes": pd.read_parquet(raw / "fact_ventes.parquet"),
        "produits": pd.read_parquet(raw / "dim_produit.parquet"),
        "promotions": pd.read_parquet(raw / "dim_promotion.parquet"),
        "dates": pd.read_parquet(raw / "dim_date.parquet"),
        "web": pd.read_parquet(raw / "fact_evenements_web.parquet"),
        "table": pd.read_parquet(PROJECT_ROOT / "data" / "processed" / "table_analytique.parquet"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    d = load()
    v, p, promo, dim_date, web, t = (
        d["ventes"], d["produits"], d["promotions"], d["dates"], d["web"], d["table"]
    )
    # Les clés viennent de sources différentes (Parquet REST vs table construite)
    # et peuvent porter des dtypes distincts (`object` vs `string`). On les
    # ramène toutes à `str` pour que les alignements d'index soient fiables.
    v = v.copy()
    v["ds"] = parse_date_key(v["date_key"])
    v["produit_key"] = v["produit_key"].astype(str)
    t = t.copy()
    t["ds"] = pd.to_datetime(t["ds"])
    t["unique_id"] = t["unique_id"].astype(str)
    p = p.copy()
    p["produit_key"] = p["produit_key"].astype(str)
    p["valid_from"] = pd.to_datetime(p["valid_from"]).dt.normalize()
    web = web.copy()
    web["produit_key"] = web["produit_key"].astype(str)

    results: dict[str, Any] = {}
    failures: list[str] = []

    # ------------------------------------------------------------------ 1
    say("=" * 78)
    say("1. ORIGINE DES ZEROS")
    say("=" * 78)
    n_qte_zero = int((v["quantite"] == 0).sum())
    n_qte_neg = int((v["quantite"] < 0).sum())
    n_qte_na = int(v["quantite"].isna().sum())
    n_obs = int((t["n_transactions"] > 0).sum())
    n_zero_rows = int((t["y"] == 0).sum())
    n_rows = len(t)
    # Zéros créés = lignes de la grille sans transaction source
    n_zero_created = int(((t["n_transactions"] == 0) & (t["y"] == 0)).sum())
    n_zero_from_source = int(((t["n_transactions"] > 0) & (t["y"] == 0)).sum())

    say(f"  lignes fact_ventes                          : {len(v):,}")
    say(f"  lignes avec quantite = 0                    : {n_qte_zero:,}")
    say(f"  lignes avec quantite < 0                    : {n_qte_neg:,}")
    say(f"  lignes avec quantite manquante              : {n_qte_na:,}")
    say(f"  quantite min / max                          : {v.quantite.min()} / {v.quantite.max()}")
    say("")
    say(f"  lignes table analytique                     : {n_rows:,}")
    say(f"  dont issues d'au moins une transaction      : {n_obs:,}")
    say(f"  dont creees ex nihilo (zeros de completion) : {n_zero_created:,}")
    say(f"  lignes y=0 AVEC transaction source          : {n_zero_from_source:,}  <- doit etre 0")
    say(f"  total lignes y=0                            : {n_zero_rows:,}")
    say("")
    say(f"  FORMULE : taux_zeros = n_zeros / n_lignes = {n_zero_rows:,} / {n_rows:,} = {n_zero_rows/n_rows:.4%}")
    say(f"  Tous les y=0 proviennent de la completion : {n_zero_created:,} == {n_zero_rows:,} -> "
        f"{'OUI' if n_zero_created == n_zero_rows else 'NON'}")
    if n_zero_from_source:
        failures.append("Des lignes y=0 portent pourtant des transactions sources.")
    if n_qte_zero or n_qte_neg:
        failures.append("fact_ventes contient des quantites nulles ou negatives (hypothese a revoir).")
    results["1_zeros"] = {
        "source_quantite_zero": n_qte_zero,
        "source_quantite_negative": n_qte_neg,
        "zeros_crees": n_zero_created,
        "zeros_avec_transaction": n_zero_from_source,
        "taux_zeros": n_zero_rows / n_rows,
    }

    # ------------------------------------------------------------------ 2
    say("")
    say("=" * 78)
    say("2. CONSERVATION DES VENTES")
    say("=" * 78)
    total_src = float(v["quantite"].sum())
    total_tab = float(t["y"].sum())
    say(f"  SUM(fact_ventes.quantite)      = {total_src:,.0f}")
    say(f"  SUM(table_analytique.y)        = {total_tab:,.0f}")
    say(f"  difference                     = {total_tab - total_src:,.0f}")

    by_prod_src = v.groupby("produit_key")["quantite"].sum()
    by_prod_tab = t.groupby("unique_id")["y"].sum()
    cmp_prod = pd.concat(
        [by_prod_src.rename("source"), by_prod_tab.rename("table")], axis=1
    ).fillna(0)
    cmp_prod["ecart"] = cmp_prod["table"] - cmp_prod["source"]
    n_prod_diff = int((cmp_prod["ecart"] != 0).sum())

    v["mois"] = v["ds"].dt.to_period("M")
    t["mois"] = t["ds"].dt.to_period("M")
    by_month_src = v.groupby("mois")["quantite"].sum()
    by_month_tab = t.groupby("mois")["y"].sum()
    cmp_month = pd.concat(
        [by_month_src.rename("source"), by_month_tab.rename("table")], axis=1
    ).fillna(0)
    cmp_month["ecart"] = cmp_month["table"] - cmp_month["source"]
    n_month_diff = int((cmp_month["ecart"] != 0).sum())

    say(f"  produits avec ecart non nul    : {n_prod_diff} / {len(cmp_prod)}")
    say(f"  mois avec ecart non nul        : {n_month_diff} / {len(cmp_month)}")
    if n_prod_diff:
        say("  --- produits en ecart ---")
        say(cmp_prod[cmp_prod["ecart"] != 0].head(20).to_string())
    if n_month_diff:
        say("  --- mois en ecart ---")
        say(cmp_month[cmp_month["ecart"] != 0].to_string())
    if abs(total_tab - total_src) > 1e-6 or n_prod_diff or n_month_diff:
        failures.append("Perte ou creation de quantite lors de l'agregation.")
    results["2_conservation"] = {
        "somme_source": total_src,
        "somme_table": total_tab,
        "difference": total_tab - total_src,
        "produits_en_ecart": n_prod_diff,
        "mois_en_ecart": n_month_diff,
    }

    # ------------------------------------------------------------------ 3
    say("")
    say("=" * 78)
    say("3. UNICITE DE LA TABLE")
    say("=" * 78)
    n_pairs = int(t.groupby(["unique_id", "ds"]).ngroups)
    n_dup = int(t.duplicated(subset=["unique_id", "ds"]).sum())
    say(f"  lignes totales                 : {len(t):,}")
    say(f"  couples (produit, date) distincts : {n_pairs:,}")
    say(f"  doublons produit-date          : {n_dup}")
    say(f"  produits                       : {t.unique_id.nunique()}")
    say(f"  date min / max                 : {t.ds.min().date()} / {t.ds.max().date()}")
    if n_dup:
        failures.append("Doublons produit-date dans la table analytique.")
    results["3_unicite"] = {
        "n_lignes": len(t),
        "n_couples": n_pairs,
        "n_doublons": n_dup,
        "n_produits": int(t.unique_id.nunique()),
    }

    # ------------------------------------------------------------------ 4
    say("")
    say("=" * 78)
    say("4. PERIODE D'ACTIVITE")
    say("=" * 78)
    launch = p.set_index("produit_key")["valid_from"]
    first_sale_all = v.groupby("produit_key")["ds"].min()
    t_launch = t["unique_id"].map(launch)
    n_before_launch = int((t["ds"] < t_launch).sum())
    v_launch = v["produit_key"].map(launch)
    n_sales_before_launch = int((v["ds"] < v_launch).sum())
    n_launch_missing = int(launch.isna().sum())

    first_row = t.groupby("unique_id")["ds"].min()
    last_sale = v.groupby("produit_key")["ds"].max()
    last_row = t.groupby("unique_id")["ds"].max()
    tail_zeros = (last_row - last_sale).dt.days.dropna()

    say(f"  lignes anterieures a valid_from             : {n_before_launch}  <- doit etre 0")
    say(f"  ventes anterieures a valid_from             : {n_sales_before_launch}  <- doit etre 0")
    say(f"  produits sans valid_from                    : {n_launch_missing}")
    say(f"  ecart median premiere ligne - valid_from    : "
        f"{(first_row - first_row.index.map(launch)).dt.days.median():.0f} j")
    say("")
    say("  Queue de zeros apres la derniere vente (jours) :")
    say(f"    min {tail_zeros.min():.0f} | median {tail_zeros.median():.0f} | "
        f"p95 {tail_zeros.quantile(.95):.0f} | max {tail_zeros.max():.0f}")
    for seuil in (30, 60, 90):
        say(f"    produits avec queue de zeros > {seuil} j : {int((tail_zeros > seuil).sum())}")
    if n_before_launch or n_sales_before_launch:
        failures.append("Des lignes ou des ventes precedent la date de lancement.")
    results["4_activite"] = {
        "lignes_avant_valid_from": n_before_launch,
        "ventes_avant_valid_from": n_sales_before_launch,
        "produits_sans_valid_from": n_launch_missing,
        "queue_zeros_max": float(tail_zeros.max()),
    }

    # ------------------------------------------------------------------ 6
    say("")
    say("=" * 78)
    say("6. JOURS MANQUANTS DANS LA DIMENSION DATE")
    say("=" * 78)
    dd = pd.to_datetime(dim_date["date_complete"]).dt.normalize().sort_values()
    expected = pd.date_range(dd.min(), dd.max(), freq="D")
    missing = sorted(set(expected) - set(dd))
    gaps = dd.diff().dt.days.dropna()
    say(f"  date min / max                 : {dd.min().date()} / {dd.max().date()}")
    say(f"  jours calendaires attendus     : {len(expected)}")
    say(f"  jours presents dans dim_date   : {len(dd)}")
    say(f"  dates manquantes               : {len(missing)}")
    if missing:
        say(f"    {[str(m.date()) for m in missing[:20]]}")
    say(f"  ecarts entre jours consecutifs : min {gaps.min():.0f}, max {gaps.max():.0f} "
        f"-> {'consecutifs' if gaps.max() == 1 else 'NON consecutifs'}")
    # Les 546 jours sont-ils calendaires ou seulement les jours avec transaction ?
    days_with_sales = v["ds"].dt.normalize().nunique()
    say(f"  jours distincts AVEC transaction: {days_with_sales}")
    say(f"  -> dim_date couvre {len(dd)} jours calendaires consecutifs ; "
        f"{days_with_sales} d'entre eux portent au moins une vente")
    if missing:
        failures.append("Trous de calendrier dans dim_date.")
    results["6_calendrier"] = {
        "jours_attendus": len(expected),
        "jours_presents": len(dd),
        "dates_manquantes": [str(m.date()) for m in missing],
        "jours_avec_vente": int(days_with_sales),
    }

    # ------------------------------------------------------------------ 8
    say("")
    say("=" * 78)
    say("8. PROMOTIONS")
    say("=" * 78)
    cross = pd.crosstab(t["en_promotion"], t["y"] > 0)
    cross.index = ["sans promotion", "promotion active"]
    cross.columns = ["y = 0", "y > 0"]
    say(cross.to_string())
    say("")
    say(f"  produit-jours promo active & y=0 : {int(cross.loc['promotion active','y = 0']):,}")
    say(f"  produit-jours promo active & y>0 : {int(cross.loc['promotion active','y > 0']):,}")
    say(f"  produit-jours sans promo & y=0   : {int(cross.loc['sans promotion','y = 0']):,}")
    say(f"  produit-jours sans promo & y>0   : {int(cross.loc['sans promotion','y > 0']):,}")
    # La remise vient-elle bien de dim_promotion ?
    remises_dim = set(promo["remise_pct"].unique())
    remises_tab = set(t.loc[t.en_promotion == 1, "remise_pct"].unique())
    say("")
    say(f"  remises distinctes dans dim_promotion : {sorted(remises_dim)}")
    say(f"  remises distinctes dans la table      : {sorted(remises_tab)}")
    say(f"  toutes issues de dim_promotion        : {'OUI' if remises_tab <= remises_dim else 'NON'}")
    say(f"  remise non nulle hors promotion       : "
        f"{int(((t.en_promotion == 0) & (t.remise_pct != 0)).sum())}  <- doit etre 0")
    if not remises_tab <= remises_dim:
        failures.append("Des taux de remise ne proviennent pas de dim_promotion.")
    results["8_promotions"] = {
        "promo_y0": int(cross.loc["promotion active", "y = 0"]),
        "promo_ypos": int(cross.loc["promotion active", "y > 0"]),
        "sans_promo_y0": int(cross.loc["sans promotion", "y = 0"]),
        "sans_promo_ypos": int(cross.loc["sans promotion", "y > 0"]),
    }

    # ------------------------------------------------------------------ 9
    say("")
    say("=" * 78)
    say("9. PRODUITS LANCES A DES DATES DIFFERENTES (3 exemples reels)")
    say("=" * 78)
    first_sale = first_sale_all
    summary = pd.DataFrame(
        {
            "valid_from": launch,
            "1ere_ligne_table": first_row,
            "1ere_vente": first_sale,
            "derniere_ligne": last_row,
        }
    ).dropna()
    summary["n_lignes"] = t.groupby("unique_id").size()
    picks = summary.sort_values("valid_from")
    examples = pd.concat([picks.head(1), picks.iloc[[len(picks) // 2]], picks.tail(1)])
    say(examples.to_string())
    say("")
    say(f"  ecart max |1ere_ligne - valid_from| : "
        f"{(summary['1ere_ligne_table'] - summary['valid_from']).dt.days.abs().max()} j")
    results["9_exemples"] = json.loads(examples.reset_index().to_json(orient="records", date_format="iso"))

    # ------------------------------------------------------------------ 10
    say("")
    say("=" * 78)
    say("10. HISTORIQUE PAR PRODUIT ET INACTIVITE")
    say("=" * 78)
    hist = t.groupby("unique_id").size()
    say(f"  jours d'historique : min {hist.min()} | mediane {hist.median():.0f} | "
        f"moyenne {hist.mean():.1f} | max {hist.max()}")
    for seuil in (30, 60, 90, 180):
        say(f"    produits avec < {seuil} jours : {int((hist < seuil).sum())}")
    say("")
    dmax = t["ds"].max()
    inactivity = (dmax - last_sale).dt.days
    say(f"  jours depuis la derniere vente : min {inactivity.min()} | "
        f"mediane {inactivity.median():.0f} | max {inactivity.max()}")
    for seuil in (30, 60, 90):
        n = int((inactivity > seuil).sum())
        say(f"    produits sans vente depuis > {seuil} j : {n}")
        if n:
            say(f"      {list(inactivity[inactivity > seuil].index[:10])}")
    results["10_historique"] = {
        "min": int(hist.min()),
        "mediane": float(hist.median()),
        "moyenne": float(hist.mean()),
        "max": int(hist.max()),
        "moins_30j": int((hist < 30).sum()),
        "moins_60j": int((hist < 60).sum()),
        "moins_90j": int((hist < 90).sum()),
        "inactifs_30j": int((inactivity > 30).sum()),
        "inactifs_60j": int((inactivity > 60).sum()),
        "inactifs_90j": int((inactivity > 90).sum()),
    }

    # ------------------------------------------------------------------ 11
    say("")
    say("=" * 78)
    say("11. STRUCTURE DES SEQUENCES DE ZEROS")
    say("=" * 78)
    runs: list[dict[str, Any]] = []
    for pid, chunk in t.sort_values(["unique_id", "ds"]).groupby("unique_id"):
        is_zero = (chunk["y"] == 0).to_numpy()
        if not is_zero.any():
            continue
        # Longueurs des plages consécutives de True
        idx = np.flatnonzero(np.diff(np.concatenate(([0], is_zero.view(np.int8), [0]))) != 0)
        lengths = idx[1::2] - idx[0::2]
        for length in lengths:
            runs.append({"unique_id": pid, "longueur": int(length)})
    runs_df = pd.DataFrame(runs)
    lg = runs_df["longueur"]
    say(f"  nombre de sequences de zeros : {len(lg):,}")
    say(f"  longueur moyenne  : {lg.mean():.2f} jours")
    say(f"  mediane           : {lg.median():.0f}")
    say(f"  90e percentile    : {lg.quantile(.90):.0f}")
    say(f"  maximum           : {lg.max()}")
    for seuil in (7, 14, 30, 60):
        say(f"    sequences > {seuil} j : {int((lg > seuil).sum())}")
    say("")
    say("  Produits aux plus longues sequences :")
    top = runs_df.sort_values("longueur", ascending=False).head(10)
    say(top.to_string(index=False))
    results["11_sequences"] = {
        "n_sequences": int(len(lg)),
        "moyenne": float(lg.mean()),
        "mediane": float(lg.median()),
        "p90": float(lg.quantile(.90)),
        "max": int(lg.max()),
        "sup_7": int((lg > 7).sum()),
        "sup_14": int((lg > 14).sum()),
        "sup_30": int((lg > 30).sum()),
        "sup_60": int((lg > 60).sum()),
    }

    # ------------------------------------------------------------------ 12
    say("")
    say("=" * 78)
    say("12. SENSIBILITE A LA REGLE DE FIN DE FENETRE")
    say("=" * 78)
    global_end = t["ds"].max()
    obs = v.groupby(["produit_key", "ds"])["quantite"].sum()
    n_obs_points = len(obs)
    valid_to_all_null = bool(p["valid_to"].isna().all())

    # Borne gauche commune aux trois scenarios : max(valid_from, debut des
    # donnees), plafonnee par la premiere vente. Sans cet ecretage, on
    # fabriquerait des lignes la ou rien n'a jamais ete observe.
    global_start = v["ds"].min()
    debut = np.minimum(launch.clip(lower=global_start), first_sale_all)

    scenarios = {}
    rows_a = int(((global_end - debut).dt.days + 1).sum())
    scenarios["A"] = (rows_a, 1 - n_obs_points / rows_a)
    rows_b = int(((last_sale.reindex(debut.index) - debut).dt.days + 1).sum())
    scenarios["B"] = (rows_b, 1 - n_obs_points / rows_b)
    end_c = pd.to_datetime(p.set_index("produit_key")["valid_to"]).fillna(global_end)
    rows_c = int(((end_c.reindex(debut.index) - debut).dt.days + 1).sum())
    scenarios["C"] = (rows_c, 1 - n_obs_points / rows_c)

    say(f"  points reellement observes (produit-jour avec vente) : {n_obs_points:,}")
    say(f"  valid_to entierement vide : {valid_to_all_null}")
    say(f"  borne gauche commune : max(valid_from, {global_start.date()}) plafonnee par la 1ere vente")
    say("")
    say(f"  {'scenario':<12} {'lignes':>10} {'taux zeros':>12} {'produits':>10}")
    labels = {
        "A": "-> derniere date globale (ACTUEL, regle validee)",
        "B": "-> derniere vente du produit",
        "C": "-> valid_to (sinon date globale)",
    }
    for key, (rows, zrate) in scenarios.items():
        say(f"  {key:<12} {rows:>10,} {zrate:>11.2%} {len(launch.dropna()):>10}   {labels[key]}")
    results["12_sensibilite"] = {
        k: {"lignes": rows, "taux_zeros": zrate} for k, (rows, zrate) in scenarios.items()
    }

    # ------------------------------------------------------------------ 7 (verif attributs)
    say("")
    say("=" * 78)
    say("7. VERIFICATION DU REMPLISSAGE PAR ZERO")
    say("=" * 78)
    zero_rows = t[t["y"] == 0]
    say(f"  lignes y=0 : {len(zero_rows):,}")
    say("")
    say("  Colonnes et leur etat sur les lignes y=0 :")
    for col, attendu in [
        ("y", "0 (completion)"),
        ("ca", "0"),
        ("n_transactions", "0"),
        ("prix_realise", "NaN (non observable sans vente)"),
        ("prix_catalogue", "valeur dimension (jamais 0)"),
        ("en_promotion", "0 ou 1 selon calendrier"),
        ("remise_pct", "0 hors promo, valeur dim_promotion sinon"),
        ("categorie", "attribut dimension"),
        ("marque", "attribut dimension"),
    ]:
        if col not in zero_rows.columns:
            continue
        s = zero_rows[col]
        n_na = int(s.isna().sum())
        if pd.api.types.is_numeric_dtype(s):
            say(f"    {col:<16} NaN={n_na:>7,}  min={s.min()}  max={s.max()}   [attendu: {attendu}]")
        else:
            say(f"    {col:<16} NaN={n_na:>7,}  modalites={s.nunique()}   [attendu: {attendu}]")
    n_prix_zero = int((zero_rows["prix_catalogue"] == 0).sum()) if "prix_catalogue" in zero_rows else 0
    n_prix_realise_filled = int(zero_rows["prix_realise"].notna().sum())
    say("")
    say(f"  prix_catalogue mis a 0 sur lignes y=0    : {n_prix_zero}  <- doit etre 0")
    say(f"  prix_realise renseigne sur lignes y=0    : {n_prix_realise_filled}  <- doit etre 0")
    if n_prix_zero or n_prix_realise_filled:
        failures.append("Remplissage par zero applique a des attributs qui ne doivent pas l'etre.")

    # ------------------------------------------------------------------ web
    say("")
    say("  Evenements web sur lignes y=0 :")
    web_cols = [c for c in t.columns if c.startswith("web_")]
    if web_cols:
        say(f"    colonnes : {web_cols}")
        say(f"    moyenne web_total sur y=0 : {zero_rows['web_total'].mean():.3f}")
        say(f"    moyenne web_total sur y>0 : {t.loc[t.y > 0, 'web_total'].mean():.3f}")
        w = web.copy()
        w["ds"] = parse_date_key(w["date_key"])
        w_launch = w["produit_key"].map(launch)
        n_web_before = int((w["ds"] < w_launch).sum())
        say(f"    evenements web anterieurs au lancement du produit : {n_web_before:,}")
        if n_web_before:
            say("      -> ces evenements sont hors fenetre d'activite et donc absents de la table")

    # ------------------------------------------------------------------ bilan
    say("")
    say("=" * 78)
    say("BILAN")
    say("=" * 78)
    if failures:
        for f in failures:
            say(f"  [ECHEC] {f}")
    else:
        say("  Tous les controles structurels passent.")
    results["echecs"] = failures

    report_path = PROJECT_ROOT / "reports" / "05_validation_table_analytique.md"
    report_path.write_text(
        "# 05 — Validation de la table analytique\n\n"
        "_Sortie brute de `python scripts/validate_dataset.py`._\n\n```\n"
        + OUT.getvalue()
        + "```\n",
        encoding="utf-8",
    )
    if args.json:
        (PROJECT_ROOT / "reports" / "05_validation.json").write_text(
            json.dumps(results, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
        )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
