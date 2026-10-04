"""SQLAlchemy schema.

Layers
  OLTP / staging : workspaces, posts, etl_runs
  Warehouse      : dim_date, dim_platform, dim_format, dim_topic, dim_hook,
                   dim_tone, dim_daypart, fact_post  (star schema)
  Intelligence   : model_runs, post_labels
  Experimentation: experiments, experiment_variants, experiment_observations, learnings
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .clock import utcnow
from .db import Base

_utcnow = utcnow


class Workspace(Base):
    __tablename__ = "workspaces"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(60), unique=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class Post(Base):
    """Raw ingested post (staging / OLTP)."""

    __tablename__ = "posts"
    __table_args__ = (UniqueConstraint("workspace_id", "platform", "external_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(64))
    platform: Mapped[str] = mapped_column(String(32))
    format: Mapped[str] = mapped_column(String(32))
    topic: Mapped[str] = mapped_column(String(64))
    hook_type: Mapped[str] = mapped_column(String(32))
    tone: Mapped[str] = mapped_column(String(32))
    caption: Mapped[str] = mapped_column(Text)
    published_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    media_count: Mapped[int] = mapped_column(Integer, default=1)
    impressions: Mapped[int] = mapped_column(Integer)
    reach: Mapped[int] = mapped_column(Integer)
    likes: Mapped[int] = mapped_column(Integer)
    comments: Mapped[int] = mapped_column(Integer)
    shares: Mapped[int] = mapped_column(Integer)
    saves: Mapped[int] = mapped_column(Integer)


class EtlRun(Base):
    __tablename__ = "etl_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"))
    source: Mapped[str] = mapped_column(String(64))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    rows_in: Mapped[int] = mapped_column(Integer, default=0)
    rows_loaded: Mapped[int] = mapped_column(Integer, default=0)
    report: Mapped[dict] = mapped_column(JSON, default=dict)


# ---------------------------------------------------------------- warehouse
class DimDate(Base):
    __tablename__ = "dim_date"
    date_key: Mapped[int] = mapped_column(primary_key=True)  # yyyymmdd
    full_date: Mapped[date] = mapped_column(Date)
    year: Mapped[int] = mapped_column(Integer)
    quarter: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)
    month_label: Mapped[str] = mapped_column(String(8))  # 2026-03
    iso_week: Mapped[int] = mapped_column(Integer)
    day_of_week: Mapped[int] = mapped_column(Integer)  # 0=Mon
    day_name: Mapped[str] = mapped_column(String(12))
    is_weekend: Mapped[bool] = mapped_column(Boolean)


class DimPlatform(Base):
    __tablename__ = "dim_platform"
    key: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)


class DimFormat(Base):
    __tablename__ = "dim_format"
    key: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)


class DimTopic(Base):
    __tablename__ = "dim_topic"
    key: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)


class DimHook(Base):
    __tablename__ = "dim_hook"
    key: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)


class DimTone(Base):
    __tablename__ = "dim_tone"
    key: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)


class DimDaypart(Base):
    __tablename__ = "dim_daypart"
    key: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)


class FactPost(Base):
    __tablename__ = "fact_post"
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    date_key: Mapped[int] = mapped_column(ForeignKey("dim_date.date_key"), index=True)
    platform_key: Mapped[int] = mapped_column(ForeignKey("dim_platform.key"))
    format_key: Mapped[int] = mapped_column(ForeignKey("dim_format.key"))
    topic_key: Mapped[int] = mapped_column(ForeignKey("dim_topic.key"))
    hook_key: Mapped[int] = mapped_column(ForeignKey("dim_hook.key"))
    tone_key: Mapped[int] = mapped_column(ForeignKey("dim_tone.key"))
    daypart_key: Mapped[int] = mapped_column(ForeignKey("dim_daypart.key"))
    published_at: Mapped[datetime] = mapped_column(DateTime)
    hour: Mapped[int] = mapped_column(Integer)
    # pre-publication attributes (usable as model features)
    caption_length: Mapped[int] = mapped_column(Integer)
    word_count: Mapped[int] = mapped_column(Integer)
    hashtag_count: Mapped[int] = mapped_column(Integer)
    emoji_count: Mapped[int] = mapped_column(Integer)
    has_cta: Mapped[bool] = mapped_column(Boolean)
    has_question: Mapped[bool] = mapped_column(Boolean)
    media_count: Mapped[int] = mapped_column(Integer)
    # post-publication measures (never features for pre-publication prediction)
    impressions: Mapped[int] = mapped_column(Integer)
    reach: Mapped[int] = mapped_column(Integer)
    likes: Mapped[int] = mapped_column(Integer)
    comments: Mapped[int] = mapped_column(Integer)
    shares: Mapped[int] = mapped_column(Integer)
    saves: Mapped[int] = mapped_column(Integer)
    engagements: Mapped[int] = mapped_column(Integer)
    engagement_rate: Mapped[float] = mapped_column(Float)
    save_rate: Mapped[float] = mapped_column(Float)
    share_rate: Mapped[float] = mapped_column(Float)
    comment_rate: Mapped[float] = mapped_column(Float)


# ------------------------------------------------------------- intelligence
class ModelRun(Base):
    __tablename__ = "model_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    algorithm: Mapped[str] = mapped_column(String(48), index=True)
    task: Mapped[str] = mapped_column(String(32))  # regression|classification|clustering|association|ranking
    target: Mapped[str | None] = mapped_column(String(48), nullable=True)
    features: Mapped[list] = mapped_column(JSON, default=list)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    results: Mapped[dict] = mapped_column(JSON, default=dict)  # interpretable output (coefficients, rules, ...)
    n_train: Mapped[int] = mapped_column(Integer, default=0)
    n_test: Mapped[int] = mapped_column(Integer, default=0)
    dataset_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), default="ok")  # ok|insufficient_data|failed
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifact_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)


class PostLabel(Base):
    __tablename__ = "post_labels"
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("model_runs.id"))
    archetype: Mapped[int] = mapped_column(Integer)


# ------------------------------------------------------------ experimentation
class Experiment(Base):
    __tablename__ = "experiments"
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    hypothesis: Mapped[str] = mapped_column(Text)
    variable: Mapped[str] = mapped_column(String(48))
    platform: Mapped[str] = mapped_column(String(32))
    metric: Mapped[str] = mapped_column(String(32), default="engagement_rate")
    status: Mapped[str] = mapped_column(String(16), default="running")  # running|completed
    min_per_variant: Mapped[int] = mapped_column(Integer, default=6)
    randomized: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(32), default="manual")
    prediction_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    variants: Mapped[list[ExperimentVariant]] = relationship(
        back_populates="experiment", cascade="all, delete-orphan", order_by="ExperimentVariant.id"
    )


class ExperimentVariant(Base):
    __tablename__ = "experiment_variants"
    id: Mapped[int] = mapped_column(primary_key=True)
    experiment_id: Mapped[int] = mapped_column(ForeignKey("experiments.id"), index=True)
    label: Mapped[str] = mapped_column(String(8))
    is_control: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[str] = mapped_column(String(240))
    experiment: Mapped[Experiment] = relationship(back_populates="variants")
    observations: Mapped[list[ExperimentObservation]] = relationship(
        back_populates="variant", cascade="all, delete-orphan", order_by="ExperimentObservation.id"
    )


class ExperimentObservation(Base):
    __tablename__ = "experiment_observations"
    id: Mapped[int] = mapped_column(primary_key=True)
    variant_id: Mapped[int] = mapped_column(ForeignKey("experiment_variants.id"), index=True)
    published_at: Mapped[datetime] = mapped_column(DateTime)
    impressions: Mapped[int] = mapped_column(Integer)
    engagements: Mapped[int] = mapped_column(Integer)
    saves: Mapped[int] = mapped_column(Integer, default=0)
    variant: Mapped[ExperimentVariant] = relationship(back_populates="observations")


class Learning(Base):
    __tablename__ = "learnings"
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    experiment_id: Mapped[int | None] = mapped_column(ForeignKey("experiments.id"), nullable=True)
    statement: Mapped[str] = mapped_column(Text)
    verdict: Mapped[str] = mapped_column(String(24))  # adopt|keep_control|inconclusive
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
