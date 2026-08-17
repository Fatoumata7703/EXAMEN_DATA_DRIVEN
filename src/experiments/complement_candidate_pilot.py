from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from src.config.settings import PROJECT_ROOT

ROOT = PROJECT_ROOT / "data" / "processed" / "final"
OUT = PROJECT_ROOT / "models" / "advanced" / "recommendation_ranking"


def cooccurrence(frame: pd.DataFrame) -> dict[str, Counter]:
    result = defaultdict(Counter)
    for _, group in frame.groupby("order_id"):
        items = list(dict.fromkeys(group.produit_key))
        for item in items:
            result[item].update(other for other in items if other != item)
    return result


def main() -> None:
    orders = pd.read_parquet(ROOT / "order_baskets.parquet"); orders.date_commande = pd.to_datetime(orders.date_commande)
    multi = orders.groupby("order_id").filter(lambda x: x.produit_key.nunique() >= 2)
    dates = multi.groupby("order_id").date_commande.min().sort_values(); chunks = np.array_split(dates.index.to_numpy(), 4)
    rows = []
    for window, ids in enumerate(chunks, 1):
        test_ids = set(ids.tolist()); test = multi[multi.order_id.isin(test_ids)]; train = multi[~multi.order_id.isin(test_ids) & multi.date_commande.lt(test.date_commande.min())]
        co = cooccurrence(train); global_pop = Counter(train.produit_key); category_pop = {cat: Counter(g.produit_key) for cat, g in train.groupby("categorie")}
        hits = {"cooccurrence_item_item": 0, "association_support_confidence_lift": 0, "bm25_panier": 0, "popularite_categorie": 0}; n = 0
        for _, group in test.groupby("order_id"):
            context = set(group.produit_key)
            for target in context:
                n += 1
                observed_context = context - {target}
                scores = Counter()
                for item in observed_context:
                    scores.update(co.get(item, Counter()))
                ranked = [x for x, _ in scores.most_common() if x not in observed_context]
                hits["cooccurrence_item_item"] += int(target in ranked[:50])
                # Association proxy: co-occurrence count / item support (confidence/lift proxy).
                assoc = Counter({x: c / max(global_pop[x], 1) for x, c in scores.items()})
                ranked_assoc = [x for x, _ in assoc.most_common() if x not in observed_context]
                hits["association_support_confidence_lift"] += int(target in ranked_assoc[:50])
                # BM25-like damped co-occurrence score.
                bm = Counter({x: c / (1.0 + np.log1p(global_pop[x])) for x, c in scores.items()})
                ranked_bm = [x for x, _ in bm.most_common() if x not in observed_context]
                hits["bm25_panier"] += int(target in ranked_bm[:50])
                cat = group.loc[group.produit_key.eq(target), "categorie"].iloc[0]
                ranked_cat = [x for x, _ in category_pop.get(cat, Counter()).most_common(50) if x not in observed_context]
                hits["popularite_categorie"] += int(target in ranked_cat[:50])
        for model, hit in hits.items():
            rows.append({"scenario": "complement_panier", "window": window, "model": model, "n_orders": len(test_ids), "n_targets": n, "candidate_recall_at50": hit / max(n, 1)})
    out = pd.DataFrame(rows); out.to_csv(OUT / "complement_candidate_metrics.csv", index=False)
    summary = out.groupby("model", as_index=False).candidate_recall_at50.mean(); gate = bool(summary.candidate_recall_at50.max() >= .50)
    payload = {"metrics": out.to_dict("records"), "summary": summary.to_dict("records"), "candidate_gate_ge_050": gate, "lambda_rank_started": False}
    (OUT / "complement_candidate_metadata.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    manifest = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.glob("*") if p.is_file() and p.name != "manifest.sha256.json"}; (OUT / "complement_manifest.sha256.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


if __name__ == "__main__": main()
