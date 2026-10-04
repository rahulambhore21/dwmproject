"""Read the star schema back into an analysis-ready DataFrame."""
from __future__ import annotations

import hashlib

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

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


def load_fact_frame(session: Session, workspace_id: int) -> pd.DataFrame:
    f = FactPost
    stmt = (
        select(
            f.post_id, f.published_at, f.hour, Post.caption,
            DimPlatform.name.label("platform"), DimFormat.name.label("format"), DimTopic.name.label("topic"),
            DimHook.name.label("hook"), DimTone.name.label("tone"), DimDaypart.name.label("daypart"),
            DimDate.full_date.label("date"), DimDate.year, DimDate.quarter, DimDate.month_label.label("month"),
            DimDate.iso_week.label("week"), DimDate.day_of_week, DimDate.day_name.label("weekday"), DimDate.is_weekend,
            f.caption_length, f.word_count, f.hashtag_count, f.emoji_count, f.has_cta, f.has_question, f.media_count,
            f.impressions, f.reach, f.likes, f.comments, f.shares, f.saves, f.engagements,
            f.engagement_rate, f.save_rate, f.share_rate, f.comment_rate,
        )
        .join(Post, Post.id == f.post_id)
        .join(DimDate, DimDate.date_key == f.date_key)
        .join(DimPlatform, DimPlatform.key == f.platform_key)
        .join(DimFormat, DimFormat.key == f.format_key)
        .join(DimTopic, DimTopic.key == f.topic_key)
        .join(DimHook, DimHook.key == f.hook_key)
        .join(DimTone, DimTone.key == f.tone_key)
        .join(DimDaypart, DimDaypart.key == f.daypart_key)
        .where(f.workspace_id == workspace_id)
        .order_by(f.published_at, f.post_id)
    )
    df = pd.DataFrame(session.execute(stmt).mappings().all())
    if df.empty:
        return df
    df["published_at"] = pd.to_datetime(df["published_at"])
    df["has_cta"] = df["has_cta"].astype(int)
    df["has_question"] = df["has_question"].astype(int)
    df["is_weekend"] = df["is_weekend"].astype(bool)
    return df.reset_index(drop=True)


def dataset_hash(df: pd.DataFrame) -> str:
    """Stable fingerprint of the modelling data (ids + outcomes)."""
    if df.empty:
        return hashlib.sha256(b"empty").hexdigest()
    payload = df[["post_id", "impressions", "engagements"]].to_csv(index=False).encode()
    return hashlib.sha256(payload).hexdigest()
