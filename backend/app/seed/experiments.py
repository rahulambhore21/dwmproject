"""Seed demo experiments. Observations come from the same simulator as history; verdicts come from the real analysis."""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Experiment
from ..services.experiments import (
    ExperimentIn,
    ObservationIn,
    VariantIn,
    add_observation,
    complete_experiment,
    create_experiment,
)
from .generator import build_caption, simulate_metrics

# (name, hypothesis, variable, platform, [(label, description, control, attrs)], posts per variant, randomized, complete)
SPECS = [
    dict(
        name="Document carousel vs text post: product tips", variable="format", platform="LinkedIn", randomized=True,
        hypothesis="A document carousel will earn a higher engagement rate than a text-only post for the same product tip.",
        base=dict(topic="Product tips", hook="How-to", tone="Authoritative", hour=8, length=430),
        variants=[("A", "Text-only post", True, dict(format="Text")), ("B", "Document carousel", False, dict(format="Carousel"))],
        n=(11, 11), complete=True, weekday_only=True,
    ),
    dict(
        name="Numbered-list hook vs bold-claim hook on carousels", variable="hook", platform="Instagram", randomized=False,
        hypothesis="A numbered-list opener will lift engagement relative to a bold-claim opener on Instagram carousels.",
        base=dict(topic="Education", tone="Warm", hour=19, length=200, format="Carousel"),
        variants=[("A", "Bold-claim hook", True, dict(hook="Bold claim")), ("B", "Numbered-list hook", False, dict(hook="Numbered list"))],
        n=(9, 9), complete=True, weekday_only=False,
    ),
    dict(
        name="Evening vs morning reels", variable="daypart", platform="Instagram", randomized=True,
        hypothesis="Reels posted at 19:00 will outperform reels posted at 08:00.",
        base=dict(topic="Behind the scenes", hook="Story", tone="Playful", length=160, format="Reel"),
        variants=[("A", "Morning (08:00)", True, dict(hour=8)), ("B", "Evening (19:00)", False, dict(hour=19))],
        n=(8, 8), complete=True, weekday_only=False,
    ),
    dict(
        name="Question hook vs story hook on TikTok", variable="hook", platform="TikTok", randomized=True,
        hypothesis="A question opener will beat a story opener on short videos.",
        base=dict(topic="Product tips", tone="Playful", hour=20, length=110, format="Video"),
        variants=[("A", "Story hook", True, dict(hook="Story")), ("B", "Question hook", False, dict(hook="Question"))],
        n=(3, 2), complete=False, weekday_only=False,
    ),
]


def seed_experiments(session: Session, workspace_id: int, as_of: datetime, seed: int) -> None:
    if session.execute(select(Experiment.id).where(Experiment.workspace_id == workspace_id).limit(1)).first():
        return
    rng = np.random.default_rng(seed + 101)
    start = as_of - timedelta(days=540)
    for si, spec in enumerate(SPECS):
        exp = create_experiment(session, workspace_id, ExperimentIn(
            name=spec["name"], hypothesis=spec["hypothesis"], variable=spec["variable"], platform=spec["platform"],
            randomized=spec["randomized"], source="demo-seed", min_per_variant=6,
            variants=[VariantIn(label=lab, description=desc, is_control=ctl) for lab, desc, ctl, _ in spec["variants"]]))
        weeks = max(spec["n"])
        for vi, (_, _, _, attrs) in enumerate(spec["variants"]):
            vid = exp.variants[vi].id
            cfg = {**spec["base"], **attrs}
            for j in range(spec["n"][vi]):
                day = as_of - timedelta(days=4 + (weeks - j) * 6 + vi * 2 + si)
                if spec.get("weekday_only") and day.weekday() >= 5:
                    day -= timedelta(days=day.weekday() - 4)
                published = day.replace(hour=cfg["hour"], minute=int(rng.integers(0, 50)), second=0, microsecond=0)
                caption = build_caption(rng, spec["platform"], cfg["topic"], cfg["hook"], cfg["tone"], cfg["length"],
                                        force_cta=False, force_question=None)
                m = simulate_metrics(rng, platform=spec["platform"], format=cfg["format"], topic=cfg["topic"], hook=cfg["hook"],
                                     tone=cfg["tone"], published_at=published, caption=caption, start=start)
                eng = m["likes"] + m["comments"] + m["shares"] + m["saves"]
                add_observation(session, workspace_id, exp.id, ObservationIn(
                    variant_id=vid, published_at=published, impressions=m["impressions"], engagements=eng, saves=m["saves"]))
        if spec["complete"]:
            complete_experiment(session, workspace_id, exp.id, at=as_of - timedelta(days=2 + si))
