"""Apriori association rules: which attribute combinations co-occur with top/bottom-quartile posts.

Frequent itemsets come from mlxtend. Rules are derived from the itemset supports,
tested with a one-sided Fisher exact test and Benjamini-Hochberg-adjusted, because
mining many candidate rules guarantees some look good by chance.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from mlxtend.frequent_patterns import apriori
from scipy.stats import fisher_exact

from .common import FEATURE_LABELS, ModelOutcome

MIN_SUPPORT = 0.03
MAX_LEN = 3
MIN_ANTECEDENT_POSTS = 12
MIN_LIFT = 1.2
FDR = 0.10


def _terciles(df: pd.DataFrame, col: str, names: tuple[str, str, str]) -> pd.Series:
    def f(s: pd.Series) -> pd.Series:
        lo, hi = s.quantile([1 / 3, 2 / 3])
        return s.apply(lambda v: names[0] if v <= lo else (names[2] if v > hi else names[1]))
    return df.groupby("platform")[col].transform(f)


def build_items(df: pd.DataFrame) -> pd.DataFrame:
    items = pd.DataFrame(index=df.index)
    for col in ("platform", "format", "topic", "hook", "tone", "daypart"):
        for level in df[col].unique():
            items[f"{col}={level}"] = df[col] == level
    items["caption=short"] = _terciles(df, "caption_length", ("short", "mid", "long")) == "short"
    items["caption=mid"] = _terciles(df, "caption_length", ("short", "mid", "long")) == "mid"
    items["caption=long"] = _terciles(df, "caption_length", ("short", "mid", "long")) == "long"
    items["hashtags=none"] = df["hashtag_count"] == 0
    items["hashtags=1-3"] = df["hashtag_count"].between(1, 3)
    items["hashtags=4+"] = df["hashtag_count"] >= 4
    items["has_question"] = df["has_question"] == 1
    items["has_cta"] = df["has_cta"] == 1
    items["weekend"] = df["is_weekend"].astype(bool)
    return items.astype(bool)


def _bh(p: np.ndarray) -> np.ndarray:
    n = len(p)
    order = np.argsort(p)
    ranked = p[order] * n / (np.arange(n) + 1)
    adj = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty(n)
    out[order] = np.minimum(adj, 1.0)
    return out


def _pretty(item: str) -> str:
    if "=" in item:
        k, v = item.split("=", 1)
        label = {"caption": "Caption length", "hashtags": "Hashtags", "hook": "Hook"}.get(k, FEATURE_LABELS.get(k, k.title()))
        return f"{label}: {v}"
    return {"has_question": "Has a question", "has_cta": "Has a call to action", "weekend": "Posted on weekend"}.get(item, item)


def apriori_rules(df: pd.DataFrame) -> ModelOutcome:
    items = build_items(df)
    n = len(df)
    outcomes = {"high_performer": df["high_performer"] == 1, "low_performer": df["low_performer"] == 1}
    candidates: list[dict] = []
    for outcome, mask in outcomes.items():
        data = items.copy()
        data[outcome] = mask.to_numpy()
        freq = apriori(data, min_support=MIN_SUPPORT, max_len=MAX_LEN, use_colnames=True)
        support = {frozenset(s): float(v) for s, v in zip(freq["itemsets"], freq["support"], strict=True)}
        base = float(mask.mean())
        for itemset, sup in support.items():
            if outcome not in itemset or len(itemset) < 2:
                continue
            ante = itemset - {outcome}
            if any(i in ("high_performer", "low_performer") for i in ante):
                continue
            sup_a = support.get(ante)
            if not sup_a:
                continue
            n_a = int(round(sup_a * n))
            hits = int(round(sup * n))
            if n_a < MIN_ANTECEDENT_POSTS:
                continue
            conf = hits / n_a
            lift = conf / base
            a_mask = items[list(ante)].all(axis=1).to_numpy()
            o = mask.to_numpy()
            table = [[int((a_mask & o).sum()), int((a_mask & ~o).sum())],
                     [int((~a_mask & o).sum()), int((~a_mask & ~o).sum())]]
            p = float(fisher_exact(table, alternative="greater")[1])
            candidates.append({
                "outcome": outcome, "antecedents": sorted(ante), "antecedent_labels": [_pretty(a) for a in sorted(ante)],
                "n_posts": n_a, "n_hits": hits, "support": float(sup), "confidence": float(conf),
                "base_rate": base, "lift": float(lift), "p_value": p,
            })
    if not candidates:
        return ModelOutcome("apriori", "association", None, [], {"min_support": MIN_SUPPORT}, {"candidate_rules": 0}, {"rules": []},
                            n, 0, status="insufficient_data", message="No frequent itemsets at the configured support threshold.")
    q = _bh(np.array([c["p_value"] for c in candidates]))
    for c, qv in zip(candidates, q, strict=True):
        c["q_value"] = float(qv)
        c["significant"] = bool(qv < FDR and c["lift"] >= MIN_LIFT)
    kept = [c for c in candidates if c["lift"] >= MIN_LIFT]
    kept.sort(key=lambda c: (not c["significant"], c["q_value"], -c["lift"]))
    top = {o: [c for c in kept if c["outcome"] == o][:20] for o in outcomes}
    return ModelOutcome(
        "apriori", "association", None, [k for k in items.columns],
        {"min_support": MIN_SUPPORT, "max_len": MAX_LEN, "min_antecedent_posts": MIN_ANTECEDENT_POSTS,
         "min_lift": MIN_LIFT, "fdr": FDR, "multiple_testing": "Benjamini-Hochberg"},
        {"candidate_rules": len(candidates), "rules_significant": sum(c["significant"] for c in kept), "n_posts": n},
        {"rules": top["high_performer"] + top["low_performer"],
         "note": "Rules show co-occurrence in history. 'Significant' means q < 0.10 after multiple-testing correction; it is still not proof of cause."},
        n, 0,
    )
