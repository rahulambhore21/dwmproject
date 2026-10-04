"""Shared ML contracts: feature sets, leakage guard, targets and chronological split."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
    roc_auc_score,
)
from sklearn.preprocessing import OneHotEncoder, StandardScaler

SEED = 42

# ----- features that exist BEFORE a post is published -----------------------
CATEGORICAL = ["platform", "format", "topic", "hook", "tone", "daypart"]
NUMERIC = ["caption_length", "caption_length_sq", "hashtag_count", "emoji_count", "media_count",
           "has_cta", "has_question", "is_weekend"]
PRE_PUBLICATION_FEATURES = CATEGORICAL + NUMERIC

# ----- anything observed AFTER publication: never a predictive feature ------
POST_PUBLICATION = {
    "impressions", "reach", "likes", "comments", "shares", "saves", "engagements",
    "engagement_rate", "save_rate", "share_rate", "comment_rate", "log_er", "rel_log_er",
    "high_performer", "low_performer", "archetype", "likes_count", "comments_count", "shares_count", "saves_count",
}

FEATURE_LABELS = {
    "platform": "Platform", "format": "Format", "topic": "Topic", "hook": "Hook type", "tone": "Tone",
    "daypart": "Time of day", "caption_length": "Caption length", "caption_length_sq": "Caption length (curve)",
    "hashtag_count": "Hashtags", "emoji_count": "Emoji", "media_count": "Media items", "has_cta": "Call to action",
    "has_question": "Question in caption", "is_weekend": "Weekend",
}


class LeakageError(ValueError):
    """Raised when a post-publication field is used as a pre-publication feature."""


def assert_no_leakage(features: list[str]) -> None:
    bad = sorted(set(features) & POST_PUBLICATION)
    if bad:
        raise LeakageError(f"Post-publication fields cannot be used as features: {bad}")
    unknown = sorted(set(features) - set(PRE_PUBLICATION_FEATURES) - {"caption_length"})
    if unknown:
        raise LeakageError(f"Unknown / unapproved features: {unknown}")


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    out = df.sort_values(["published_at", "post_id"]).reset_index(drop=True).copy()
    out["caption_length_sq"] = out["caption_length"].astype(float) ** 2 / 1000.0
    out["is_weekend"] = out["is_weekend"].astype(int)
    out["log_er"] = np.log(out["engagement_rate"].clip(lower=1e-5))
    out["rel_log_er"] = out["log_er"] - out.groupby("platform")["log_er"].transform("mean")
    return out


def chrono_split(df: pd.DataFrame, frac: float = 0.8) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Train on the past, test on the future. No shuffling, so no temporal leakage."""
    cut = int(len(df) * frac)
    return df.iloc[:cut].copy(), df.iloc[cut:].copy()


def platform_thresholds(train: pd.DataFrame) -> dict[str, dict[str, float]]:
    g = train.groupby("platform")["engagement_rate"]
    return {p: {"high": float(g.quantile(0.75)[p]), "low": float(g.quantile(0.25)[p])} for p in g.groups}


def label_performance(df: pd.DataFrame, thresholds: dict) -> pd.DataFrame:
    out = df.copy()
    hi = out["platform"].map(lambda p: thresholds.get(p, {}).get("high", np.nan))
    lo = out["platform"].map(lambda p: thresholds.get(p, {}).get("low", np.nan))
    out["high_performer"] = (out["engagement_rate"] >= hi).astype(int)
    out["low_performer"] = (out["engagement_rate"] <= lo).astype(int)
    return out


def preprocessor(*, scale: bool, drop_first: bool, numeric: list[str] | None = None) -> ColumnTransformer:
    cat = OneHotEncoder(drop="first" if drop_first else None, handle_unknown="ignore", sparse_output=False)
    num = StandardScaler() if scale else "passthrough"
    return ColumnTransformer(
        [("cat", cat, CATEGORICAL), ("num", num, numeric or NUMERIC)], verbose_feature_names_out=False
    )


def term_group(name: str) -> tuple[str, str]:
    """Map a transformed column name back to (feature, level)."""
    for c in CATEGORICAL:
        if name.startswith(c + "_"):
            return c, name[len(c) + 1:]
    return name, ""


def regression_metrics(y_true, y_pred) -> dict:
    y_true, y_pred = np.asarray(y_true), np.asarray(y_pred)
    return {
        "r2": float(r2_score(y_true, y_pred)),
        "rmse_log": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "mae_log": float(mean_absolute_error(y_true, y_pred)),
        "mae_engagement_rate": float(mean_absolute_error(np.exp(y_true), np.exp(y_pred))),
    }


def classification_metrics(y_true, y_pred, y_prob) -> dict:
    y_true = np.asarray(y_true)
    out = {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "baseline_accuracy": float(max(y_true.mean(), 1 - y_true.mean())),
        "positive_rate_test": float(y_true.mean()),
    }
    out["roc_auc"] = float(roc_auc_score(y_true, y_prob)) if len(np.unique(y_true)) == 2 else None
    return out


@dataclass
class ModelOutcome:
    """What a trainer returns; the pipeline persists it as a ModelRun."""

    algorithm: str
    task: str
    target: str | None
    features: list[str]
    params: dict
    metrics: dict
    results: dict
    n_train: int
    n_test: int
    artifact: object | None = None
    status: str = "ok"
    message: str | None = None
