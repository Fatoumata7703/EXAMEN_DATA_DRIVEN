"""
fact_exposition_reco — v4, corrige la fuite structurelle de la v3 : les slates
étaient construits en utilisant la connaissance de CE QUI SERA acheté/vu plus tard
dans la session (donc le "modèle" connaissait déjà la réponse). En v4, un produit
n'entre dans un slate QUE si son score, calculé avec des informations disponibles
STRICTEMENT AVANT impression_timestamp, le place dans le top-K.

Deux politiques réelles, pas juste des étiquettes :
  - controle    : popularite_globale_v1 — popularité cumulée du produit (toutes ventes
                  confirmées), recalculée en cumul glissant par semaine, toujours
                  strictement antérieure à l'impression.
  - traitement  : challenger_affinite_categorie_v1 — score = affinité du client pour
                  la catégorie du produit (achats confirmés antérieurs dans cette
                  catégorie) + popularité globale en repli (visiteurs anonymes / sans
                  historique).

Résolution temporelle du score : hebdomadaire (semaine ISO), pas à la timestamp près
— chaque score utilise exclusivement les semaines ISO STRICTEMENT complètes avant la
semaine de l'impression. Simplification documentée, choisie pour rester calculable à
l'échelle du projet tout en respectant strictement l'absence de fuite.

Lignage :
  script  : fact_exposition_reco_v4.py
  seed    : 47
  entrees : dim_produit.csv, fact_ventes.csv, fact_evenements_web.csv (Gold, v3 pipeline)
"""
import hashlib
import os
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path

SEED = 47
rng = np.random.default_rng(SEED)

STAR_DIR = Path(os.environ.get(
    "STAR_DIR", str(Path(__file__).resolve().parent.parent / "03_pipeline_ingestion" / "lake" / "gold" / "star_schema")
))
OUT_DIR = Path(os.environ.get("OUT_DIR", str(Path(__file__).resolve().parent / "donnees")))
OUT_DIR.mkdir(exist_ok=True)

TOP_K = 5              # taille du slate
SAMPLING_RATE = 0.25    # taux d'échantillonnage UNIFORME (même règle achat/non-achat)

print("Chargement des données existantes (inchangées)...")
dim_produit = pd.read_csv(STAR_DIR / "dim_produit.csv")
fact_ventes = pd.read_csv(STAR_DIR / "fact_ventes.csv")
fact_web = pd.read_csv(STAR_DIR / "fact_evenements_web.csv", low_memory=False)
fact_web["event_timestamp"] = pd.to_datetime(fact_web["event_timestamp"], utc=True)

dim_produit["valid_from"] = pd.to_datetime(dim_produit["valid_from"]).dt.tz_localize("UTC")
produit_keys = dim_produit["produit_key"].to_numpy()
categorie_de = dict(zip(dim_produit["produit_key"], dim_produit["categorie"]))
launch_of = dict(zip(dim_produit["produit_key"], dim_produit["valid_from"]))

fact_ventes["date_key"] = fact_ventes["date_key"].astype(str)
fact_ventes["date"] = pd.to_datetime(fact_ventes["date_key"], format="%Y%m%d", utc=True)
fact_ventes_conf = fact_ventes[fact_ventes["statut_commande"] == "confirmee"].merge(
    dim_produit[["produit_key", "categorie"]], on="produit_key"
)
fact_ventes_conf["semaine"] = fact_ventes_conf["date"].dt.to_period("W-SUN").apply(lambda p: p.start_time).dt.tz_localize("UTC")

# ----------------------------------------------------------------------------
# Popularité globale cumulée, PAR SEMAINE, toujours strictement antérieure
# ----------------------------------------------------------------------------
print("Construction de la popularité globale hebdomadaire (cumul strictement antérieur)...")
pop_hebdo = fact_ventes_conf.groupby(["semaine", "produit_key"])["quantite"].sum().unstack(fill_value=0)
pop_cumulee = pop_hebdo.rolling(window=4, min_periods=1).sum().shift(1).fillna(0)  # popularité GLISSANTE (4 semaines), pas cumulée depuis le début -- plus réaliste, évite le verrouillage d'un leader précoce

