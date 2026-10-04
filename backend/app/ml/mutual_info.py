"""Mutual information between content attributes and platform-adjusted performance.

Exploratory (whole history, not a predictive evaluation). A label-shuffle null
distribution gives a noise floor so tiny MI values are not over-read.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.feature_selection import mutual_info_classif, mutual_info_regression
from sklearn.preprocessing import OrdinalEncoder

from .common import CATEGORICAL, FEATURE_LABELS, SEED, ModelOutcome, assert_no_leakage

MI_FEATURES = [
    "platform", "format", "topic", "hook", "tone", "daypart", "caption_length", "hashtag_count",
    "emoji_count", "has_cta", "has_question", "is_weekend",
]
N_SHUFFLES = 20


def _mi(X: np.ndarray, y: np.ndarray, discrete: np.ndarray, classify: bool) -> np.ndarray:
    fn = mutual_info_classif if classify else mutual_info_regression
    return fn(X, y, discrete_features=discrete, n_neighbors=5, random_state=SEED)


def mutual_information(df: pd.DataFrame) -> ModelOutcome:
    assert_no_leakage(MI_FEATURES)
    X = df[MI_FEATURES].copy()
    X[CATEGORICAL] = OrdinalEncoder().fit_transform(X[CATEGORICAL])
    Xv = X.to_numpy(dtype=float)
    discrete = np.array([f not in ("caption_length",) for f in MI_FEATURES])
    y_reg = df["rel_log_er"].to_numpy()
    y_cls = df["high_performer"].to_numpy()

    mi_reg = _mi(Xv, y_reg, discrete, classify=False)
    mi_cls = _mi(Xv, y_cls, discrete, classify=True)

    rng = np.random.default_rng(SEED)
    null_reg = np.empty((N_SHUFFLES, len(MI_FEATURES)))
    null_cls = np.empty_like(null_reg)
    for i in range(N_SHUFFLES):
        perm = rng.permutation(len(df))
        null_reg[i] = _mi(Xv, y_reg[perm], discrete, classify=False)
        null_cls[i] = _mi(Xv, y_cls[perm], discrete, classify=True)
    floor_reg = np.quantile(null_reg, 0.95, axis=0)
    floor_cls = np.quantile(null_cls, 0.95, axis=0)

    rows = []
    for i, f in enumerate(MI_FEATURES):
        rows.append({
            "feature": f, "label": FEATURE_LABELS.get(f, f),
            "mi_performance_index": float(mi_reg[i]), "noise_floor_performance_index": float(floor_reg[i]),
            "mi_high_performer": float(mi_cls[i]), "noise_floor_high_performer": float(floor_cls[i]),
            "above_noise": bool(mi_reg[i] > floor_reg[i] or mi_cls[i] > floor_cls[i]),
        })
    rows.sort(key=lambda r: -(r["mi_performance_index"] - r["noise_floor_performance_index"]))
    n_above = sum(r["above_noise"] for r in rows)
    return ModelOutcome(
        "mutual_information", "ranking", "platform_adjusted_log_er", MI_FEATURES,
        {"n_neighbors": 5, "noise_shuffles": N_SHUFFLES, "noise_quantile": 0.95, "seed": SEED},
        {"features_ranked": len(rows), "features_above_noise": n_above, "n_posts": len(df)},
        {"ranking": rows, "note": "MI measures statistical dependence (any shape), not cause and effect. "
                                  "Target is engagement rate relative to the platform's average."},
        len(df), 0,
    )
