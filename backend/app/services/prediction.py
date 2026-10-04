"""Pre-publication prediction. Only attributes known before posting are used."""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field, field_validator
from scipy import stats
from sqlalchemy.orm import Session

from ..etl.text import daypart, extract_text_features
from ..ml.common import FEATURE_LABELS, PRE_PUBLICATION_FEATURES, assert_no_leakage, term_group
from ..ml.pipeline import latest_run, load_artifact
from .similarity import find_similar

Z80 = float(stats.norm.ppf(0.9))
DEFAULT_MEDIA = {"Carousel": 5, "Thread": 4}


class Draft(BaseModel):
    platform: str = Field(min_length=1, max_length=32)
    format: str = Field(min_length=1, max_length=32)
    topic: str = Field(min_length=1, max_length=64)
    hook: str = Field(min_length=1, max_length=32)
    tone: str = Field(min_length=1, max_length=32)
    caption: str = Field(min_length=1, max_length=5000)
    scheduled_at: datetime
    media_count: int | None = Field(default=None, ge=0, le=100)

    @field_validator("caption")
    @classmethod
    def _non_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("caption must not be blank")
        return v


def draft_frame(d: Draft) -> pd.DataFrame:
    tf = extract_text_features(d.caption)
    row = dict(
        platform=d.platform, format=d.format, topic=d.topic, hook=d.hook, tone=d.tone, daypart=daypart(d.scheduled_at.hour),
        caption_length=tf.caption_length, caption_length_sq=tf.caption_length**2 / 1000.0, hashtag_count=tf.hashtag_count,
        emoji_count=tf.emoji_count, media_count=d.media_count if d.media_count is not None else DEFAULT_MEDIA.get(d.format, 1),
        has_cta=int(tf.has_cta), has_question=int(tf.has_question), is_weekend=int(d.scheduled_at.weekday() >= 5),
    )
    return pd.DataFrame([row])[PRE_PUBLICATION_FEATURES]


def vocabulary(frame: pd.DataFrame) -> dict:
    out: dict = {"platforms": {}, "topics": [], "hooks": [], "tones": [], "dayparts": []}
    if frame.empty:
        return out
    for p, g in frame.groupby("platform"):
        counts = g["format"].value_counts()
        out["platforms"][p] = {"formats": [{"name": f, "n": int(c)} for f, c in counts.items()], "n": int(len(g)),
                               "median_engagement_rate": float(g["engagement_rate"].median())}
    for key, col in (("topics", "topic"), ("hooks", "hook"), ("tones", "tone")):
        out[key] = sorted(frame[col].unique())
    return out


def _check_known(frame: pd.DataFrame, d: Draft) -> list[str]:
    problems = []
    for col, val in (("platform", d.platform), ("topic", d.topic), ("hook", d.hook), ("tone", d.tone), ("format", d.format)):
        if val not in set(frame[col]):
            problems.append(f"Unknown {col} '{val}'. Known: {', '.join(sorted(frame[col].unique()))}")
    return problems


def _predict_log(artifact, X: pd.DataFrame) -> float:
    return float(artifact["pipeline"].predict(X)[0])


def _contributions(artifact, X: pd.DataFrame) -> list[dict]:
    """Per-feature log-effect of this draft relative to the average training post."""
    pipe = artifact["pipeline"]
    prep, lr = pipe.named_steps["prep"], pipe.named_steps["lr"]
    names = artifact["feature_names"]
    means = np.array([artifact["results"]["train_column_means"][n] for n in names])
    xt = prep.transform(X)[0]
    parts = lr.coef_ * (xt - means)
    groups: dict[str, float] = {}
    for n, v in zip(names, parts, strict=True):
        g, _ = term_group(n)
        g = "caption_length" if g == "caption_length_sq" else g
        groups[g] = groups.get(g, 0.0) + float(v)
    row = X.iloc[0]
    out = []
    for g, v in groups.items():
        if g == "platform":
            continue  # platform baseline is shown separately; contributions are within-platform
        if g in ("hashtag_count", "emoji_count", "media_count"):
            shown = str(int(row[g]))
        elif g in ("has_cta", "has_question", "is_weekend"):
            shown = "yes" if row[g] else "no"
        elif g == "caption_length":
            shown = f"{int(row['caption_length'])} chars"
        else:
            shown = str(row[g])
        out.append({"feature": g, "label": FEATURE_LABELS.get(g, g), "value": shown, "log_effect": v,
                    "effect_pct": float(np.expm1(v) * 100)})
    return sorted(out, key=lambda c: -abs(c["log_effect"]))


def _prob(run_artifact, X: pd.DataFrame) -> float | None:
    if not run_artifact:
        return None
    pipe, feats = run_artifact["pipeline"], run_artifact["features"]
    if "leaf_rates" in run_artifact:  # tree: observed training hit rate of the matching leaf (unweighted)
        leaf = int(pipe.named_steps["tree"].apply(pipe.named_steps["prep"].transform(X[feats]))[0])
        return float(run_artifact["leaf_rates"][leaf])
    return float(pipe.predict_proba(X[feats])[:, 1][0])