# ----------------------------------------------------------------------------
# Affinité client x catégorie, PAR SEMAINE, toujours strictement antérieure
# ----------------------------------------------------------------------------
print("Construction de l'affinité client x catégorie hebdomadaire...")
affinite_hebdo = fact_ventes_conf.groupby(["semaine", "client_key", "categorie"]).size().unstack(fill_value=0)
affinite_cumulee = affinite_hebdo.groupby(level=0).sum()  # place-holder, recalculé proprement ci-dessous

# reconstruction propre : cumul par (client_key, categorie) au fil des semaines
aff_pivot = fact_ventes_conf.pivot_table(
    index="semaine", columns=["client_key", "categorie"], values="quantite", aggfunc="count", fill_value=0
)
aff_cumulee = aff_pivot.rolling(window=4, min_periods=1).sum().shift(1).fillna(0)

semaines_disponibles = sorted(pop_cumulee.index)


def semaine_de(ts):
    """Renvoie la semaine ISO (lundi) contenant ts."""
    return pd.Timestamp(ts).to_period("W-SUN").start_time.tz_localize("UTC") if pd.Timestamp(ts).tzinfo is None \
        else pd.Timestamp(ts).tz_convert("UTC").to_period("W-SUN").start_time.tz_localize("UTC")


def semaine_precedente_disponible(sem):
    """Dernière semaine du tableau cumulé <= sem (les données sont déjà décalées d'1 semaine)."""
    idx = np.searchsorted(semaines_disponibles, sem, side="right") - 1
    return semaines_disponibles[idx] if idx >= 0 else None


# ----------------------------------------------------------------------------
# Exclusion des sessions bot + échantillonnage UNIFORME (même règle achat/non-achat)
# ----------------------------------------------------------------------------
print("Échantillonnage uniforme des sessions (bots exclus, même règle pour tous)...")
bot_sessions = set(fact_web.loc[fact_web["est_bot"], "session_id"].unique())
fact_web_clean = fact_web[~fact_web["session_id"].isin(bot_sessions)]

session_first_event = fact_web_clean.groupby("session_id")["event_timestamp"].min()
session_meta = fact_web_clean.groupby("session_id").agg(
    client_key=("client_key", "first"), anonymous_id=("anonymous_id", "first")
)
session_meta["impression_timestamp"] = session_first_event

all_sessions = session_meta.index.to_numpy()
n_sample = int(len(all_sessions) * SAMPLING_RATE)
sampled_session_ids = rng.choice(all_sessions, size=n_sample, replace=False)
print(f"{len(sampled_session_ids)} / {len(all_sessions)} sessions échantillonnées ({SAMPLING_RATE:.0%}, taux unique achat/non-achat).")

# ----------------------------------------------------------------------------
# Assignation PERSISTANTE du groupe (inchangé par rapport à la v3)
# ----------------------------------------------------------------------------
all_client_keys = fact_web_clean["client_key"].dropna().unique()
group_by_client = dict(zip(all_client_keys, rng.choice(["controle", "traitement"], size=len(all_client_keys), p=[0.5, 0.5])))
all_anon_ids = fact_web_clean["anonymous_id"].dropna().unique()
group_by_anon = dict(zip(all_anon_ids, rng.choice(["controle", "traitement"], size=len(all_anon_ids), p=[0.5, 0.5])))

# ----------------------------------------------------------------------------
# Événements réels par (session, produit, type) -> premier timestamp APRÈS impression
# (précalculé une fois pour ne jamais rescanner tout le DataFrame)
# ----------------------------------------------------------------------------
events_lookup = fact_web_clean.groupby(["session_id", "produit_key", "type_event"])["event_timestamp"].min().to_dict()

EXPERIMENT_ID = "XPRECO_V4_0001"
assignment_cache = {}


def get_assignment(client_key, anon_id):
    key = client_key if pd.notna(client_key) else anon_id
    if key not in assignment_cache:
        assignment_cache[key] = f"ASG{hashlib.md5(str(key).encode()).hexdigest()[:10]}"
    return assignment_cache[key]


print("Construction des slates (scoring réel, aucune connaissance du futur de la session)...")
exposures = []
exposure_counter = 0
slate_counter = 0

