"""OLAP engine over the star schema (roll-up, drill-down, slice, dice, pivot).

Pure functions over the analysis frame; whitelisted dimensions/measures only.
Rates are per-post means (each post counts once) with t-based 95% intervals,
and every cell carries its sample size so the UI can flag thin cells.
"""
from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field, model_validator
from scipy import stats

Dimension = Literal["platform", "format", "topic", "hook", "tone", "daypart", "weekday", "hour", "year", "quarter", "month"]
Measure = Literal[
    "posts", "impressions", "engagements", "engagement_rate", "median_engagement_rate",
    "save_rate", "share_rate", "comment_rate", "avg_impressions",
]

HIERARCHIES: dict[str, list[str]] = {
    "Channel": ["platform", "format"],
    "Content": ["topic", "hook", "tone"],
    "Timing": ["daypart", "weekday", "hour"],
    "Calendar": ["year", "quarter", "month"],
}
MEASURE_LABELS: dict[str, str] = {
    "posts": "Posts", "impressions": "Impressions", "engagements": "Engagements",
    "engagement_rate": "Avg engagement rate", "median_engagement_rate": "Median engagement rate",
    "save_rate": "Avg save rate", "share_rate": "Avg share rate", "comment_rate": "Avg comment rate",
    "avg_impressions": "Avg impressions",
}
RATE_MEASURES = {"engagement_rate", "median_engagement_rate", "save_rate", "share_rate", "comment_rate"}
_ORDER = {
    "weekday": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    "daypart": ["Morning", "Midday", "Afternoon", "Evening"],
}
LOW_SAMPLE = 8


class OlapQuery(BaseModel):
    rows: list[Dimension] = Field(default_factory=list, max_length=3)
    columns: Dimension | None = None
    measures: list[Measure] = Field(default_factory=lambda: ["posts", "engagement_rate"], min_length=1, max_length=6)
    filters: dict[Dimension, list[str | int]] = Field(default_factory=dict)
    rollup: bool = False
    sort_by: Measure | None = None
    descending: bool = True
    limit: int = Field(default=200, ge=1, le=1000)
    min_posts: int = Field(default=1, ge=1, le=500)

    @model_validator(mode="after")
    def _check(self) -> OlapQuery:
        if self.columns and self.columns in self.rows:
            raise ValueError("columns dimension must differ from row dimensions")
        if len(set(self.rows)) != len(self.rows):
            raise ValueError("duplicate row dimensions")
        return self


def schema() -> dict:
    return {
        "dimensions": [
            {"key": d, "label": d.replace("_", " ").title()}
            for d in ("platform", "format", "topic", "hook", "tone", "daypart", "weekday", "hour", "year", "quarter", "month")
        ],
        "hierarchies": [{"name": k, "levels": v} for k, v in HIERARCHIES.items()],
        "measures": [{"key": k, "label": v, "is_rate": k in RATE_MEASURES} for k, v in MEASURE_LABELS.items()],
    }


def _apply_filters(df: pd.DataFrame, filters: dict) -> pd.DataFrame:
    for dim, values in filters.items():
        if not values:
            continue
        col = df[dim]
        coerced = [type(col.iloc[0])(v) if len(col) and not isinstance(col.iloc[0], str) else str(v) for v in values]
        df = df[col.isin(coerced)]
    return df


def _aggregate(g: pd.core.groupby.DataFrameGroupBy | pd.DataFrame) -> pd.DataFrame:
    named = dict(
        posts=("post_id", "count"), impressions=("impressions", "sum"), engagements=("engagements", "sum"),
        engagement_rate=("engagement_rate", "mean"), median_engagement_rate=("engagement_rate", "median"),
        er_sd=("engagement_rate", "std"), save_rate=("save_rate", "mean"), share_rate=("share_rate", "mean"),
        comment_rate=("comment_rate", "mean"), avg_impressions=("impressions", "mean"),
    )
    return g.agg(**named)


def _finish(agg: pd.DataFrame) -> pd.DataFrame:
    n = agg["posts"].to_numpy(dtype=float)
    sd = agg["er_sd"].fillna(0).to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        tcrit = np.where(n > 1, stats.t.ppf(0.975, np.maximum(n - 1, 1)), np.nan)
        half = tcrit * sd / np.sqrt(np.maximum(n, 1))
    agg["er_ci_low"] = np.maximum(agg["engagement_rate"] - half, 0)
    agg["er_ci_high"] = agg["engagement_rate"] + half
    agg["low_sample"] = agg["posts"] < LOW_SAMPLE
    return agg.drop(columns=["er_sd"])


def _sorted_keys(df: pd.DataFrame, rows: list[str]) -> pd.DataFrame:
    for dim in rows[::-1]:
        if dim in _ORDER:
            rank = {v: i for i, v in enumerate(_ORDER[dim])}
            df = df.sort_values(dim, key=lambda s: s.map(rank), kind="stable")
    return df


