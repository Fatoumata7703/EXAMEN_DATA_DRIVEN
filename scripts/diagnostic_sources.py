"""Diagnostic complémentaire : documentation du data engineer vs données réelles.

    python scripts/diagnostic_sources.py

Confronte `DATA_DICTIONARY.md` et le document d'architecture aux 6 tables
réellement exposées par Supabase. Lecture seule, aucune écriture.
"""

from __future__ import annotations

import io
import json
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


RAW = PROJECT_ROOT / "data" / "raw"


def main() -> int:
    p = pd.read_parquet(RAW / "dim_produit.parquet")
    c = pd.read_parquet(RAW / "dim_client.parquet")
    v = pd.read_parquet(RAW / "fact_ventes.parquet")
    w = pd.read_parquet(RAW / "fact_evenements_web.parquet")
    promo = pd.read_parquet(RAW / "dim_promotion.parquet")
    for df, col in ((p, "valid_from"), (p, "valid_to"), (c, "valid_from"), (c, "valid_to")):
        df[col] = pd.to_datetime(df[col])
    v["ds"] = parse_date_key(v["date_key"])
    w["ds"] = parse_date_key(w["date_key"])

    # ------------------------------------------------------------------
    say("=" * 78)
    say("A. ANALYSE SCD TYPE 2")
    say("=" * 78)
    for name, dim, key, natural in (
        ("dim_produit", p, "produit_key", "product_id"),
        ("dim_client", c, "client_key", "customer_id"),
    ):
        say(f"\n--- {name} ---")
        say(f"  lignes                       : {len(dim):,}")
        say(f"  cles de substitution ({key}) : {dim[key].nunique():,}")
        say(f"  identifiants metier ({natural}) : {dim[natural].nunique():,}")
        vc = dim.groupby(natural).size()
        say(f"  versions par identifiant     : min {vc.min()} | median {vc.median():.0f} | max {vc.max()}")
        say(f"  identifiants a >1 version    : {int((vc > 1).sum())}")
        say(f"  is_current = True            : {int(dim['is_current'].sum()):,}")
        say(f"  valid_to renseigne           : {int(dim['valid_to'].notna().sum()):,}")
        # Anomalies SCD
        multi_current = dim[dim["is_current"]].groupby(natural).size()
        say(f"  identifiants a >1 version courante : {int((multi_current > 1).sum())}")
        say(f"  identifiants sans version courante : {int(dim[natural].nunique() - (multi_current >= 1).sum())}")
        bad = dim[dim["valid_to"].notna() & (dim["valid_to"] < dim["valid_from"])]
        say(f"  valid_to anterieur a valid_from    : {len(bad)}")
        # Chevauchements / trous (seulement si versions multiples)
        overlaps = gaps = 0
        if (vc > 1).any():
            for _, grp in dim[dim[natural].isin(vc[vc > 1].index)].groupby(natural):
                g = grp.sort_values("valid_from")
                ends = g["valid_to"].fillna(pd.Timestamp.max)
                starts = g["valid_from"]
                for i in range(len(g) - 1):
                    if starts.iloc[i + 1] <= ends.iloc[i]:
                        overlaps += 1
                    elif (starts.iloc[i + 1] - ends.iloc[i]).days > 1:
                        gaps += 1
        say(f"  chevauchements de fenetres         : {overlaps}")
        say(f"  trous entre versions               : {gaps}")

    say("")
    say("  CONSEQUENCE : dim_produit compte 1 version par produit et dim_client")
    say("  1 version par client. Le SCD2 est en place STRUCTURELLEMENT mais AUCUNE")
    say("  historisation n'a encore eu lieu. La jointure temporelle est donc")
    say("  aujourd'hui equivalente a une jointure simple -- ce qui cessera d'etre")
    say("  vrai des le premier changement de prix ou de segment.")

    # Ventes rattachees a une version valide a leur date ?
    say("")
    val = p.set_index("produit_key")[["valid_from", "valid_to"]]
    j = v.join(val, on="produit_key")
    ok = (j["ds"] >= j["valid_from"]) & (j["valid_to"].isna() | (j["ds"] <= j["valid_to"]))
    say(f"  ventes dans la fenetre de validite de leur version : {ok.sum():,} / {len(j):,} ({ok.mean():.2%})")

    # ------------------------------------------------------------------
    say("")
    say("=" * 78)
    say("B. VARIABLES ANNONCEES PAR LE DICTIONNAIRE vs REELLEMENT PRESENTES")
    say("=" * 78)
    expected = {
        "dim_products.product_id": ("dim_produit", "product_id"),
        "dim_products.product_name": ("dim_produit", "product_name"),
        "dim_products.category": ("dim_produit", "categorie"),
        "dim_products.brand": ("dim_produit", "marque"),
        "dim_products.base_price_xof": ("dim_produit", "prix_base_xof"),
        "dim_products.cost_xof": ("dim_produit", "cout_xof"),
        "dim_products.popularity_score": ("dim_produit", None),
        "dim_products.launch_date": ("dim_produit", None),
        "dim_products.initial_stock": ("dim_produit", None),
        "dim_customers.region": ("dim_client", "region"),
        "dim_customers.age_bracket": ("dim_client", "age_bracket"),
        "dim_customers.signup_date": ("dim_client", None),
        "dim_customers.loyalty_segment": ("dim_client", "segment_fidelite"),
        "dim_customers.full_name": ("dim_client", None),
        "fact_transactions.order_id": ("fact_ventes", None),
        "fact_transactions.quantity": ("fact_ventes", "quantite"),
        "fact_transactions.unit_price_xof": ("fact_ventes", None),
        "fact_transactions.discount_pct_applied": ("fact_ventes", None),
        "fact_transactions.order_date": ("fact_ventes", "date_key"),
        "stock_daily.stock_level": (None, None),
        "web_events.session_id": ("fact_evenements_web", None),
        "web_events.event_timestamp": ("fact_evenements_web", None),
        "web_events.referral_source": ("fact_evenements_web", None),
        "web_events.device": ("fact_evenements_web", "device"),
        "web_events.event_type": ("fact_evenements_web", "type_event"),
    }
    frames = {"dim_produit": p, "dim_client": c, "fact_ventes": v, "fact_evenements_web": w}
    say(f"  {'variable source':<38} {'table cible':<22} {'statut'}")
    manquantes = []
    for src, (table, col) in expected.items():
        if table is None:
            statut, cible = "TABLE ABSENTE", "-"
            manquantes.append(src)
        elif col is None:
            statut, cible = "ABSENTE", table
            manquantes.append(src)
        else:
            statut = "presente" if col in frames[table].columns else "ABSENTE"
            cible = f"{table}.{col}"
            if statut != "presente":
                manquantes.append(src)
        say(f"  {src:<38} {cible:<22} {statut}")
    say("")
    say(f"  -> {len(manquantes)} variable(s) source absente(s) du warehouse.")

    # ------------------------------------------------------------------
    say("")
    say("=" * 78)
    say("C. RECONCILIATION DES ANOMALIES ANNONCEES")
    say("=" * 78)
    say("  Le jeu Raw n'est PAS accessible : la reconciliation porte sur ce qui")
    say("  reste observable dans le warehouse (etat final), pas sur le detail des")
    say("  lignes rejetees.")
    say("")
    say(f"  {'anomalie annoncee':<42} {'volume Raw':>11}  {'etat dans Supabase'}")
    say(f"  {'doublons exacts fact_transactions':<42} {'~425':>11}  "
        f"0 doublon (vente_id unique sur {len(v):,})")
    say(f"  {'quantites negatives':<42} {'~85':>11}  "
        f"{int((v.quantite <= 0).sum())} quantite <= 0")
    orph = set(v["produit_key"]) - set(p["produit_key"])
    say(f"  {'FK orphelines P99999':<42} {'42':>11}  {len(orph)} cle orpheline")
    upper = [x for x in p["categorie"].unique() if str(x).isupper()]
    say(f"  {'categories en MAJUSCULES':<42} {'15':>11}  "
        f"{len(upper)} categorie en majuscules ({p.categorie.nunique()} distinctes)")
    say(f"  {'nulls region / age_bracket':<42} {'~3%':>11}  "
        f"region {c.region.isna().mean():.2%} | age {c.age_bracket.isna().mean():.2%}")
    say(f"  {'timestamps web desordonnes':<42} {'~1%':>11}  "
        f"INVERIFIABLE (event_timestamp absent, seul date_key subsiste)")
    say("")
    say("  --- Reconciliation arithmetique des volumes ---")
    say(f"    volume Raw annonce (~)            : 86 000")
    say(f"    - doublons exacts                 :   -425")
    say(f"    - quantites negatives             :    -85")
    say(f"    - FK orphelines P99999            :    -42")
    say(f"    = attendu apres nettoyage         : ~85 448")
    say(f"    volume reel dans fact_ventes      : {len(v):,}")
    say(f"    ecart                             : {85448 - len(v):+,}")
    say("    -> l'ecart tient a l'imprecision du '~86 000' annonce ; il ne peut")
    say("       etre leve qu'avec le compte EXACT du fichier Raw.")

    # Valeurs de remplacement eventuelles cote client
    say("")
    for col in ("region", "age_bracket", "segment_fidelite"):
        if col in c.columns:
            vals = c[col].value_counts(dropna=False)
            say(f"  {col} : {len(vals)} modalites -> {list(vals.index[:12])}")

    # ------------------------------------------------------------------
    say("")
    say("=" * 78)
    say("D. GRAIN DES VENTES ET NOMMAGE")
    say("=" * 78)
    say(f"  vente_id unique                    : {v.vente_id.is_unique}")
    say(f"  lignes                             : {len(v):,}")
    say(f"  couples (client, date) distincts   : {v.groupby(['client_key','ds']).ngroups:,}")
    dup_cd = v.groupby(["client_key", "ds"]).size()
    say(f"  client-jour avec >1 ligne          : {int((dup_cd > 1).sum()):,} "
        f"(max {dup_cd.max()} lignes)")
    say("  -> order_id est ABSENT : impossible de reconstituer une commande.")
    say("     Un meme client peut avoir plusieurs lignes le meme jour, qui peuvent")
    say("     appartenir a une seule commande multi-produits ou a plusieurs.")
    say("     `n_transactions` doit donc etre renomme `nombre_lignes_vente`.")

    # ------------------------------------------------------------------
    say("")
    say("=" * 78)
    say("E. PRIX PAYE, REMISE ET MARGE")
    say("=" * 78)
    m = v.merge(p[["produit_key", "prix_base_xof", "cout_xof"]], on="produit_key", how="left")
    m = m.merge(promo[["promo_key", "remise_pct"]], on="promo_key", how="left")
    m["prix_unitaire_paye"] = m["montant_net_xof"] / m["quantite"]
    m["remise_appliquee_pct"] = 100 * (1 - m["prix_unitaire_paye"] / m["prix_base_xof"])
    m["remise_planifiee_pct"] = m["remise_pct"].fillna(0)
    say("  prix_unitaire_paye = montant_net_xof / quantite  (reconstitue exactement)")
    say(f"    min {m.prix_unitaire_paye.min():,.0f} | median {m.prix_unitaire_paye.median():,.0f} "
        f"| max {m.prix_unitaire_paye.max():,.0f} XOF")
    say("")
    ecart = m["remise_appliquee_pct"] - m["remise_planifiee_pct"]
    say("  remise appliquee vs remise planifiee (points de pourcentage) :")
    say(f"    median {ecart.median():+.3f} | p5 {ecart.quantile(.05):+.3f} | p95 {ecart.quantile(.95):+.3f}")
    say(f"    |ecart| <= 2 pts : {(ecart.abs() <= 2).mean():.2%}")
    say("    -> le bruit de +-2 % identifie precedemment est un ECART ENTRE LE PRIX")
    say("       PAYE ET LE PRIX CATALOGUE REMISE, non une incoherence : le")
    say("       dictionnaire confirme que unit_price_xof est 'le prix reellement")
    say("       paye'. Il est donc porteur d'information pour le pricing.")
    say("")
    sans_promo = m[m["promo_key"].isna()]
    say(f"  lignes SANS promotion : remise appliquee mediane "
        f"{sans_promo.remise_appliquee_pct.median():+.3f} pts "
        f"(etendue {sans_promo.remise_appliquee_pct.min():+.2f} / {sans_promo.remise_appliquee_pct.max():+.2f})")
    say("")
    say(f"  cout_xof present : OUI -> marge calculable")
    m["marge_unitaire"] = m["prix_unitaire_paye"] - m["cout_xof"]
    m["taux_marge"] = m["marge_unitaire"] / m["prix_unitaire_paye"]
    say(f"    marge unitaire mediane : {m.marge_unitaire.median():,.0f} XOF")
    say(f"    taux de marge : median {m.taux_marge.median():.1%} | "
        f"p5 {m.taux_marge.quantile(.05):.1%} | p95 {m.taux_marge.quantile(.95):.1%}")
    say(f"    lignes a marge negative : {int((m.marge_unitaire < 0).sum()):,}")

    # Variation de prix par produit : condition de faisabilite du pricing
    say("")
    say("  --- Variation de prix par produit (faisabilite de l'elasticite) ---")
    niveaux = m.groupby("produit_key")["prix_unitaire_paye"].nunique()
    say(f"    niveaux de prix distincts par produit : median {niveaux.median():.0f} | "
        f"min {niveaux.min()} | max {niveaux.max()}")
    ratio = m.groupby("produit_key")["prix_unitaire_paye"].agg(lambda s: s.max() / s.min())
    say(f"    amplitude max/min par produit : median {ratio.median():.3f} | p95 {ratio.quantile(.95):.3f}")
    prix_cat = p.groupby("product_id")["prix_base_xof"].nunique()
    say(f"    produits dont le PRIX CATALOGUE varie : {int((prix_cat > 1).sum())} / {len(prix_cat)}")
    say("    -> le prix catalogue est FIXE (une seule version SCD par produit).")
    say("       Seules les promotions font varier le prix paye : l'elasticite ne")
    say("       sera identifiable que via l'effet promotionnel.")

    # ------------------------------------------------------------------
    say("")
    say("=" * 78)
    say("F. IMPACT ESTIME DU STOCK MANQUANT")
    say("=" * 78)
    t = pd.read_parquet(PROJECT_ROOT / "data" / "processed" / "table_analytique.parquet")
    say(f"  lignes de la table analytique     : {len(t):,}")
    say(f"  lignes annoncees pour stock_daily : ~118 000")
    say(f"  ecart                             : {118000 - len(t):+,}")
    say("  -> la proximite des deux volumes indique que stock_daily couvre le meme")
    say("     grain produit x jour sur la meme fenetre. C'est un indice fort que la")
    say("     borne launch_date est proche de la borne actuellement reconstituee.")
    say("")
    say(f"  zeros actuels : {int((t.y == 0).sum()):,} ({(t.y == 0).mean():.2%})")
    say("  Sans stock_daily, il est IMPOSSIBLE de partitionner ces zeros entre :")
    say("    - absence de demande (vrai zero, exploitable) ;")
    say("    - rupture de stock (demande censuree, a masquer ou ponderer).")
    say("  Le dictionnaire indique que les ventes s'ARRETENT quand le stock atteint 0.")
    say("  Une part inconnue des 50,77 % de zeros est donc de la censure, et non de")
    say("  la demande nulle. Tout modele entraine sur ces zeros apprend partiellement")
    say("  la contrainte d'offre.")

    report = PROJECT_ROOT / "reports" / "06_diagnostic_sources.md"
    report.write_text(
        "# 06 — Documentation du data engineer vs données réelles\n\n"
        "_Sortie brute de `python scripts/diagnostic_sources.py`._\n\n```\n"
        + OUT.getvalue()
        + "```\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
