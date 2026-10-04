"""Decision tree and Gaussian Naive Bayes: P(post lands in its platform's top quartile) before publishing."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.naive_bayes import GaussianNB
from sklearn.pipeline import Pipeline
from sklearn.tree import DecisionTreeClassifier

from .common import (
    FEATURE_LABELS,
    NUMERIC,
    PRE_PUBLICATION_FEATURES,
    SEED,
    ModelOutcome,
    assert_no_leakage,
    chrono_split,
    classification_metrics,
    label_performance,
    platform_thresholds,
    preprocessor,
    term_group,
)

TREE_FEATURES = [f for f in PRE_PUBLICATION_FEATURES if f != "caption_length_sq"]


def _split(df: pd.DataFrame):
    train, test = chrono_split(df)
    thresholds = platform_thresholds(train)  # thresholds from the past only
    return label_performance(train, thresholds), label_performance(test, thresholds), thresholds


def _cond(col: str, thr: float, positive: bool) -> str:
    group, level = term_group(col)
    if level:  # one-hot column (threshold 0.5): right branch means the level is present
        return f"{FEATURE_LABELS.get(group, group)} {'is' if positive else 'is not'} {level}"
    label = FEATURE_LABELS.get(col, col)
    if col in ("has_cta", "has_question", "is_weekend"):
        return f"{label}: {'yes' if positive else 'no'}"
    return f"{label} {'>' if positive else '≤'} {thr:.0f}"


def _extract_rules(tree: DecisionTreeClassifier, names: list[str], base_rate: float) -> list[dict]:
    t = tree.tree_
    rules: list[dict] = []

    def walk(node: int, path: list[str]) -> None:
        if t.children_left[node] == t.children_right[node]:
            counts = t.value[node][0]
            n = int(t.n_node_samples[node])
            # class_weight="balanced" skews t.value; recover raw rate from weighted counts
            pos_share = float(counts[1] / counts.sum()) if counts.sum() else 0.0
            rules.append({"node": node, "conditions": path, "n_train": n, "weighted_positive_share": pos_share})
            return
        col, thr = names[t.feature[node]], float(t.threshold[node])
        walk(t.children_left[node], [*path, _cond(col, thr, positive=False)])
        walk(t.children_right[node], [*path, _cond(col, thr, positive=True)])

    walk(0, [])
    return rules


def _grouped_importance(names: list[str], values: np.ndarray) -> list[dict]:
    agg: dict[str, float] = {}
    for n, v in zip(names, values, strict=True):
        g, _ = term_group(n)
        agg[g] = agg.get(g, 0.0) + float(v)
    return sorted(
        ({"feature": g, "label": FEATURE_LABELS.get(g, g), "importance": v} for g, v in agg.items()),
        key=lambda r: -r["importance"],
    )


def decision_tree(df: pd.DataFrame) -> ModelOutcome:
    feats = TREE_FEATURES
    assert_no_leakage(feats)
    train, test, thresholds = _split(df)
    pipe = Pipeline([
        ("prep", preprocessor(scale=False, drop_first=False, numeric=[f for f in NUMERIC if f != "caption_length_sq"])),
        ("tree", DecisionTreeClassifier(max_depth=4, min_samples_leaf=20, class_weight="balanced", random_state=SEED)),
    ])
    pipe.fit(train[feats], train["high_performer"])
    prob = pipe.predict_proba(test[feats])[:, 1]
    pred = pipe.predict(test[feats])
    metrics = classification_metrics(test["high_performer"], pred, prob)
    names = list(pipe.named_steps["prep"].get_feature_names_out())
    tree = pipe.named_steps["tree"]

    # Leaf hit-rates on the *actual* training labels (unweighted), plus holdout confirmation.
    leaf_tr = tree.apply(pipe.named_steps["prep"].transform(train[feats]))
    leaf_te = tree.apply(pipe.named_steps["prep"].transform(test[feats]))
    base_rate = float(train["high_performer"].mean())
    raw_rules = _extract_rules(tree, names, base_rate)
    rules = []
    for rule in raw_rules:
        leaf = rule["node"]
        mask_tr, mask_te = leaf_tr == leaf, leaf_te == leaf
        n_tr, n_te = int(mask_tr.sum()), int(mask_te.sum())
        hit_tr = float(train.loc[mask_tr, "high_performer"].mean()) if n_tr else 0.0
        hit_te = float(test.loc[mask_te, "high_performer"].mean()) if n_te >= 5 else None
        rules.append({
            "conditions": rule["conditions"], "n_train": n_tr, "hit_rate_train": hit_tr,
            "lift_train": hit_tr / base_rate if base_rate else None, "n_test": n_te, "hit_rate_test": hit_te,
        })
    leaf_rates = {int(r["node"]): next(x["hit_rate_train"] for x in rules if x["conditions"] == r["conditions"]) for r in raw_rules}
    rules.sort(key=lambda r: -r["hit_rate_train"])
    results = {
        "rules": rules, "base_rate_train": base_rate, "depth": int(tree.get_depth()), "n_leaves": int(tree.get_n_leaves()),
        "feature_importance": _grouped_importance(names, tree.feature_importances_),
        "thresholds": thresholds,
        "target_definition": "High performer = engagement rate in the top quartile of its platform (threshold from training period).",
        "note": "Rules describe historical patterns, not causes.",
    }
    return ModelOutcome(
        "decision_tree", "classification", "high_performer", feats,
        {"max_depth": 4, "min_samples_leaf": 20, "class_weight": "balanced", "seed": SEED}, metrics, results,
        len(train), len(test), artifact={"pipeline": pipe, "features": feats, "thresholds": thresholds, "leaf_rates": leaf_rates},
    )


def gaussian_nb(df: pd.DataFrame) -> ModelOutcome:
    feats = PRE_PUBLICATION_FEATURES
    assert_no_leakage(feats)
    train, test, thresholds = _split(df)
    # Raw GNB probabilities are extreme (independence assumption); sigmoid calibration makes them usable.
    pipe = Pipeline([
        ("prep", preprocessor(scale=True, drop_first=False)),
        ("nb", CalibratedClassifierCV(GaussianNB(), method="sigmoid", cv=5)),
    ])
    pipe.fit(train[feats], train["high_performer"])
    prob = pipe.predict_proba(test[feats])[:, 1]
    pred = pipe.predict(test[feats])
    metrics = classification_metrics(test["high_performer"], pred, prob)
    # calibration check: mean predicted probability vs observed rate
    metrics["mean_predicted_probability"] = float(prob.mean())
    results = {
        "class_prior": {"not_high": float(1 - train["high_performer"].mean()), "high": float(train["high_performer"].mean())},
        "thresholds": thresholds,
        "note": "Gaussian Naive Bayes treats one-hot columns as Gaussian and assumes independent features. "
                "Its raw probabilities are over-confident, so they are sigmoid-calibrated (5-fold) before use.",
    }
    return ModelOutcome(
        "gaussian_nb", "classification", "high_performer", list(feats), {"base": "GaussianNB", "calibration": "sigmoid, 5-fold", "seed": SEED},
        metrics, results, len(train), len(test), artifact={"pipeline": pipe, "features": feats, "thresholds": thresholds},
    )
