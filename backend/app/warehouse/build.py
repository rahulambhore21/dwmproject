"""Dimensional warehouse loader (staging `posts` -> star schema)."""
from __future__ import annotations

import pandas as pd
from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from ..etl.text import daypart, extract_text_features
from ..models import (
    DimDate,
    DimDaypart,
    DimFormat,
    DimHook,
    DimPlatform,
    DimTone,
    DimTopic,
    FactPost,
    Post,
)

_DIMS = {
    "platform": (DimPlatform, "platform"),
    "format": (DimFormat, "format"),
    "topic": (DimTopic, "topic"),
    "hook": (DimHook, "hook_type"),
    "tone": (DimTone, "tone"),
    "daypart": (DimDaypart, "daypart"),
}


def _ensure_dim(session: Session, model, names: set[str]) -> dict[str, int]:
    existing = {n: k for k, n in session.execute(select(model.key, model.name)).all()}
    missing = sorted(names - existing.keys())
    if missing:
        session.execute(insert(model), [{"name": n} for n in missing])
        session.flush()
        existing = {n: k for k, n in session.execute(select(model.key, model.name)).all()}
    return existing


def build_warehouse(session: Session, workspace_id: int) -> dict:
    """Idempotently rebuild dimensions and the fact table for one workspace."""
    posts = session.execute(select(Post).where(Post.workspace_id == workspace_id)).scalars().all()
    session.execute(delete(FactPost).where(FactPost.workspace_id == workspace_id))
    if not posts:
        session.flush()
        return {"fact_rows": 0, "dimensions": {}}

    rows = []
    for p in posts:
        tf = extract_text_features(p.caption)
        eng = p.likes + p.comments + p.shares + p.saves
        rows.append(dict(
            post_id=p.id, workspace_id=workspace_id, published_at=p.published_at, hour=p.published_at.hour,
            platform=p.platform, format=p.format, topic=p.topic, hook=p.hook_type, tone=p.tone,
            daypart=daypart(p.published_at.hour),
            caption_length=tf.caption_length, word_count=tf.word_count, hashtag_count=tf.hashtag_count,
            emoji_count=tf.emoji_count, has_cta=tf.has_cta, has_question=tf.has_question, media_count=p.media_count,
            impressions=p.impressions, reach=p.reach, likes=p.likes, comments=p.comments, shares=p.shares,
            saves=p.saves, engagements=eng, engagement_rate=eng / p.impressions,
            save_rate=p.saves / p.impressions, share_rate=p.shares / p.impressions,
            comment_rate=p.comments / p.impressions,
        ))
    df = pd.DataFrame(rows)

    keys: dict[str, dict[str, int]] = {}
    for col, (model, _) in _DIMS.items():
        keys[col] = _ensure_dim(session, model, set(df[col].unique()))

    dates = pd.to_datetime(df["published_at"]).dt.normalize().drop_duplicates()
    existing_dates = set(session.execute(select(DimDate.date_key)).scalars().all())
    new_dates = []
    for d in dates:
        dk = int(d.strftime("%Y%m%d"))
        if dk in existing_dates:
            continue
        new_dates.append(dict(
            date_key=dk, full_date=d.date(), year=d.year, quarter=(d.month - 1) // 3 + 1, month=d.month,
            month_label=d.strftime("%Y-%m"), iso_week=int(d.isocalendar().week), day_of_week=d.dayofweek,
            day_name=d.strftime("%a"), is_weekend=d.dayofweek >= 5,
        ))
    if new_dates:
        session.execute(insert(DimDate), new_dates)

    fact_rows = []
    for r in rows:
        fact_rows.append(dict(
            post_id=r["post_id"], workspace_id=workspace_id,
            date_key=int(r["published_at"].strftime("%Y%m%d")),
            platform_key=keys["platform"][r["platform"]], format_key=keys["format"][r["format"]],
            topic_key=keys["topic"][r["topic"]], hook_key=keys["hook"][r["hook"]], tone_key=keys["tone"][r["tone"]],
            daypart_key=keys["daypart"][r["daypart"]],
            **{k: r[k] for k in (
                "published_at", "hour", "caption_length", "word_count", "hashtag_count", "emoji_count", "has_cta",
                "has_question", "media_count", "impressions", "reach", "likes", "comments", "shares", "saves",
                "engagements", "engagement_rate", "save_rate", "share_rate", "comment_rate")},
        ))
    session.execute(insert(FactPost), fact_rows)
    session.flush()
    return {
        "fact_rows": len(fact_rows),
        "dimensions": {c: len(k) for c, k in keys.items()} | {"date": len(existing_dates) + len(new_dates)},
    }
