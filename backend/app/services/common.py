from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Workspace
from ..warehouse.frames import load_fact_frame


class ApiError(Exception):
    """Domain error mapped to an HTTP status by the app's exception handler."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def active_workspace(session: Session) -> Workspace:
    ws = session.execute(select(Workspace).order_by(Workspace.id).limit(1)).scalar_one_or_none()
    if ws is None:
        raise ApiError(503, "no_workspace", "No workspace exists yet. Seed the demo data or ingest posts first.")
    return ws


@dataclass
class Context:
    session: Session
    workspace: Workspace
    frame: pd.DataFrame


def get_context(session: Session) -> Context:
    ws = active_workspace(session)
    return Context(session, ws, load_fact_frame(session, ws.id))


def pct_rank(series: pd.Series, value: float) -> float:
    """Percentile (0-100) of `value` within `series` (share of values <= value)."""
    if len(series) == 0:
        return float("nan")
    return float((series <= value).mean() * 100)