for sid in sampled_session_ids:
    meta = session_meta.loc[sid]
    client_key, anon_id, impression_ts = meta["client_key"], meta["anonymous_id"], meta["impression_timestamp"]

    sem = impression_ts.to_period("W-SUN").start_time.tz_localize("UTC")
    sem_dispo = semaine_precedente_disponible(sem)

    # produits déjà lancés au moment de l'impression -> seul pool de candidats légitime
    candidats = [pk for pk in produit_keys if launch_of[pk] < impression_ts]
    if not candidats:
        continue

    groupe = group_by_client.get(client_key) if pd.notna(client_key) else group_by_anon.get(anon_id, "controle")
    modele = "popularite_globale_v1" if groupe == "controle" else "challenger_affinite_categorie_v1"

    if sem_dispo is None:
        scores = {pk: 0.0 for pk in candidats}  # aucune donnée antérieure disponible (tout début de période)
    elif groupe == "controle":
        pop_row = pop_cumulee.loc[sem_dispo] if sem_dispo in pop_cumulee.index else None
        scores = {pk: float(pop_row.get(pk, 0)) if pop_row is not None else 0.0 for pk in candidats}
    else:
        pop_row = pop_cumulee.loc[sem_dispo] if sem_dispo in pop_cumulee.index else None
        pop_fallback = {pk: float(pop_row.get(pk, 0)) if pop_row is not None else 0.0 for pk in candidats}
        aff_scores = {}
        if pd.notna(client_key) and sem_dispo in aff_cumulee.index:
            row = aff_cumulee.loc[sem_dispo]
            for pk in candidats:
                cat = categorie_de[pk]
                try:
                    aff_scores[pk] = float(row.get((client_key, cat), 0))
                except Exception:
                    aff_scores[pk] = 0.0
        else:
            aff_scores = {pk: 0.0 for pk in candidats}
        scores = {pk: aff_scores[pk] * 100000 + pop_fallback[pk] for pk in candidats}

    scored = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    top_k = scored[:TOP_K]
    if not top_k:
        continue

    score_array = np.array([s for _, s in top_k])
    exp_scores = np.exp(score_array - score_array.max())
    propensites = exp_scores / exp_scores.sum()

    slate_counter += 1
    slate_id = f"SLT{slate_counter:09d}"
    assignment_id = get_assignment(client_key, anon_id)

    for rank, ((pk, score), prop) in enumerate(zip(top_k, propensites), start=1):
        view_ts = events_lookup.get((sid, pk, "view"))
        cart_ts = events_lookup.get((sid, pk, "add_to_cart"))
        purchase_ts = events_lookup.get((sid, pk, "purchase"))

        # NE CONSERVER QUE les actions strictement APRES l'impression
        view_ts = view_ts if (view_ts is not None and view_ts > impression_ts) else None
        cart_ts = cart_ts if (cart_ts is not None and cart_ts > impression_ts) else None
        purchase_ts = purchase_ts if (purchase_ts is not None and purchase_ts > impression_ts) else None

        exposure_counter += 1
        exposures.append({
            "recommendation_id": f"REC{exposure_counter:09d}",
            "slate_id": slate_id,
            "experiment_id": EXPERIMENT_ID,
            "assignment_id": assignment_id,
            "client_key": client_key if pd.notna(client_key) else None,
            "anonymous_id": anon_id if pd.notna(anon_id) else None,
            "session_id": sid,
            "model_version": modele,
            "model_score": round(float(score), 3),
            "produit_key": pk,
            "rank": rank,
            "impression_timestamp": impression_ts.isoformat(),
            "viewed_after_impression": view_ts is not None,
            "view_timestamp": view_ts.isoformat() if view_ts is not None else None,
            "added_to_cart_after": cart_ts is not None,
            "add_to_cart_timestamp": cart_ts.isoformat() if cart_ts is not None else None,
            "purchased_after": purchase_ts is not None,
            "purchase_timestamp": purchase_ts.isoformat() if purchase_ts is not None else None,
            "experiment_group": groupe,
            "group_assignment_propensity": 0.5,
            "session_selection_probability": SAMPLING_RATE,
            "product_exposure_probability": round(float(prop), 4),
        })

fact_exposition_reco_v4 = pd.DataFrame(exposures)
out_path = OUT_DIR / "fact_exposition_reco_v4.csv"
fact_exposition_reco_v4.to_csv(out_path, index=False)

print(f"\n{len(fact_exposition_reco_v4)} expositions générées ({slate_counter} slates).")
print(f"Sauvegardé : {out_path}")
print(f"Empreinte de sortie (SHA256) : {hashlib.sha256(open(out_path,'rb').read()).hexdigest()}")
print(f"Date d'exécution : {datetime.now().isoformat()}")
print(f"Seed : {SEED}")
