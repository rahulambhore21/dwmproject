"""Seed the demo workspace: synthetic history -> ETL -> warehouse -> models -> experiments."""
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..clock import utcnow
from ..config import get_settings
from ..etl.pipeline import ingest_records
from ..models import Post, Workspace
from .generator import generate_posts

log = logging.getLogger("signal.seed")
DEMO_SLUG = "northwind-studio"
DEMO_POSTS = 720


def get_demo_workspace(session: Session) -> Workspace | None:
    return session.execute(select(Workspace).where(Workspace.slug == DEMO_SLUG)).scalar_one_or_none()


def seed_demo(session: Session, as_of: datetime | None = None, n_posts: int = DEMO_POSTS, seed: int | None = None) -> Workspace:
    from ..ml.pipeline import train_all
    from .experiments import seed_experiments

    as_of = as_of or utcnow().replace(minute=0, second=0, microsecond=0)
    seed = get_settings().seed if seed is None else seed
    ws = get_demo_workspace(session)
    if ws is None:
        ws = Workspace(name="Northwind Studio", slug=DEMO_SLUG, is_demo=True)
        session.add(ws)
        session.commit()
    have = session.execute(select(Post.id).where(Post.workspace_id == ws.id).limit(1)).first()
    if not have:
        log.info("seeding %d synthetic posts", n_posts)
        report = ingest_records(session, ws.id, generate_posts(n_posts, as_of, seed), source="demo-seed")
        log.info("ETL: %s", {k: v for k, v in report.items() if k != "warehouse"})
    train_all(session, ws.id)
    seed_experiments(session, ws.id, as_of, seed)
    return ws
