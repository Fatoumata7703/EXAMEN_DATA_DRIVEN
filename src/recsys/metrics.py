"""Métriques de recommandation — Top-K évalué contre les achats futurs
réellement observés (jamais un split aléatoire)."""

from __future__ import annotations

import numpy as np
import pandas as pd


def precision_at_k(recommended: list[str], relevant: set[str], k: int) -> float:
    topk = recommended[:k]
    if not topk:
        return 0.0
    hits = sum(1 for p in topk if p in relevant)
    return hits / len(topk)


def recall_at_k(recommended: list[str], relevant: set[str], k: int) -> float | None:
    if not relevant:
        return None
    topk = recommended[:k]
    hits = sum(1 for p in topk if p in relevant)
    return hits / len(relevant)


def ndcg_at_k(recommended: list[str], relevant: set[str], k: int) -> float | None:
    if not relevant:
        return None
    topk = recommended[:k]
    dcg = sum(1.0 / np.log2(i + 2) for i, p in enumerate(topk) if p in relevant)
    idcg = sum(1.0 / np.log2(i + 2) for i in range(min(len(relevant), k)))
    return dcg / idcg if idcg > 0 else 0.0


def average_precision_at_k(recommended: list[str], relevant: set[str], k: int = 10) -> float | None:
    if not relevant:
        return None
    topk = recommended[:k]
    hits, score = 0, 0.0
    for i, p in enumerate(topk):
        if p in relevant:
            hits += 1
            score += hits / (i + 1)
    m = min(len(relevant), k)
    return score / m if m > 0 else 0.0


def catalog_coverage(all_recommendations: list[list[str]], candidate_universe: set[str]) -> float:
    recommended_union = set()
    for rec in all_recommendations:
        recommended_union.update(rec)
    return len(recommended_union) / max(len(candidate_universe), 1)


def intra_list_category_diversity(recommended: list[str], produit_categorie: dict[str, str]) -> float | None:
    if not recommended:
        return None
    cats = [produit_categorie.get(p) for p in recommended if p in produit_categorie]
    if not cats:
        return None
    return len(set(cats)) / len(cats)


def evaluate_recommendations(
    recs_by_client: dict[str, list[str]], relevant_by_client: dict[str, set[str]],
    produit_categorie: dict[str, str], candidate_universe: set[str], k_list: list[int] = (5, 10),
) -> dict:
    rows = []
    for client_id, relevant in relevant_by_client.items():
        recs = recs_by_client.get(client_id, [])
        row = {"client_id": client_id, "n_relevant": len(relevant), "n_recommended": len(recs)}
        for k in k_list:
            row[f"precision_at_{k}"] = precision_at_k(recs, relevant, k)
            row[f"recall_at_{k}"] = recall_at_k(recs, relevant, k)
            row[f"ndcg_at_{k}"] = ndcg_at_k(recs, relevant, k)
        row["map_at_10"] = average_precision_at_k(recs, relevant, 10)
        row["diversity_at_10"] = intra_list_category_diversity(recs[:10], produit_categorie)
        rows.append(row)
    per_client = pd.DataFrame(rows)

    n_evaluable = len(relevant_by_client)
    n_with_recs = sum(1 for c in relevant_by_client if len(recs_by_client.get(c, [])) > 0)
    user_coverage = n_with_recs / max(n_evaluable, 1)
    cat_coverage = catalog_coverage([recs_by_client.get(c, []) for c in relevant_by_client], candidate_universe)

    summary = {"user_coverage": user_coverage, "catalog_coverage": cat_coverage, "n_evaluable": n_evaluable}
    for k in k_list:
        summary[f"precision_at_{k}"] = per_client[f"precision_at_{k}"].mean()
        summary[f"recall_at_{k}"] = per_client[f"recall_at_{k}"].dropna().mean()
        summary[f"ndcg_at_{k}"] = per_client[f"ndcg_at_{k}"].dropna().mean()
    summary["map_at_10"] = per_client["map_at_10"].dropna().mean()
    summary["diversity_at_10"] = per_client["diversity_at_10"].dropna().mean()
    return {"per_client": per_client, "summary": summary}