def predict(session: Session, workspace_id: int, frame: pd.DataFrame, d: Draft, *, with_similar: bool = True,
            with_whatif: bool = True) -> dict:
    mlr_run = latest_run(session, workspace_id, "multiple_linear_regression")
    if mlr_run is None or mlr_run.status != "ok":
        return {"status": "insufficient_data",
                "message": (mlr_run.message if mlr_run else None) or "Models have not been trained yet.",
                "prediction": None}
    problems = _check_known(frame, d)
    if problems:
        return {"status": "invalid", "message": "; ".join(problems), "prediction": None}
    assert_no_leakage(PRE_PUBLICATION_FEATURES)

    art = load_artifact(mlr_run)
    X = draft_frame(d)
    pred_log = _predict_log(art, X)
    sd = float(mlr_run.metrics["interval_sd_log"])
    plat = frame[frame["platform"] == d.platform]["engagement_rate"]
    plat_median = float(plat.median())
    er = float(np.exp(pred_log))
    seg_n = int(((frame["platform"] == d.platform) & (frame["format"] == d.format)).sum())

    dt_run, nb_run = latest_run(session, workspace_id, "decision_tree"), latest_run(session, workspace_id, "gaussian_nb")
    p_dt = _prob(load_artifact(dt_run), X) if dt_run and dt_run.status == "ok" else None
    p_nb = _prob(load_artifact(nb_run), X) if nb_run and nb_run.status == "ok" else None
    probs = [p for p in (p_dt, p_nb) if p is not None]

    caveats = [
        "Model estimate from historical associations, not a guarantee.",
        f"Typical error on unseen recent posts: ±{(np.exp(sd) - 1) * 100:.0f}% (1 SD, log scale).",
    ]
    if seg_n < 15:
        caveats.append(f"Only {seg_n} past {d.platform} {d.format} posts: this combination is thinly covered.")
    adj = mlr_run.metrics.get("r2_platform_adjusted")
    if adj is not None and adj < 0.1:
        caveats.append("Within a platform the model explains little of the variation; treat differences as weak signals.")

    result = {
        "status": "ok", "message": None,
        "prediction": {
            "engagement_rate": er, "interval_80": [float(np.exp(pred_log - Z80 * sd)), float(np.exp(pred_log + Z80 * sd))],
            "platform_median_engagement_rate": plat_median, "vs_platform_median_pct": float((er / plat_median - 1) * 100),
            "probability_top_quartile": {"decision_tree": p_dt, "gaussian_nb": p_nb,
                                         "blend": float(np.mean(probs)) if probs else None, "base_rate": 0.25},
            "contributions": _contributions(art, X),
            "features": {k: (v.item() if hasattr(v, "item") else v) for k, v in X.iloc[0].to_dict().items()},
        },
        "model": {
            "run_id": mlr_run.id, "algorithm": "multiple_linear_regression", "trained_at": mlr_run.created_at.isoformat(),
            "n_train": mlr_run.n_train, "n_test": mlr_run.n_test, "holdout_r2": mlr_run.metrics["r2"],
            "r2_platform_adjusted": adj, "baseline_r2": mlr_run.metrics["baseline_r2"],
        },
        "caveats": caveats, "similar": None, "what_if": [],
    }
    if with_similar:
        result["similar"] = find_similar(
            session, workspace_id, frame, caption=d.caption,
            attrs={"platform": d.platform, "format": d.format, "topic": d.topic, "hook": d.hook, "tone": d.tone})
    if with_whatif:
        result["what_if"] = what_if(art, frame, d, pred_log)
    return result


def what_if(art, frame: pd.DataFrame, d: Draft, base_log: float) -> list[dict]:
    """Model-estimated change from swapping one attribute, only where history supports the alternative."""
    out = []
    plat = frame[frame["platform"] == d.platform]

    def consider(feature: str, label: str, new_value: str, X_alt: pd.DataFrame, n_support: int, change: str) -> None:
        if n_support < 8:
            return
        delta = _predict_log(art, X_alt) - base_log
        pct = float(np.expm1(delta) * 100)
        if abs(pct) >= 3:
            out.append({"feature": feature, "label": label, "change": change, "value": new_value,
                        "estimated_change_pct": pct, "supporting_posts": int(n_support)})

    base_X = draft_frame(d)
    for col, feat in (("hook", "hook"), ("format", "format"), ("tone", "tone")):
        cur = getattr(d, feat)
        for val in sorted(plat[col].unique()):
            if val == cur:
                continue
            X = base_X.copy()
            X[col] = val
            consider(feat, FEATURE_LABELS[col], val, X, int((plat[col] == val).sum()), f"{cur} → {val}")
    for dp in sorted(plat["daypart"].unique()):
        if dp == daypart(d.scheduled_at.hour):
            continue
        X = base_X.copy()
        X["daypart"] = dp
        consider("daypart", "Time of day", dp, X, int((plat["daypart"] == dp).sum()), f"{daypart(d.scheduled_at.hour)} → {dp}")
    for flag, label in (("has_question", "Question in caption"), ("has_cta", "Call to action")):
        X = base_X.copy()
        X[flag] = 1 - int(base_X[flag].iloc[0])
        want = int(X[flag].iloc[0])
        consider(flag, label, "add" if want else "remove", X, int((plat[flag] == want).sum()),
                 f"{'Add' if want else 'Remove'} {label.lower()}")
    out.sort(key=lambda r: -r["estimated_change_pct"])
    return [r for r in out if r["estimated_change_pct"] > 0][:5]
