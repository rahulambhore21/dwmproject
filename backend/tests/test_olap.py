import pytest
from pydantic import ValidationError

from app.olap.engine import OlapQuery, run_query
from app.warehouse.frames import load_fact_frame


@pytest.fixture(scope="module")
def df(seeded):
    s, ws = seeded
    return load_fact_frame(s, ws.id)


def test_group_by_matches_pandas(df):
    out = run_query(df, OlapQuery(rows=["platform"], measures=["posts", "engagement_rate"]))
    by = {r["keys"]["platform"]: r for r in out["rows"]}
    for p, g in df.groupby("platform"):
        assert by[p]["posts"] == len(g)
        assert by[p]["engagement_rate"] == pytest.approx(g["engagement_rate"].mean(), abs=1e-5)
    assert sum(r["posts"] for r in out["rows"]) == out["n_posts"] == len(df)


def test_slice_and_dice(df):
    sl = run_query(df, OlapQuery(rows=["format"], filters={"platform": ["LinkedIn"]}))
    assert sl["n_posts"] == (df["platform"] == "LinkedIn").sum()
    dice = run_query(df, OlapQuery(rows=["topic"], filters={"platform": ["LinkedIn", "X"], "format": ["Text"]}))
    assert dice["n_posts"] == df[df["platform"].isin(["LinkedIn", "X"]) & (df["format"] == "Text")].shape[0]


def test_rollup_has_subtotals_that_sum(df):
    out = run_query(df, OlapQuery(rows=["platform", "format"], rollup=True))
    subtotals = {r["keys"]["platform"]: r["posts"] for r in out["rows"] if r["level"] == 1}
    assert subtotals
    for p, total in subtotals.items():
        detail = sum(r["posts"] for r in out["rows"] if r["level"] == 2 and r["keys"]["platform"] == p)
        assert detail == total


def test_pivot_cells(df):
    out = run_query(df, OlapQuery(rows=["topic"], columns="platform", measures=["posts"]))
    piv = out["pivot"]
    assert set(piv["column_labels"]) == {"Instagram", "LinkedIn", "TikTok", "X"}
    total = sum(c["posts"] for r in piv["rows"] for c in r["cells"] if c)
    assert total == len(df)


def test_time_dimensions_are_naturally_ordered(df):
    out = run_query(df, OlapQuery(rows=["weekday"]))
    assert [r["keys"]["weekday"] for r in out["rows"]] == ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def test_low_sample_flag_and_empty_filter(df):
    out = run_query(df, OlapQuery(rows=["platform", "format", "topic"]))
    assert any(r["low_sample"] for r in out["rows"])
    empty = run_query(df, OlapQuery(rows=["format"], filters={"platform": ["MySpace"]}))
    assert empty["status"] == "empty"


def test_rejects_unknown_dimensions_and_bad_pivots(df):
    with pytest.raises(ValidationError):
        OlapQuery(rows=["; drop table posts"])
    with pytest.raises(ValidationError):
        OlapQuery(rows=["platform"], columns="platform")
    with pytest.raises(ValueError):
        run_query(df, OlapQuery(columns="platform"))
