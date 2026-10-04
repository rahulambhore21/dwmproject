"""ETL: validate raw records -> stage in `posts` -> rebuild the dimensional warehouse.

Every rejection is counted and reported; nothing is silently dropped or imputed.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..clock import utcnow
from ..models import EtlRun, Post
from ..warehouse.build import build_warehouse

REQUIRED_COLUMNS = [
    "external_id", "platform", "format", "topic", "hook_type", "tone", "caption",
    "published_at", "impressions", "reach", "likes", "comments", "shares", "saves",
]
MAX_ROWS_PER_BATCH = 20000


class RawPostIn(BaseModel):
    external_id: str = Field(min_length=1, max_length=64)
    platform: str = Field(min_length=1, max_length=32)
    format: str = Field(min_length=1, max_length=32)
    topic: str = Field(min_length=1, max_length=64)
    hook_type: str = Field(min_length=1, max_length=32)
    tone: str = Field(min_length=1, max_length=32)
    caption: str = Field(max_length=10000)
    published_at: datetime
    media_count: int = Field(default=1, ge=0, le=100)
    impressions: int = Field(ge=1)
    reach: int = Field(ge=0)
    likes: int = Field(ge=0)
    comments: int = Field(ge=0)
    shares: int = Field(ge=0)
    saves: int = Field(ge=0)

    @field_validator("external_id", "platform", "format", "topic", "hook_type", "tone", mode="before")
    @classmethod
    def _strip(cls, v: Any) -> Any:
        return v.strip() if isinstance(v, str) else v

    @field_validator("published_at")
    @classmethod
    def _not_future(cls, v: datetime) -> datetime:
        v = v.replace(tzinfo=None)
        if v > utcnow():
            raise ValueError("published_at is in the future")
        return v

    @model_validator(mode="after")
    def _consistent(self) -> RawPostIn:
        if self.likes + self.comments + self.shares + self.saves > self.impressions:
            raise ValueError("engagements exceed impressions")
        if self.reach > self.impressions:
            raise ValueError("reach exceeds impressions")
        return self


def _reason(err: ValidationError) -> str:
    e = err.errors()[0]
    loc = ".".join(str(x) for x in e["loc"]) or "row"
    return f"{loc}: {e['msg']}"


def ingest_records(session: Session, workspace_id: int, records: list[dict], source: str) -> dict:
    """Validate and load records; rebuild warehouse; return the ETL report."""
    if len(records) > MAX_ROWS_PER_BATCH:
        raise ValueError(f"Batch too large ({len(records)} rows, max {MAX_ROWS_PER_BATCH}).")
    rejected: Counter[str] = Counter()
    examples: list[dict] = []
    valid: list[RawPostIn] = []
    for idx, rec in enumerate(records):
        try:
            valid.append(RawPostIn(**rec))
        except ValidationError as err:
            reason = _reason(err)
            rejected[reason[:90]] += 1
            if len(examples) < 15:
                examples.append({"row": idx + 1, "reason": reason})
        except TypeError as err:
            rejected[f"row: {err}"] += 1

    existing = set(
        session.execute(select(Post.platform, Post.external_id).where(Post.workspace_id == workspace_id)).all()
    )
    seen: set[tuple[str, str]] = set()
    fresh: list[RawPostIn] = []
    duplicates = 0
    for r in valid:
        key = (r.platform, r.external_id)
        if key in existing or key in seen:
            duplicates += 1
            continue
        seen.add(key)
        fresh.append(r)

    session.add_all(Post(workspace_id=workspace_id, **r.model_dump()) for r in fresh)
    session.flush()
    warehouse = build_warehouse(session, workspace_id)
    report = {
        "rows_in": len(records),
        "rows_valid": len(valid),
        "rows_loaded": len(fresh),
        "rows_rejected": len(records) - len(valid),
        "duplicates_skipped": duplicates,
        "rejection_reasons": dict(rejected.most_common(10)),
        "rejection_examples": examples,
        "warehouse": warehouse,
    }
    session.add(EtlRun(workspace_id=workspace_id, source=source, rows_in=len(records), rows_loaded=len(fresh), report=report))
    session.commit()
    return report


def reset_workspace_data(session: Session, workspace_id: int) -> None:
    from ..models import FactPost, PostLabel

    session.execute(delete(PostLabel))
    session.execute(delete(FactPost).where(FactPost.workspace_id == workspace_id))
    session.execute(delete(Post).where(Post.workspace_id == workspace_id))
    session.commit()