_NATURAL_ORDER = {"weekday", "daypart", "hour", "year", "quarter", "month"}


def _order_rows(agg: pd.DataFrame, keys: list[str], q: OlapQuery) -> pd.DataFrame:
    """Explicit sort_by wins; otherwise natural order for time-like dims, else by first measure."""
    if q.sort_by:
        return agg.sort_values(q.sort_by, ascending=not q.descending, kind="stable")
    if keys[0] in _NATURAL_ORDER:
        return _sorted_keys(agg.sort_values(keys, kind="stable"), keys)
    return agg.sort_values(q.measures[0], ascending=not q.descending, kind="stable")


def _clean(v):
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        return None if np.isnan(v) else round(float(v), 6)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    return v


def run_query(df: pd.DataFrame, q: OlapQuery) -> dict:
    if df.empty:
        return {"status": "empty", "message": "No posts in the warehouse yet.", "rows": [], "totals": None,
                "pivot": None, "n_posts": 0, "low_sample_threshold": LOW_SAMPLE}
    work = _apply_filters(df, q.filters)
    n_filtered = len(work)
    if n_filtered == 0:
        return {"status": "empty", "message": "No posts match the selected filters.", "rows": [], "totals": None,
                "pivot": None, "n_posts": 0, "low_sample_threshold": LOW_SAMPLE}

    totals = _finish(_aggregate(work.assign(_all=1).groupby("_all"))).iloc[0].to_dict()
    totals = {k: _clean(v) for k, v in totals.items()}

    keys = list(q.rows)
    rows_out: list[dict] = []
    if keys:
        agg = _finish(_aggregate(work.groupby(keys, observed=True))).reset_index()
        agg = agg[agg["posts"] >= q.min_posts]
        agg = _order_rows(agg, keys, q)
        for rec in agg.head(q.limit).to_dict("records"):
            row = {"keys": {k: _clean(rec[k]) for k in keys}, "level": len(keys)}
            row.update({k: _clean(v) for k, v in rec.items() if k not in keys})
            rows_out.append(row)
        if q.rollup and len(keys) > 1:
            subtotal_rows: list[dict] = []
            for depth in range(len(keys) - 1, 0, -1):
                sub = _finish(_aggregate(work.groupby(keys[:depth], observed=True))).reset_index()
                for rec in sub.to_dict("records"):
                    row = {"keys": {k: (_clean(rec[k]) if k in keys[:depth] else None) for k in keys}, "level": depth}
                    row.update({k: _clean(v) for k, v in rec.items() if k not in keys[:depth]})
                    subtotal_rows.append(row)
            rows_out = _interleave(rows_out, subtotal_rows, keys)

    pivot = None
    if q.columns:
        if not keys:
            raise ValueError("pivot requires at least one row dimension")
        measure = q.sort_by or q.measures[0]
        cells = _finish(_aggregate(work.groupby([*keys, q.columns], observed=True))).reset_index()
        col_labels = _ordered_unique(cells[q.columns], q.columns)
        row_labels = [tuple(r) for r in cells[keys].drop_duplicates().itertuples(index=False)]
        lookup = {(tuple(r[k] for k in keys), r[q.columns]): r for r in cells.to_dict("records")}
        pivot = {
            "measure": measure, "row_dimensions": keys, "column_dimension": q.columns, "column_labels": col_labels,
            "rows": [
                {"keys": dict(zip(keys, map(_clean, rl), strict=True)),
                 "cells": [
                     ({"value": _clean(lookup[(rl, c)][measure]), "posts": int(lookup[(rl, c)]["posts"]),
                       "low_sample": bool(lookup[(rl, c)]["low_sample"])} if (rl, c) in lookup else None)
                     for c in col_labels]}
                for rl in row_labels[: q.limit]
            ],
        }

    return {
        "status": "ok", "message": None, "rows": rows_out, "totals": totals, "pivot": pivot,
        "n_posts": int(n_filtered), "low_sample_threshold": LOW_SAMPLE,
        "dimensions": keys, "measures": q.measures,
    }


def _ordered_unique(series: pd.Series, dim: str) -> list:
    vals = list(series.drop_duplicates())
    if dim in _ORDER:
        vals.sort(key=lambda v: _ORDER[dim].index(v) if v in _ORDER[dim] else 99)
    else:
        vals.sort()
    return [_clean(v) for v in vals]


def _interleave(detail: list[dict], subtotals: list[dict], keys: list[str]) -> list[dict]:
    """Group detail rows under their first-level subtotal row."""
    first = keys[0]
    by_prefix = {(r["keys"][first],): r for r in subtotals if r["level"] == 1}
    groups: dict = {}
    for r in detail:
        groups.setdefault(r["keys"][first], []).append(r)
    out: list[dict] = []
    for g, members in groups.items():
        out.append(by_prefix[(g,)])
        out.extend(members)
    return out
