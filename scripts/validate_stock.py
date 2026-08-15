"""Validation approfondie de `fact_stock` — nouvelle table livrée le 2026-08-13.

    python scripts/validate_stock.py

Grain, unicité, couverture, trous, valeurs négatives/nulles, cohérence avec
les ventes (ventes positives à stock nul, séquences de rupture), impact sur
le taux de zéros de la cible. Lecture seule, aucune modification.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config.settings import PROJECT_ROOT  # noqa: E402
from src.data.build_dataset import parse_date_key  # noqa: E402

OUT = io.StringIO()


def say(text: str = "") -> None:
    print(text)
    OUT.write(text + "\n")


def main() -> int:
    raw = PROJECT_ROOT / "data" / "raw"
    stock = pd.read_parquet(raw / "fact_stock.parquet")
    v = pd.read_parquet(raw / "fact_ventes.parquet")
    p = pd.read_parquet(raw / "dim_produit.parquet")
    p["valid_from"] = pd.to_datetime(p["valid_from"])
    stock["ds"] = parse_date_key(stock["date_key"])
    v["ds"] = parse_date_key(v["date_key"])
    stock["produit_key"] = stock["produit_key"].astype(str)
    v["produit_key"] = v["produit_key"].astype(str)

    say("=" * 78)
    say("1. GRAIN ET UNICITÉ")
    say("=" * 78)
    say(f"  lignes                          : {len(stock):,}")
    n_pairs = stock.groupby(["produit_key", "ds"]).ngroups
    n_dup = int(stock.duplicated(subset=["produit_key", "ds"]).sum())
    say(f"  couples (produit, date) distincts : {n_pairs:,}")
    say(f"  doublons produit-date           : {n_dup}  <- doit être 0")
    say(f"  produits distincts              : {stock['produit_key'].nunique()} / 300")
    say(f"  dates : {stock['ds'].min().date()} -> {stock['ds'].max().date()} "
        f"({stock['ds'].nunique()} jours)")

    say("")
    say("=" * 78)
    say("2. COUVERTURE PRODUIT-DATE")
    say("=" * 78)
    dmin_all, dmax_all = v["ds"].min(), v["ds"].max()
    full_grid = pd.MultiIndex.from_product(
        [sorted(p["produit_key"].unique()), pd.date_range(dmin_all, dmax_all, freq="D")],
        names=["produit_key", "ds"],
    ).to_frame(index=False)
    say(f"  grille théorique complète (300 x {  (dmax_all-dmin_all).days+1 } j) : {len(full_grid):,}")
    say(f"  lignes fact_stock                                           : {len(stock):,}")
    say(f"  écart                                                       : "
        f"{len(full_grid) - len(stock):+,}")

    # Couverture par produit : première/dernière date de stock connue
    per_prod = stock.groupby("produit_key")["ds"].agg(["min", "max", "size"])
    per_prod.columns = ["premiere_date_stock", "derniere_date_stock", "n_jours"]
    say("")
    say(f"  jours de stock par produit : min {per_prod.n_jours.min()} | "
        f"médiane {per_prod.n_jours.median():.0f} | max {per_prod.n_jours.max()}")
    say(f"  produits avec dernière date < {dmax_all.date()} : "
        f"{int((per_prod.derniere_date_stock < dmax_all).sum())}")

    say("")
    say("  --- Comparaison avec valid_from (dim_produit) ---")
    cmp = per_prod.join(p.set_index("produit_key")[["valid_from"]])
    cmp["ecart_stock_vs_valid_from"] = (cmp["premiere_date_stock"] - cmp["valid_from"]).dt.days
    say(f"  écart (1ère date stock - valid_from) : médiane "
        f"{cmp['ecart_stock_vs_valid_from'].median():.0f} j, "
        f"min {cmp['ecart_stock_vs_valid_from'].min():.0f}, "
        f"max {cmp['ecart_stock_vs_valid_from'].max():.0f}")
    exact = int((cmp["ecart_stock_vs_valid_from"] == 0).sum())
    say(f"  produits où stock démarre EXACTEMENT à valid_from : {exact} / {len(cmp)}")

    fs = v.groupby("produit_key")["ds"].min()
    cmp2 = per_prod.join(fs.rename("premiere_vente"))
    cmp2["ecart_stock_vs_vente"] = (cmp2["premiere_vente"] - cmp2["premiere_date_stock"]).dt.days
    say("")
    say("  --- Comparaison avec la première vente observée ---")
    say(f"  écart (1ère vente - 1ère date stock) : médiane "
        f"{cmp2['ecart_stock_vs_vente'].median():.0f} j, "
        f"min {cmp2['ecart_stock_vs_vente'].min():.0f}, "
        f"max {cmp2['ecart_stock_vs_vente'].max():.0f}")
    say(f"  ventes AVANT la première date de stock connue : "
        f"{int((cmp2['ecart_stock_vs_vente'] < 0).sum())} produit(s)")

    say("")
    say("=" * 78)
    say("3. VALEURS DE STOCK")
    say("=" * 78)
    s = stock["niveau_stock"]
    say(f"  min {s.min()} | médiane {s.median():.0f} | max {s.max()} | moyenne {s.mean():.1f}")
    say(f"  valeurs négatives : {int((s < 0).sum())}  <- doit être 0")
    say(f"  valeurs nulles    : {int((s == 0).sum())} ({(s == 0).mean():.2%})")
    say(f"  valeurs manquantes: {int(s.isna().sum())}")

    say("")
    say("=" * 78)
    say("4. TROUS TEMPORELS PAR PRODUIT")
    say("=" * 78)
    trous = 0
    longueurs = []
    for pid, g in stock.sort_values("ds").groupby("produit_key"):
        gaps = g["ds"].diff().dt.days.dropna()
        bad = gaps[gaps > 1]
        trous += len(bad)
        longueurs.extend((bad - 1).tolist())
    say(f"  produits avec au moins un trou : "
        f"{stock.groupby('produit_key')['ds'].apply(lambda d: (d.sort_values().diff().dt.days > 1).any()).sum()}")
    say(f"  nombre total de trous          : {trous}")
    if longueurs:
        say(f"  longueur des trous : médiane {np.median(longueurs):.0f} j, max {max(longueurs):.0f} j")

    say("")
    say("=" * 78)
    say("5. RELATION STOCK <-> VENTES (censure de la demande)")
    say("=" * 78)
    daily_sales = v.groupby(["produit_key", "ds"])["quantite"].sum().rename("y").reset_index()
    m = stock.merge(daily_sales, on=["produit_key", "ds"], how="left")
    m["y"] = m["y"].fillna(0.0)

    say(f"  produit-jours avec stock_fin_jour = 0           : {int((m['niveau_stock'] == 0).sum()):,}")
    ventes_stock_nul = m[(m["niveau_stock"] == 0) & (m["y"] > 0)]
    say(f"  ventes POSITIVES un jour où stock_fin_jour = 0   : {len(ventes_stock_nul):,}")
    say("    -> plausible si niveau_stock est le stock de FIN de journée : les")
    say("       ventes du jour ont pu épuiser le stock (vente puis stock=0 le soir).")
    say(f"    part de ces cas / total produit-jours à stock nul : "
        f"{len(ventes_stock_nul) / max(int((m['niveau_stock']==0).sum()),1):.2%}")

    # Utiliser le stock de la VEILLE comme proxy de disponibilité en DÉBUT de jour J
    m = m.sort_values(["produit_key", "ds"])
    m["stock_veille"] = m.groupby("produit_key")["niveau_stock"].shift(1)
    say("")
    say("  --- Disponibilité en DÉBUT de journée (proxy = stock de la veille) ---")
    dispo = m.dropna(subset=["stock_veille"])
    rupture = dispo["stock_veille"] <= 0
    say(f"  produit-jours avec stock_veille <= 0 (rupture probable en entrée de journée) : "
        f"{int(rupture.sum()):,} ({rupture.mean():.2%})")
    say(f"  taux de disponibilité (stock_veille > 0)                                    : "
        f"{(~rupture).mean():.2%}")
    ventes_en_rupture = dispo[rupture & (dispo["y"] > 0)]
    say(f"  ventes positives malgré stock_veille <= 0 : {len(ventes_en_rupture):,} "
        f"({len(ventes_en_rupture) / max(int(rupture.sum()),1):.2%} des jours en rupture)")
    say("    -> un réapprovisionnement peut intervenir EN COURS de journée J : la vente")
    say("       est alors possible même si le stock de fin J-1 était nul.")

    say("")
    say("  --- Zéros de vente : avec vs sans rupture (stock_veille <= 0) ---")
    zero_days = dispo[dispo["y"] == 0]
    say(f"  zéros AVEC rupture (stock_veille <= 0) : {int((zero_days['stock_veille'] <= 0).sum()):,}")
    say(f"  zéros SANS rupture (stock_veille > 0)  : {int((zero_days['stock_veille'] > 0).sum()):,}")
    say(f"  total zéros observés dans fact_stock (grille stock) : {len(zero_days):,}")

    say("")
    say("=" * 78)
    say("6. SÉQUENCES DE RUPTURE")
    say("=" * 78)
    runs = []
    for pid, g in m.sort_values("ds").groupby("produit_key"):
        is_rupt = (g["niveau_stock"] <= 0).to_numpy()
        if not is_rupt.any():
            continue
        idx = np.flatnonzero(np.diff(np.concatenate(([0], is_rupt.view(np.int8), [0]))) != 0)
        for length in idx[1::2] - idx[0::2]:
            runs.append(int(length))
    if runs:
        rr = pd.Series(runs)
        say(f"  nombre de séquences de rupture (stock fin jour <= 0) : {len(rr):,}")
        say(f"  longueur : moyenne {rr.mean():.2f} | médiane {rr.median():.0f} | "
            f"p90 {rr.quantile(.9):.0f} | max {rr.max()}")
        for seuil in (7, 14, 30):
            say(f"    séquences > {seuil} j : {int((rr > seuil).sum())}")
    else:
        say("  aucune séquence de stock nul détectée.")

    say("")
    say("=" * 78)
    say("7. IMPACT SUR LE TAUX DE ZÉROS DE LA CIBLE (117 763 lignes, 50,77 %)")
    say("=" * 78)
    table = pd.read_parquet(PROJECT_ROOT / "data" / "processed" / "table_analytique.parquet")
    table["unique_id"] = table["unique_id"].astype(str)
    tj = table.merge(
        m[["produit_key", "ds", "niveau_stock", "stock_veille"]],
        left_on=["unique_id", "ds"], right_on=["produit_key", "ds"], how="left",
    )
    matched = tj["stock_veille"].notna()
    say(f"  lignes de la table analytique jointes à un stock_veille connu : "
        f"{int(matched.sum()):,} / {len(tj):,} ({matched.mean():.2%})")
    zeros = tj[tj["y"] == 0]
    zeros_matched = zeros[zeros["stock_veille"].notna()]
    say(f"  zéros de la cible                          : {len(zeros):,}")
    say(f"  dont avec stock_veille connu                : {len(zeros_matched):,}")
    censures = zeros_matched[zeros_matched["stock_veille"] <= 0]
    say(f"  dont CENSURÉS (stock_veille <= 0)           : {len(censures):,} "
        f"({len(censures)/max(len(zeros_matched),1):.2%} des zéros documentés)")
    say(f"  dont zéros SANS rupture apparente           : "
        f"{len(zeros_matched) - len(censures):,}")
    say("")
    say(f"  -> sur les {len(zeros):,} zéros de la table analytique, "
        f"{len(censures):,} ({len(censures)/len(zeros):.2%} du total) sont associés "
        f"à un stock de veille nul ou négatif : ce sont des candidats à la censure, "
        f"PAS une preuve d'absence de demande.")

    (PROJECT_ROOT / "reports" / "13_validation_stock.md").write_text(
        "# 13 — Validation de fact_stock\n\n"
        "_Sortie de `python scripts/validate_stock.py`._\n\n```\n" + OUT.getvalue() + "```\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
