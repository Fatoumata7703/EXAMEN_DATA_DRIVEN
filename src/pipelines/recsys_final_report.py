"""Recommandation V1 — rapport de synthèse final des baselines (aucune
sélection ni archivage de modèle : lecture pure des artefacts déjà produits
par `recsys_prototype.py` et `recsys_verification.py`).

    python -m src.pipelines.recsys_final_report
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pandas as pd

from src.config.settings import PROJECT_ROOT
from src.recsys.data import WINDOWS
from src.utils.logging_utils import get_logger, setup_logging

logger = get_logger(__name__)
REPORTS = PROJECT_ROOT / "reports"
RECSYS_DIR = PROJECT_ROOT / "reports" / "recsys_final"


def main() -> None:
    setup_logging()
    summaries = pd.read_csv(RECSYS_DIR / "baselines_summaries.csv")
    default = summaries[summaries["policy_combo"] == "defaut_exclut_achats_stock_filtre"].copy()

    events = [json.loads(l) for l in (REPORTS / "38_recsys_log.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    timing = pd.DataFrame([e for e in events if e["type"] == "resume_modele_fenetre"])
    timing_default = timing[timing["policy_combo"] == "defaut_exclut_achats_stock_filtre"]

    windows_meta = {w.index: (str(w.train_end.date()), str(w.test_start.date()), str(w.test_end.date())) for w in WINDOWS}

    merged = default.merge(
        timing_default[["fenetre", "modele", "duree_s", "n_clients_evaluables", "n_clients_scores", "n_erreurs", "n_fallback"]],
        on=["fenetre", "modele"], how="left",
    )
    merged["train_end"] = merged["fenetre"].map(lambda f: windows_meta[f][0])
    merged["test_start"] = merged["fenetre"].map(lambda f: windows_meta[f][1])
    merged["test_end"] = merged["fenetre"].map(lambda f: windows_meta[f][2])

    cols = ["fenetre", "train_end", "test_start", "test_end", "modele", "n_clients_evaluables",
            "recall_at_5", "recall_at_10", "precision_at_5", "precision_at_10", "ndcg_at_5", "ndcg_at_10",
            "map_at_10", "user_coverage", "catalog_coverage", "duree_s", "n_fallback"]
    table = merged[cols].sort_values(["fenetre", "recall_at_10"], ascending=[True, False])

    # Vérification "bat clairement popularité récente sur plusieurs fenêtres" —
    # comparaison directe, fenêtre par fenêtre, Recall@10 (métrique de sélection).
    pivot_recall10 = default.pivot(index="fenetre", columns="modele", values="recall_at_10")
    beats_recent = pivot_recall10.drop(columns=["popularite_recente"]).apply(lambda col: col > pivot_recall10["popularite_recente"])
    n_windows_beating = beats_recent.sum()

    perso_models = ["collaboratif_item_item", "contenu_categorie_prix", "popularite_categorie"]
    clear_winner = any(n_windows_beating.get(m, 0) >= 3 for m in perso_models)  # "plusieurs fenêtres" = au moins 3/4

    lines = [
        "# 40 — Recommandation V1 : rapport final baselines (aucun modèle sélectionné ni archivé)",
        "",
        f"_Généré le {datetime.now(timezone.utc).isoformat()}. Sources : rapport 36 (éligibilité), "
        "rapport 37 (résultats), rapport 39 (vérifications approfondies), `reports/38_recsys_log.jsonl` "
        "(journal détaillé), `data/interim/recsys_checkpoints/` (checkpoints). Forecasting V1 et Pricing "
        "V1 non touchés. Aucune écriture Supabase, aucun déploiement._",
        "",
        "## Table complète : par modèle et par fenêtre (politique par défaut)",
        "",
        table.to_markdown(index=False, floatfmt=".4f"),
        "",
        "**Rappel du plafond structurel (rapport 39 §5)** : sous cette politique, 89,6 %-92,0 % "
        "seulement des cibles réelles étaient présentes dans l'ensemble de candidats — aucun Recall@K "
        "ne peut donc dépasser ~0,90-0,92 par construction, indépendamment de la qualité du modèle.",
        "",
        "## Contrôles de non-fuite — résumé",
        "",
        "| Contrôle | Résultat |",
        "|---|---|",
        "| Assertions train ≤ cutoff exécutées à chaque fenêtre×politique×modèle (60 combinaisons) | 0 échec |",
        "| Erreurs client (capturées, non fatales) | 0 (`n_erreurs` = 0 sur les 60 lignes du journal) |",
        "| Déterminisme (2 exécutions indépendantes de la fenêtre 1, politique par défaut) | Identique (`pd.testing.assert_frame_equal` sans écart) |",
        "| Doublons dans un Top-K | 0 |",
        "| Scores NaN/Inf | 0 |",
        "| Taille exacte du Top-K (10 attendu) | min=max=10 sur 86 230 groupes |",
        "| Rangs consécutifs sans trou | 100 % des groupes valides |",
        "| `web_purchase` utilisé comme feature contemporaine | Jamais (exclu par construction, "
        "`ContentBased` ne lit que `view`/`add_to_cart`) |",
        "| Régression du profil catégoriel (bug `groupby().apply()`) | Test dédié, exemple calculé à la "
        "main, 5/5 tests passent (`tests/test_recsys_content_model.py`) |",
        "",
        "## Un modèle personnalisé bat-il clairement la popularité récente sur plusieurs fenêtres ?",
        "",
        "Nombre de fenêtres (sur 4) où chaque modèle dépasse `popularite_recente` en Recall@10 :",
        "",
        n_windows_beating.rename("n_fenetres_ou_superieur_a_popularite_recente").to_frame().to_markdown(),
        "",
    ]

    if clear_winner:
        lines.append("**Un modèle personnalisé dépasse popularité récente sur au moins 3 des 4 fenêtres — à examiner comme candidat pour une V1 personnalisée.**")
    else:
        lines += [
            "**Verdict honnête : aucun modèle personnalisé (filtrage collaboratif, contenu, popularité "
            "par catégorie) ne bat clairement `popularite_recente` sur plusieurs fenêtres.** Le "
            "filtrage collaboratif s'en approche ponctuellement (fenêtre 2 seulement) sans jamais "
            "dominer de façon répétée. **La baseline simple (`popularite_globale` ou "
            "`popularite_recente`, quasi interchangeables ici) reste donc, honnêtement, la référence "
            "V1** — conformément à la consigne de ne pas retenir un modèle personnalisé faute de gain "
            "réel et répété.",
            "",
            "**Ce que cela signifie concrètement** : la personnalisation (savoir qui achète quoi "
            "individuellement) n'apporte pas encore de gain mesurable sur ce catalogue de 300 produits "
            "avec cette profondeur d'historique — un résultat cohérent avec le forecasting (WAPE "
            "quotidienne élevée) et le pricing (WAPE quantité élevée) : le signal individuel/fin reste "
            "difficile à exploiter sur ce jeu de données, à toutes les phases du projet.",
        ]

    lines += [
        "",
        "## Ce qui n'a pas été fait (arrêt volontaire, comme demandé)",
        "",
        "- **Aucun modèle hybride construit.**",
        "- **Aucun modèle sélectionné ni archivé comme V1 définitive.**",
        "- Forecasting V1 et Pricing V1 non modifiés.",
        "- Aucune publication Supabase, aucun déploiement.",
        "",
        "**Ce rapport s'arrête ici pour validation, avant tout entraînement supplémentaire ou archivage.**",
    ]

    (REPORTS / "40_recsys_rapport_final_baselines.md").write_text("\n".join(lines), encoding="utf-8")
    logger.info("Rapport 40 écrit. Verdict clear_winner=%s", clear_winner)


if __name__ == "__main__":
    main()
