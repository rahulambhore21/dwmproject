from datetime import datetime

import pytest
from sqlalchemy import func, select

from app.etl.pipeline import ingest_records
from app.etl.text import daypart, extract_text_features
from app.models import DimPlatform, FactPost, Post, Workspace
from app.warehouse.frames import load_fact_frame


def _rec(i, **kw):
    base = dict(external_id=f"X-{i}", platform="Instagram", format="Reel", topic="Education", hook_type="Question",
                tone="Warm", caption="Why do teams ignore data? Save this. #data", published_at="2026-01-05T09:00:00",
                impressions=1000, reach=800, likes=40, comments=5, shares=3, saves=2)
    base.update(kw)
    return base


def test_text_features():
    f = extract_text_features("Why? Try it now ✨ #a #b")
    assert f.has_question and f.has_cta and f.hashtag_count == 2 and f.emoji_count == 1
    assert extract_text_features("plain statement").has_question is False
    assert daypart(7) == "Morning" and daypart(20) == "Evening"


def test_etl_rejects_and_reports(empty_session):
    s = empty_session
    ws = Workspace(name="t", slug="t")
    s.add(ws)
    s.commit()
    records = [
        _rec(1),
        _rec(2, impressions=0),
        _rec(3, likes=2000),
        _rec(4, published_at="2999-01-01T00:00:00"),
        _rec(5, reach=5000),
        _rec(1),
        {"external_id": "X-9"},
    ]
    report = ingest_records(s, ws.id, records, source="test")
    assert report["rows_in"] == 7
    assert report["rows_loaded"] == 1
    assert report["rows_rejected"] == 5
    assert report["duplicates_skipped"] == 1
    assert len(report["rejection_examples"]) == 5
    again = ingest_records(s, ws.id, [_rec(1)], source="test")
    assert again["rows_loaded"] == 0 and again["duplicates_skipped"] == 1


def test_batch_size_limit(empty_session):
    s = empty_session
    ws = Workspace(name="t", slug="t2")
    s.add(ws)
    s.commit()
    with pytest.raises(ValueError):
        ingest_records(s, ws.id, [{}] * 20001, source="x")


def test_warehouse_star_schema(seeded):
    s, ws = seeded
    n_posts = s.scalar(select(func.count(Post.id)))
    n_fact = s.scalar(select(func.count(FactPost.post_id)))
    assert n_posts == n_fact == 720
    assert s.scalar(select(func.count(DimPlatform.key))) == 4
    df = load_fact_frame(s, ws.id)
    assert len(df) == 720
    row = df.iloc[0]
    assert row["engagements"] == row["likes"] + row["comments"] + row["shares"] + row["saves"]
    assert abs(row["engagement_rate"] - row["engagements"] / row["impressions"]) < 1e-12
    assert df["published_at"].max() < datetime(2026, 10, 4)


def test_seed_is_deterministic():
    from app.seed.generator import generate_posts

    a = generate_posts(50, datetime(2026, 10, 4), 7)
    b = generate_posts(50, datetime(2026, 10, 4), 7)
    c = generate_posts(50, datetime(2026, 10, 4), 8)
    assert a == b and a != c
