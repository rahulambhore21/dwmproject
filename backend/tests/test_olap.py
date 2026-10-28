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


def test_to_sql_describes_the_same_query():
    from app.olap.engine import to_sql

    q = OlapQuery(rows=["platform", "weekday"], columns="daypart", filters={"format": ["Reel", "O'Brien"]},
                  measures=["posts", "median_engagement_rate"], rollup=True, min_posts=5)
    sql = to_sql(q)
    assert "GROUP BY ROLLUP (dp.name, d.day_name), dd.name" in sql
    assert "JOIN dim_platform" in sql and "JOIN dim_daypart" in sql and "JOIN dim_format" in sql
    assert sql.count("JOIN dim_date") == 1  # joined once even though used by several dimensions
    assert "IN ('Reel', 'O''Brien')" in sql  # quotes escaped
    assert "percentile_cont(0.5)" in sql and "HAVING COUNT(*) >= 5" in sql
    assert "workspace_id = :workspace_id" in sql


def test_to_sql_group_by_matches_engine(seeded):
    """Run the generated SQL on the test DB (no ROLLUP / percentile) and compare with the engine."""
    from sqlalchemy import text

    from app.olap.engine import to_sql

    s, ws = seeded
    q = OlapQuery(rows=["platform", "year"], measures=["posts", "engagement_rate"], sort_by="posts", limit=1000)
    sql = to_sql(q).rstrip(";").replace(":workspace_id", str(ws.id))
    got = {(r[0], r[1]): (r[2], r[3]) for r in s.execute(text(sql)).all()}
    frame = load_fact_frame(s, ws.id)
    out = run_query(frame, q)
    assert len(got) == len(out["rows"])
    for r in out["rows"]:
        n, er = got[(r["keys"]["platform"], r["keys"]["year"])]
        assert n == r["posts"] and er == pytest.approx(r["engagement_rate"], abs=1e-5)
