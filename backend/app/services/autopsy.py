"""Content Autopsy: why did this post perform the way it did? (associations, not causes)"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats
from sqlalchemy.orm import Session

from ..ml.common import prepare
from ..ml.pipeline import latest_run, load_artifact
from ..models import Post, PostLabel
from .common import ApiError, pct_rank
from .prediction import Draft, _contributions, draft_frame
from .similarity import find_similar

MIN_SEGMENT = 8


def _segment_lift(plat: pd.DataFrame, col: str, value, own_er: float) -> dict | None:
    """Mean ER of same-platform posts sharing this attribute vs same-platform posts without it."""
    mask = plat[col] == value
    n_with, n_without = int(mask.sum()), int((~mask).sum())
    if n_with < MIN_SEGMENT or n_without < MIN_SEGMENT:
        return None
    a, b = plat.loc[mask, "engagement_rate"].to_numpy(), plat.loc[~mask, "engagement_rate"].to_numpy()
    test = stats.ttest_ind(a, b, equal_var=False)
    return {"n_with": n_with, "n_without": n_without, "mean_with": float(a.mean()), "mean_without": float(b.mean()),
            "lift_pct": float((a.mean() / b.mean() - 1) * 100), "p_value": float(test.pvalue)}


def build_autopsy(session: Session, workspace_id: int, frame: pd.DataFrame, post_id: int) -> dict:
    row_df = frame[frame["post_id"] == post_id]
    if row_df.empty:
        raise ApiError(404, "post_not_found", f"Post {post_id} not found.")
    r = row_df.iloc[0]
    post = session.get(Post, post_id)
    plat = frame[frame["platform"] == r["platform"]]
    seg = plat[plat["format"] == r["format"]]
    own_er = float(r["engagement_rate"])
    plat_median = float(plat["engagement_rate"].median())

    benchmark = {
        "platform_median_engagement_rate": plat_median, "platform_n": int(len(plat)),
        "platform_percentile": pct_rank(plat["engagement_rate"], own_er),
        "format_median_engagement_rate": float(seg["engagement_rate"].median()), "format_n": int(len(seg)),
        "format_percentile": pct_rank(seg["engagement_rate"], own_er),
        "performance_index": own_er / plat_median,
    }
    mix = []
    for label, col in (("Save rate", "save_rate"), ("Share rate", "share_rate"), ("Comment rate", "comment_rate")):
        med = float(plat[col].median())
        mix.append({"label": label, "value": float(r[col]), "platform_median": med,
                    "vs_median_pct": float((r[col] / med - 1) * 100) if med > 0 else None})
    mix.append({"label": "Impressions", "value": float(r["impressions"]), "platform_median": float(plat["impressions"].median()),
                "vs_median_pct": float((r["impressions"] / plat["impressions"].median() - 1) * 100)})

    # Attribute evidence: for each attribute this post has, how did same-platform posts with it perform?
    attribute_evidence = []
    for col, label in (("format", "Format"), ("hook", "Hook"), ("tone", "Tone"), ("topic", "Topic"), ("daypart", "Time of day")):
        lift = _segment_lift(plat, col, r[col], own_er)
        attribute_evidence.append({"attribute": label, "value": str(r[col]), "evidence": lift})
    for col, label, flag in (("has_question", "Question in caption", bool(r["has_question"])),
                             ("has_cta", "Call to action", bool(r["has_cta"]))):
        lift = _segment_lift(plat, col, int(flag), own_er)
        attribute_evidence.append({"attribute": label, "value": "yes" if flag else "no", "evidence": lift})

    # Model check (honest about whether the model had seen this post)
    model_check = None
    mlr = latest_run(session, workspace_id, "multiple_linear_regression")
    if mlr and mlr.status == "ok":
        art = load_artifact(mlr)
        d = Draft(platform=r["platform"], format=r["format"], topic=r["topic"], hook=r["hook"], tone=r["tone"],
                  caption=post.caption if post else "-", scheduled_at=r["published_at"].to_pydatetime(),
                  media_count=int(r["media_count"]))
        X = draft_frame(d)
        pred = float(np.exp(art["pipeline"].predict(X)[0]))
        order = prepare(frame)[["post_id"]].reset_index(drop=True)
        rank = int(order.index[order["post_id"] == post_id][0])
        holdout = rank >= mlr.n_train
        model_check = {
            "predicted_engagement_rate": pred, "actual_engagement_rate": own_er, "ratio_actual_to_predicted": own_er / pred,
            "split": "holdout" if holdout else "training",
            "note": ("The model had not seen this post when it was trained, so this is a fair out-of-sample check."
                     if holdout else "This post was part of the model's training period, so the fit is optimistic."),
            "contributions": _contributions(art, X)[:6],
        }

    label_row = session.get(PostLabel, post_id)
    archetype = None
    if label_row:
        km = latest_run(session, workspace_id, "kmeans")
        if km and km.status == "ok":
            cl = next((c for c in km.results["clusters"] if c["id"] == label_row.archetype), None)
            if cl:
                archetype = {"id": cl["id"], "name": cl["name"], "share": cl["share"], "n": cl["n"],
                             "mean_engagement_rate": cl["mean_engagement_rate"]}

    similar = find_similar(
        session, workspace_id, frame, caption=post.caption if post else "",
        attrs={"platform": r["platform"], "format": r["format"], "topic": r["topic"], "hook": r["hook"], "tone": r["tone"]},
        k=5, exclude_post_id=post_id)

    return {
        "post": {
            "id": int(r["post_id"]), "external_id": post.external_id if post else None, "platform": r["platform"],
            "format": r["format"], "topic": r["topic"], "hook": r["hook"], "tone": r["tone"], "daypart": r["daypart"],
            "published_at": r["published_at"].isoformat(), "caption": post.caption if post else "",
            "caption_length": int(r["caption_length"]), "hashtag_count": int(r["hashtag_count"]),
            "emoji_count": int(r["emoji_count"]), "has_cta": bool(r["has_cta"]), "has_question": bool(r["has_question"]),
            "media_count": int(r["media_count"]),
            "metrics": {k: int(r[k]) for k in ("impressions", "reach", "likes", "comments", "shares", "saves", "engagements")}
                       | {"engagement_rate": own_er},
        },
        "benchmark": benchmark, "engagement_mix": mix, "attribute_evidence": attribute_evidence,
        "model_check": model_check, "archetype": archetype, "similar": similar,
        "caveat": "These are associations in this workspace's history. A single post cannot show which attribute caused its result.",
    }


def list_posts(frame: pd.DataFrame, *, q: dict) -> dict:
    """Filter/sort/paginate Content Memory."""
    df = frame
    for col in ("platform", "format", "topic", "hook", "tone"):
        if q.get(col):
            df = df[df[col] == q[col]]
    if q.get("search"):
        s = q["search"].lower()
        df = df[df["caption"].str.lower().str.contains(s, regex=False)]
    plat_median = frame.groupby("platform")["engagement_rate"].transform("median")
    df = df.assign(perf_index=(frame["engagement_rate"] / plat_median).reindex(df.index))
    sort = q.get("sort", "published_at")
    asc = q.get("order", "desc") == "asc"
    df = df.sort_values(sort, ascending=asc, kind="stable")
    total = len(df)
    page, size = q.get("page", 1), q.get("page_size", 25)
    sl = df.iloc[(page - 1) * size: page * size]
    return {
        "total": int(total), "page": page, "page_size": size,
        "items": [{
            "post_id": int(x.post_id), "platform": x.platform, "format": x.format, "topic": x.topic, "hook": x.hook,
            "tone": x.tone, "published_at": x.published_at.isoformat(), "caption_preview": (x.caption or "")[:160],
            "impressions": int(x.impressions), "engagements": int(x.engagements),
            "engagement_rate": float(x.engagement_rate), "performance_index": float(x.perf_index),
        } for x in sl.itertuples()],
    }
