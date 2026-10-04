"""Overview: UNDERSTAND -> DECIDE -> EXPERIMENT -> LEARN, assembled from stored model runs and the warehouse."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ml.pipeline import ALGORITHMS, latest_run, latest_runs
from ..models import EtlRun
from . import experiments as exp_svc

HEADLINE_METRIC = {
    "linear_regression": ("r2", "Holdout R²"), "multiple_linear_regression": ("r2_platform_adjusted", "Within-platform R²"),
    "mutual_information": ("features_above_noise", "Features above noise"), "decision_tree": ("roc_auc", "Holdout AUC"),
    "gaussian_nb": ("roc_auc", "Holdout AUC"), "kmeans": ("silhouette", "Silhouette"),
    "agglomerative": ("silhouette", "Silhouette"), "apriori": ("rules_significant", "Significant rules"),
}


def _window_compare(df: pd.DataFrame, days: int) -> dict:
    end = df["published_at"].max()
    cur = df[df["published_at"] > end - pd.Timedelta(days=days)]
    prev = df[(df["published_at"] <= end - pd.Timedelta(days=days)) & (df["published_at"] > end - pd.Timedelta(days=2 * days))]
    out = {"window_days": days, "n_current": int(len(cur)), "n_previous": int(len(prev)),
           "current": float(cur["engagement_rate"].mean()) if len(cur) else None,
           "previous": float(prev["engagement_rate"].mean()) if len(prev) else None, "delta_pct": None, "p_value": None}
    if len(cur) >= 8 and len(prev) >= 8:
        out["delta_pct"] = float((out["current"] / out["previous"] - 1) * 100)
        # compare platform-adjusted performance so a shift in platform mix does not masquerade as a trend
        adj = df["engagement_rate"] / df.groupby("platform")["engagement_rate"].transform("median")
        out["p_value"] = float(stats.ttest_ind(adj.loc[cur.index], adj.loc[prev.index], equal_var=False).pvalue)
    return out


def _signal_cards(session: Session, ws_id: int) -> dict:
    apr = latest_run(session, ws_id, "apriori")
    rules = (apr.results.get("rules") if apr and apr.status == "ok" else None) or []
    sig = [r for r in rules if r["significant"]]
    return {
        "working": [r for r in sig if r["outcome"] == "high_performer"][:4],
        "underperforming": [r for r in sig if r["outcome"] == "low_performer"][:3],
    }


def build_overview(session: Session, ws, frame: pd.DataFrame) -> dict:
    if frame.empty:
        return {"status": "empty", "message": "No posts yet. Seed the demo workspace or import a CSV to begin.",
                "workspace": {"id": ws.id, "name": ws.name, "is_demo": ws.is_demo}}
    runs = latest_runs(session, ws.id)
    ok_runs = {a: r for a, r in runs.items() if r.status == "ok"}
    monthly = (frame.groupby("month").agg(posts=("post_id", "count"), engagement_rate=("engagement_rate", "mean"))
               .reset_index().sort_values("month"))
    by_plat = (frame.groupby(["month", "platform"])["engagement_rate"].mean().unstack("platform").reset_index().sort_values("month"))
    plat_median = frame.groupby("platform")["engagement_rate"].transform("median")
    idx = (frame["engagement_rate"] / plat_median)
    ranked = frame.assign(perf_index=idx).sort_values("perf_index", ascending=False)
    recent = ranked[ranked["published_at"] > frame["published_at"].max() - pd.Timedelta(days=120)]

    def card(r) -> dict:
        return {"post_id": int(r.post_id), "platform": r.platform, "format": r.format, "topic": r.topic, "hook": r.hook,
                "published_at": r.published_at.isoformat(), "engagement_rate": float(r.engagement_rate),
                "performance_index": float(r.perf_index), "caption_preview": (r.caption or "")[:110]}

    platform_rows = []
    for p, g in frame.groupby("platform"):
        platform_rows.append({"platform": p, "posts": int(len(g)), "engagement_rate": float(g["engagement_rate"].mean()),
                              "median_impressions": float(g["impressions"].median())})
    platform_rows.sort(key=lambda r: -r["posts"])

    etl = session.execute(select(EtlRun).where(EtlRun.workspace_id == ws.id).order_by(EtlRun.id.desc()).limit(1)).scalar_one_or_none()
    all_exps = exp_svc.list_experiments(session, ws.id)
    learnings = exp_svc.list_learnings(session, ws.id, 3)
    signals = _signal_cards(session, ws.id)
    mlr = ok_runs.get("multiple_linear_regression")

    suggestions = []
    for rule in signals["working"][:3]:
        suggestions.append({
            "title": " + ".join(rule["antecedent_labels"]),
            "basis": f"Top-quartile in {rule['n_hits']} of {rule['n_posts']} past posts ({rule['confidence'] * 100:.0f}% vs {rule['base_rate'] * 100:.0f}% baseline; "
                     f"lift {rule['lift']:.2f}, q={rule['q_value']:.3f}).",
            "antecedents": rule["antecedents"],
        })

    return {
        "status": "ok", "message": None,
        "workspace": {"id": ws.id, "name": ws.name, "is_demo": ws.is_demo},
        "data": {"posts": int(len(frame)), "first_post": frame["published_at"].min().isoformat(),
                 "last_post": frame["published_at"].max().isoformat(),
                 "last_etl": etl.started_at.isoformat() if etl else None},
        "kpis": {
            "avg_engagement_rate": float(frame["engagement_rate"].mean()),
            "median_impressions": float(frame["impressions"].median()),
            "total_impressions": int(frame["impressions"].sum()),
            "trend_30d": _window_compare(frame, 30), "trend_90d": _window_compare(frame, 90),
        },
        "trend": {"monthly": [{"month": r.month, "posts": int(r.posts), "engagement_rate": float(r.engagement_rate)} for r in monthly.itertuples()],
                  "by_platform": [{k: (None if (isinstance(v, float) and np.isnan(v)) else v) for k, v in rec.items()}
                                  for rec in by_plat.to_dict("records")]},
        "platforms": platform_rows,
        "top_posts": [card(r) for r in recent.head(5).itertuples()],
        "bottom_posts": [card(r) for r in recent.tail(5).iloc[::-1].itertuples()],
        "signals": signals, "suggested_tests": suggestions,
        "experiments": {"running": sum(e.status == "running" for e in all_exps), "completed": sum(e.status == "completed" for e in all_exps),
                        "recent": [exp_svc.serialize(e, detail=False) for e in all_exps[:3]]},
        "learnings": [{"id": lr.id, "statement": lr.statement, "verdict": lr.verdict, "created_at": lr.created_at.isoformat(),
                       "experiment_id": lr.experiment_id} for lr in learnings],
        "model_health": {
            "trained": len(ok_runs), "total": len(ALGORITHMS),
            "predictive_ready": mlr is not None,
            "runs": [{"algorithm": a, "status": r.status, "message": r.message, "created_at": r.created_at.isoformat(),
                      "headline": ({"label": HEADLINE_METRIC[a][1], "value": r.metrics.get(HEADLINE_METRIC[a][0])}
                                   if r.status == "ok" and r.metrics.get(HEADLINE_METRIC[a][0]) is not None else None)}
                     for a, r in runs.items()],
        },
    }
