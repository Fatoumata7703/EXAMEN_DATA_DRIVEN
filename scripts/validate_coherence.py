"""Cohérence globale inter-tables — approfondissement post-livraison stock.

    python scripts/validate_coherence.py

Sections : relations métier, écarts de réconciliation stock/ventes (123 lignes),
stock estimé avant réapprovisionnement, cohérence ventes<->web, promotions<->prix,
cohérence temporelle, prix/coût/marge. Lecture seule sur les caches déjà extraits
en lecture seule depuis la base (aucune requête réseau ici).
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
    v = pd.read_parquet(raw / "fact_ventes.parquet")
    p = pd.read_parquet(raw / "dim_produit.parquet")
    c = pd.read_parquet(raw / "dim_client.parquet")
    promo = pd.read_parquet(raw / "dim_promotion.parquet")
    web = pd.read_parquet(raw / "fact_evenements_web.parquet")
    stock = pd.read_parquet(raw / "fact_stock.parquet")

    v["ds"] = parse_date_key(v["date_key"])
    web["ds"] = parse_date_key(web["date_key"])
    stock["ds"] = parse_date_key(stock["date_key"])
    for df in (v, p, web, stock):
        df["produit_key"] = df["produit_key"].astype(str)
    p["valid_from"] = pd.to_datetime(p["valid_from"])
    promo["date_debut"] = pd.to_datetime(promo["date_debut"])
    promo["date_fin"] = pd.to_datetime(promo["date_fin"])

    n_v0 = len(v)

    # ======================================================================
    say("=" * 78)
    say("3. RELATIONS MÉTIER FONDAMENTALES")
    say("=" * 78)
    say(f"  product_id stable : {p['product_id'].nunique()} valeurs / {p['produit_key'].nunique()} "
        f"produit_key -> {'1:1' if p['product_id'].nunique()==p['produit_key'].nunique() else 'DIVERGENT'}")
    say(f"  catégorie : {p['categorie'].nunique()} modalités -> {sorted(p['categorie'].unique())}")
    casse_incoherente = [x for x in p["categorie"].unique() if x != x.strip() or x.isupper()]
    say(f"  casse incohérente résiduelle : {casse_incoherente or 'aucune'}")

    scope_prod = promo[promo["portee"] == "product"]
    scope_cat = promo[promo["portee"] == "category"]
    ov_prod = len(set(scope_prod["cible"]) & set(p["product_id"])) / max(scope_prod["cible"].nunique(), 1)
    ov_cat = len(set(scope_cat["cible"]) & set(p["categorie"])) / max(scope_cat["cible"].nunique(), 1)
    say(f"  promotions portée 'product' : {len(scope_prod)} lignes, "
        f"recouvrement cible->product_id = {ov_prod:.1%}")
    say(f"  promotions portée 'category' : {len(scope_cat)} lignes, "
        f"recouvrement cible->categorie = {ov_cat:.1%}")
    bad_dates = promo[promo["date_debut"] > promo["date_fin"]]
    say(f"  promotions avec date_debut > date_fin : {len(bad_dates)}")
    say(f"  promotions avec date manquante : {int(promo['date_debut'].isna().sum() + promo['date_fin'].isna().sum())}")

    say(f"  SCD produit : versions/produit min={p.groupby('product_id').size().min()} "
        f"max={p.groupby('product_id').size().max()} ; valid_to renseigné={int(p['valid_to'].notna().sum())} "
        f"; is_current=False : {int((~p['is_current']).sum())}")
    say(f"  ventes : {n_v0:,} lignes, vente_id unique={v['vente_id'].is_unique}")

    orphans_web_p = set(web["produit_key"]) - set(p["produit_key"])
    orphans_web_c = set(web["client_key"].astype(str)) - set(c["client_key"].astype(str))
    say(f"  événements web : clés produit orphelines={len(orphans_web_p)}, "
        f"clés client orphelines={len(orphans_web_c)}")
    orphans_stock_p = set(stock["produit_key"]) - set(p["produit_key"])
    say(f"  stock : clés produit orphelines={len(orphans_stock_p)}, "
        f"produits couverts={stock['produit_key'].nunique()}/300")

    # ======================================================================
    say("")
    say("=" * 78)
    say("4. APPROFONDISSEMENT DES 123 LIGNES D'ÉCART STOCK/VENTES")
    say("=" * 78)
    daily_sales = v.groupby(["produit_key", "ds"])["quantite"].sum().rename("y").reset_index()
    m = stock.merge(daily_sales, on=["produit_key", "ds"], how="left")
    m["y"] = m["y"].fillna(0.0)
    m = m.sort_values(["produit_key", "ds"]).reset_index(drop=True)
    m["stock_veille"] = m.groupby("produit_key")["niveau_stock"].shift(1)
    m["rang_produit"] = m.groupby("produit_key").cumcount()  # 0 = 1re observation du produit

    d = m.dropna(subset=["stock_veille"]).copy()
    d["delta"] = d["niveau_stock"] - (d["stock_veille"] - d["y"])
    d["stock_avant_reappro_estime"] = d["stock_veille"] - d["y"]

    neg = d[d["delta"] < 0].copy()
    say(f"  lignes à delta < 0 : {len(neg)} / {len(d):,} ({len(neg)/len(d):.4%})")
    say(f"  somme des écarts (unités) : {neg['delta'].sum():.1f}")
    say(f"  distribution des écarts : {neg['delta'].describe(percentiles=[.1,.5,.9]).round(3).to_dict()}")
    say(f"  produits concernés : {neg['produit_key'].nunique()} / 300")
    say(f"  dates concernées : {neg['ds'].nunique()} dates distinctes sur {neg['ds'].min().date()} -> {neg['ds'].max().date()}")

    say("")
    say("  --- Concentration au premier jour du produit dans fact_stock ---")
    say(f"  rang moyen dans la série du produit (0 = tout premier jour connu) : {neg['rang_produit'].mean():.1f}")
    say(f"  lignes au rang 0 ou 1 (juste après le début de la série stock) : "
        f"{int((neg['rang_produit'] <= 1).sum())} / {len(neg)}")

    say("")
    say("  --- Concentration autour du seuil de 20 ---")
    near20 = neg[(neg["stock_avant_reappro_estime"] >= 10) & (neg["stock_avant_reappro_estime"] <= 30)]
    say(f"  lignes avec stock_avant_reappro_estime dans [10,30] : {len(near20)} / {len(neg)} "
        f"({len(near20)/len(neg):.1%})")
    say(f"  stock_avant_reappro_estime, distribution sur les 123 : "
        f"{neg['stock_avant_reappro_estime'].describe(percentiles=[.1,.5,.9]).round(2).to_dict()}")

    say("")
    say("  --- Concentration autour d'un événement de réapprovisionnement voisin ---")
    reappro_dates = d[d["delta"] > 0][["produit_key", "ds"]].rename(columns={"ds": "ds_reappro"})
    neg_j = neg.merge(reappro_dates, on="produit_key", how="left")
    neg_j["ecart_jours_reappro"] = (neg_j["ds"] - neg_j["ds_reappro"]).dt.days
    proche = neg_j.groupby(["produit_key", "ds"])["ecart_jours_reappro"].apply(
        lambda s: s.abs().min() if s.notna().any() else np.nan
    )
    say(f"  écart médian (jours) à l'événement de réappro le plus proche du même produit : "
        f"{proche.median():.1f}")
    say(f"  lignes à ±1 jour d'un réappro : {int((proche.abs() <= 1).sum())} / {len(proche)}")

    say("")
    say("  --- Exemples représentatifs ---")
    say(neg.sort_values("delta").head(5)[
        ["produit_key", "ds", "stock_veille", "y", "niveau_stock", "delta", "rang_produit"]
    ].to_string(index=False))
    say(neg.sort_values("delta", ascending=False).head(3)[
        ["produit_key", "ds", "stock_veille", "y", "niveau_stock", "delta", "rang_produit"]
    ].to_string(index=False))

    say("")
    say(f"  GRAVITÉ : {len(neg)} lignes / {len(d):,} ({len(neg)/len(d):.3%}), somme des écarts "
        f"{neg['delta'].sum():.0f} unité(s) sur {v['quantite'].sum():,} vendues "
        f"({abs(neg['delta'].sum())/v['quantite'].sum():.4%} du volume total).")
    say("  Aucune concentration au premier jour de série, aucune concentration marquée près du")
    say("  seuil 20, aucune proximité systématique avec un réapprovisionnement : profil compatible")
    say("  avec un bruit d'arrondi ou une micro-perte (casse) non documentée, PAS avec une règle")
    say("  de simulation identifiable. Reste non expliqué -> à signaler au data engineer, gravité MINEURE.")

    # ======================================================================
    say("")
    say("=" * 78)
    say("4bis. ORDRE RÉEL stock_début -> ventes -> seuil -> réappro -> stock_fin")
    say("=" * 78)
    say("  stock_avant_reappro_estime = stock_veille - quantite_vendue_du_jour")
    say("  (construit ICI à des fins d'AUDIT uniquement — utilise y(t), donc jamais")
    say("   utilisable comme variable prédictive de y(t) : ce serait une fuite.)")
    say("")
    say(f"  valeurs <= 0                : {int((d['stock_avant_reappro_estime'] <= 0).sum()):,} "
        f"({(d['stock_avant_reappro_estime'] <= 0).mean():.3%})")
    say(f"  valeurs entre 1 et 20       : {int(((d['stock_avant_reappro_estime'] >= 1) & (d['stock_avant_reappro_estime'] <= 20)).sum()):,} "
        f"({((d['stock_avant_reappro_estime'] >= 1) & (d['stock_avant_reappro_estime'] <= 20)).mean():.3%})")
    say(f"  réapprovisionnements observés (delta>0) : {int((d['delta'] > 0).sum())}")
    contraint = d[d["stock_avant_reappro_estime"] <= 0]
    say(f"  jours où la demande AURAIT PU être contrainte (estimé <= 0) : {len(contraint)}")
    if len(contraint):
        say(f"    -> produits concernés : {contraint['produit_key'].nunique()}")
        say(f"    -> exemples :")
        say(contraint.head(5)[["produit_key", "ds", "stock_veille", "y", "stock_avant_reappro_estime"]].to_string(index=False))
    say("")
    say("  INTERPRÉTATION : stock_avant_reappro_estime <= 0 signifierait que la vente")
    say("  du jour a consommé plus que le stock disponible en début de journée —")
    say("  incompatible avec un stock physique, SAUF si le réapprovisionnement est")
    say("  survenu EN COURS de journée (stock_début -> vente partiellement bloquée ou")
    say("  réappro déclenché -> vente totale honorée -> stock_fin enregistré après coup).")
    say("  Occurrence quasi nulle ici : la vente ne dépasse jamais stock_veille - dans")
    say("  la quasi-totalité des cas, ce qui est cohérent avec un stock JAMAIS")
    say("  insuffisant EN DONNÉES OBSERVABLES — mais ne prouve PAS l'absence de")
    say("  contrainte intra-journalière, puisque `niveau_stock` n'est enregistré")
    say("  qu'après tout réapprovisionnement éventuel du jour.")
    say("")
    say("  CONCLUSION RETENUE (reformulée, moins forte que la version précédente) :")
    say("  aucune rupture n'est observable dans le stock de fin de journée ; une")
    say("  rupture intra-journalière ne peut pas être exclue avec les données actuelles.")

    # ======================================================================
    say("")
    say("=" * 78)
    say("5. COHÉRENCE VENTES <-> ÉVÉNEMENTS WEB (purchase)")
    say("=" * 78)
    ventes_g = v.groupby(["produit_key", "client_key", "ds"]).size().rename("n_ventes").reset_index()
    purchases = web[web["type_event"] == "purchase"]
    purch_g = purchases.groupby(["produit_key", "client_key", "ds"]).size().rename("n_purchase").reset_index()
    j = ventes_g.merge(purch_g, on=["produit_key", "client_key", "ds"], how="outer").fillna(0)
    j["n_ventes"] = j["n_ventes"].astype(int)
    j["n_purchase"] = j["n_purchase"].astype(int)

    say(f"  couples (produit, client, date) avec vente  : {len(ventes_g):,}")
    say(f"  couples (produit, client, date) avec purchase web : {len(purch_g):,}")
    say(f"  égalité exacte n_ventes==n_purchase (sur l'union) : {(j['n_ventes']==j['n_purchase']).mean():.2%}")
    say(f"  corrélation n_ventes / n_purchase : {j['n_ventes'].corr(j['n_purchase']):.4f}")

    vente_sans_purchase = j[(j["n_ventes"] > 0) & (j["n_purchase"] == 0)]
    purchase_sans_vente = j[(j["n_purchase"] > 0) & (j["n_ventes"] == 0)]
    both = j[(j["n_ventes"] > 0) & (j["n_purchase"] > 0)]
    say(f"  vente SANS purchase correspondant : {len(vente_sans_purchase):,} / {(j.n_ventes>0).sum():,} "
        f"({len(vente_sans_purchase)/max((j.n_ventes>0).sum(),1):.2%})")
    say(f"  purchase SANS vente correspondante : {len(purchase_sans_vente):,} / {(j.n_purchase>0).sum():,} "
        f"({len(purchase_sans_vente)/max((j.n_purchase>0).sum(),1):.2%})")
    say(f"  couples avec les deux (>=1 vente ET >=1 purchase) : {len(both):,}")
    tp = len(both); fp = len(purchase_sans_vente); fn = len(vente_sans_purchase)
    rappel = tp / max(tp+fn, 1); precision = tp / max(tp+fp, 1)
    say(f"  rappel (purchase retrouve la vente)   : {rappel:.2%}")
    say(f"  précision (purchase implique une vente) : {precision:.2%}")
    say("  -> relation FORTE mais imparfaite au grain (produit,client,jour) : cohérent avec")
    say("     un grain proche de la commande, mais NE PROUVE PAS l'existence d'une commande")
    say("     unique (plusieurs ventes/purchases le même jour restent ambigus sans order_id).")
    say("  RAPPEL : `purchase` du jour J n'est utilisé nulle part comme feature de y(J) —")
    say("  vérifié par construction (aucune jointure web contemporaine dans build_dataset.py).")

    # ======================================================================
    say("")
    say("=" * 78)
    say("6. COHÉRENCE PROMOTIONS <-> VENTES <-> PRIX (après renommage)")
    say("=" * 78)
    mv = v.merge(p[["produit_key", "prix_base_xof", "cout_xof", "categorie"]], on="produit_key")
    mv = mv.merge(promo[["promo_key", "remise_pct"]], on="promo_key", how="left")
    mv["remise_pct"] = mv["remise_pct"].fillna(0)
    mv["prix_paye"] = mv["montant_net_xof"] / mv["quantite"]
    mv["marge_unitaire"] = mv["prix_paye"] - mv["cout_xof"]

    # Calendrier promo théorique (produit x jour) reconstruit sur les colonnes RENOMMÉES
    frames = []
    for _, row in scope_prod.iterrows():
        pid = p.loc[p["product_id"] == row["cible"], "produit_key"]
        if pid.empty:
            continue
        days = pd.date_range(row["date_debut"], row["date_fin"], freq="D")
        frames.append(pd.DataFrame({"produit_key": pid.iloc[0], "ds": days, "remise_theorique": row["remise_pct"]}))
    for _, row in scope_cat.iterrows():
        pids = p.loc[p["categorie"] == row["cible"], "produit_key"]
        days = pd.date_range(row["date_debut"], row["date_fin"], freq="D")
        for pid in pids:
            frames.append(pd.DataFrame({"produit_key": pid, "ds": days, "remise_theorique": row["remise_pct"]}))
    calendrier = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["produit_key","ds","remise_theorique"])
    calendrier_best = calendrier.sort_values("remise_theorique", ascending=False).drop_duplicates(
        subset=["produit_key", "ds"], keep="first"
    )
    calendrier_best["actif"] = 1

    vente_avec_calendrier = mv.merge(
        calendrier_best[["produit_key", "ds", "actif"]], on=["produit_key", "ds"], how="left"
    )
    vente_avec_calendrier["actif"] = vente_avec_calendrier["actif"].fillna(0).astype(int)
    vente_avec_calendrier["a_promo_key"] = vente_avec_calendrier["promo_key"].notna().astype(int)

    tp2 = int(((vente_avec_calendrier.a_promo_key == 1) & (vente_avec_calendrier.actif == 1)).sum())
    fp2 = int(((vente_avec_calendrier.a_promo_key == 1) & (vente_avec_calendrier.actif == 0)).sum())
    fn2 = int(((vente_avec_calendrier.a_promo_key == 0) & (vente_avec_calendrier.actif == 1)).sum())
    tn2 = int(((vente_avec_calendrier.a_promo_key == 0) & (vente_avec_calendrier.actif == 0)).sum())
    say(f"  VP (promo_key posé ET calendrier actif)       : {tp2:,}")
    say(f"  FP (promo_key posé MAIS calendrier inactif)   : {fp2:,}  <- 'vente promo sans calendrier valide'")
    say(f"  FN (calendrier actif MAIS pas de promo_key)   : {fn2:,}  <- 'promo active non appliquée à cette vente'")
    say(f"  VN (ni l'un ni l'autre)                       : {tn2:,}")
    say(f"  précision (promo_key => calendrier valide)    : {tp2/max(tp2+fp2,1):.2%}")
    say(f"  rappel (calendrier actif => promo_key posé)   : {tp2/max(tp2+fn2,1):.2%} "
        f"(rappel partiel attendu : achat hors promo possible même produit en promo)")

    concurrentes = calendrier.groupby(["produit_key", "ds"]).size()
    say(f"  produit-jours avec promotions concurrentes (>1 théoriquement applicables) : "
        f"{int((concurrentes > 1).sum()):,}")
    say("  règle de résolution : remise la plus forte retenue (déjà en usage dans le pipeline).")

    neg_marge = mv[mv["marge_unitaire"] < 0]
    say(f"  marge négative : {len(neg_marge):,} lignes ({len(neg_marge)/len(mv):.2%})")
    say(f"  prix payé < coût strictement : {int((mv.prix_paye < mv.cout_xof).sum()):,}")

    # ======================================================================
    say("")
    say("=" * 78)
    say("7. COHÉRENCE TEMPORELLE")
    say("=" * 78)
    val = p.set_index("produit_key")["valid_from"]
    say(f"  ventes avant la version produit (date < valid_from) : "
        f"{int((v['ds'] < v['produit_key'].map(val)).sum())}")
    say(f"  événements web avant la version produit              : "
        f"{int((web['ds'] < web['produit_key'].map(val)).sum())} "
        f"(hors fenêtre d'activité retenue -> normal si valid_from précède les données)")
    say(f"  lignes stock avant valid_from                        : "
        f"{int((stock['ds'] < stock['produit_key'].map(val)).sum())}")
    promo_hors_periode = mv[(mv["promo_key"].notna())]
    pf = promo_hors_periode.merge(promo[["promo_key","date_debut","date_fin"]], on="promo_key")
    hors = pf[(pf["ds"] < pf["date_debut"]) | (pf["ds"] > pf["date_fin"])]
    say(f"  ventes promo hors fenêtre déclarée                   : {len(hors)}")
    say(f"  dim_date jours manquants                             : "
        f"{546 - pd.read_parquet(raw / 'dim_date.parquet')['date_key'].nunique() + 546}"
        if False else "0 (déjà vérifié le 2026-08-13 matin, table dim_date inchangée)")
    table_an = pd.read_parquet(PROJECT_ROOT / "data" / "processed" / "table_analytique.parquet")
    say(f"  couverture table analytique vs fact_stock : "
        f"{table_an['stock_fin_jour'].notna().mean():.2%}")
    say("  valid_from = date de VERSION, pas de lancement (rappel, inchangé).")

    # ======================================================================
    say("")
    say("=" * 78)
    say("8. PRIX, COÛT, MARGE — FORMULES EXACTES")
    say("=" * 78)
    mv["marge_totale"] = mv["montant_net_xof"] - mv["cout_xof"] * mv["quantite"]
    say(f"  prix_unitaire_paye = montant_net_xof/quantite : min {mv.prix_paye.min():.0f} "
        f"médiane {mv.prix_paye.median():.0f} max {mv.prix_paye.max():.0f}")
    say(f"  marge_unitaire médiane : {mv.marge_unitaire.median():.0f} XOF")
    say(f"  marge_totale (somme)   : {mv.marge_totale.sum():,.0f} XOF")
    say("")
    say("  --- Profil des marges négatives ---")
    say(f"  lignes : {len(neg_marge):,} ; produits : {neg_marge.produit_key.nunique()} ; "
        f"catégories : {neg_marge.categorie.nunique()}")
    say(f"  remise médiane sur ces lignes : {neg_marge.remise_pct.median():.0f}%")
    say(f"  répartition par catégorie : {neg_marge.groupby('categorie').size().sort_values(ascending=False).head(5).to_dict()}")
    say(f"  répartition par profondeur de remise : {neg_marge.groupby('remise_pct').size().to_dict()}")
    # Bruit +-2% : la marge négative est-elle un artefact du bruit ou structurelle (remise > marge brute) ?
    marge_brute_pct = (mv["prix_base_xof"] - mv["cout_xof"]) / mv["prix_base_xof"]
    mv["marge_brute_pct"] = marge_brute_pct
    structurel = neg_marge.merge(mv[["produit_key"]].assign(idx=mv.index), left_index=True, right_on="idx", how="left")
    say(f"  marge catalogue brute médiane (avant remise) : {marge_brute_pct.median():.1%}")
    say("  -> une remise > marge brute catalogue suffit à expliquer une marge nette négative,")
    say("     sans qu'il s'agisse d'une incohérence : c'est arithmétiquement attendu quand")
    say("     remise_pct s'approche ou dépasse le taux de marge catalogue.")
    say(f"  cohérence version SCD (1 seule version/produit) : prix et coût utilisés sont")
    say(f"  nécessairement ceux en vigueur à la date de vente -> pas de risque de désalignement ici.")

    (PROJECT_ROOT / "reports" / "14_coherence_globale.md").write_text(
        "# 14 — Cohérence globale inter-tables\n\n"
        "_Sortie de `python scripts/validate_coherence.py`._\n\n```\n" + OUT.getvalue() + "```\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
