"""
Analyse de significativité — au grain PRODUIT (n=300 observations indépendantes),
pas au grain produit-semaine (n=11 799, pseudo-répliqué : les mêmes 300 produits
reviennent chaque semaine, donc les observations d'un même produit ne sont pas
indépendantes entre elles -- l'unité de randomisation est le produit, l'analyse
doit se faire à ce grain, pas à un grain plus fin qui gonflerait artificiellement
la taille d'échantillon et la significativité apparente).

Pour chaque produit : moyenne de units_sold_window_7j / revenue_window_xof_7j /
margin_window_xof_7j sur toutes ses décisions (nombre de semaines variable selon les
exclusions lancement/promo, d'où l'usage d'une MOYENNE et non d'une somme).

3 comparaisons : traitement_5pct / traitement_10pct / traitement_15pct, chacun vs
controle_0pct. Correction de Holm sur les 3 p-values de chaque outcome (9 tests au
total, 3 familles de 3 comparaisons).
"""
import numpy as np
import pandas as pd
from pathlib import Path

SEED = 49
rng = np.random.default_rng(SEED)
N_BOOTSTRAP = 10000
N_PERMUTATIONS = 10000

V4_DIR = Path("/home/claude/journal_v4")
ep = pd.read_csv(V4_DIR / "fact_experimentation_prix_v4.csv")

# ----------------------------------------------------------------------------
# Agrégation au grain produit (une ligne par produit, respecte l'unité de randomisation)
# ----------------------------------------------------------------------------
produit_level = ep.groupby(["produit_key", "treatment_group"]).agg(
    units_sold_window_7j=("units_sold_window_7j", "mean"),
    revenue_window_xof_7j=("revenue_window_xof_7j", "mean"),
    margin_window_xof_7j=("margin_window_xof_7j", "mean"),
    n_decisions=("decision_id", "count"),
).reset_index()

print(f"{len(produit_level)} produits (grain d'analyse), répartition :")
print(produit_level["treatment_group"].value_counts())


def bootstrap_ci(a, b, n_boot=N_BOOTSTRAP, alpha=0.05):
    """IC bootstrap (percentile) sur la différence de moyennes b - a."""
    diffs = np.empty(n_boot)
    for i in range(n_boot):
        sa = rng.choice(a, size=len(a), replace=True)
        sb = rng.choice(b, size=len(b), replace=True)
        diffs[i] = sb.mean() - sa.mean()
    lo, hi = np.percentile(diffs, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return diffs.mean(), lo, hi


def permutation_test(a, b, n_perm=N_PERMUTATIONS):
    """Test de permutation bilatéral sur la différence de moyennes."""
    observed = b.mean() - a.mean()
    pooled = np.concatenate([a, b])
    n_a = len(a)
    count_extreme = 0
    for _ in range(n_perm):
        rng.shuffle(pooled)
        perm_diff = pooled[n_a:].mean() - pooled[:n_a].mean()
        if abs(perm_diff) >= abs(observed):
            count_extreme += 1
    p_value = (count_extreme + 1) / (n_perm + 1)  # +1 : correction standard (jamais p=0 exactement)
    return observed, p_value


def holm_correction(p_values):
    """Correction de Holm-Bonferroni, retourne les p-values ajustées dans l'ordre d'origine."""
    p_values = np.array(p_values)
    order = np.argsort(p_values)
    m = len(p_values)
    adjusted = np.empty(m)
    running_max = 0
    for rank, idx in enumerate(order):
        adj = (m - rank) * p_values[idx]
        running_max = max(running_max, adj)
        adjusted[idx] = min(running_max, 1.0)
    return adjusted


OUTCOMES = ["units_sold_window_7j", "revenue_window_xof_7j", "margin_window_xof_7j"]
COMPARISONS = ["traitement_5pct", "traitement_10pct", "traitement_15pct"]

resultats = []
for outcome in OUTCOMES:
    controle_vals = produit_level[produit_level["treatment_group"] == "controle_0pct"][outcome].to_numpy()
    p_values_famille = []
    lignes_famille = []
    for comp in COMPARISONS:
        treat_vals = produit_level[produit_level["treatment_group"] == comp][outcome].to_numpy()
        diff_boot, ci_lo, ci_hi = bootstrap_ci(controle_vals, treat_vals)
        diff_obs, p_value = permutation_test(controle_vals, treat_vals)
        lignes_famille.append({
            "outcome": outcome,
            "comparaison": f"{comp}_vs_controle",
            "n_controle": len(controle_vals),
            "n_traitement": len(treat_vals),
            "difference_observee": round(diff_obs, 3),
            "ic95_bootstrap_bas": round(ci_lo, 3),
            "ic95_bootstrap_haut": round(ci_hi, 3),
            "p_value_permutation": round(p_value, 4),
        })
        p_values_famille.append(p_value)

    p_adjustees = holm_correction(p_values_famille)
    for ligne, p_adj in zip(lignes_famille, p_adjustees):
        ligne["p_value_holm_ajustee"] = round(p_adj, 4)
        ligne["significatif_5pct"] = bool(p_adj < 0.05)
        resultats.append(ligne)

resultats_df = pd.DataFrame(resultats)
out_path = V4_DIR / "analyse_significativite_v4.csv"
resultats_df.to_csv(out_path, index=False)

print("\n=== RÉSULTATS ===")
print(resultats_df.to_string(index=False))
print(f"\nSauvegardé : {out_path}")
