from __future__ import annotations

from datetime import UTC, datetime


def utcnow() -> datetime:
    """Naive UTC 'now' (the schema stores naive UTC timestamps)."""
    return datetime.now(UTC).replace(tzinfo=None)
