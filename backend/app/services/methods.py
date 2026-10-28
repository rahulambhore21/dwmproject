"""Methods catalogue: how every algorithm and OLAP operation in SIGNAL is implemented.

Nothing here is hand-copied code. Source listings come from `inspect.getsource` on the live functions,
metrics come from the latest stored `model_runs` row, the star schema is read from the SQLAlchemy
metadata, and OLAP examples are executed against the current warehouse. If the code changes, this page changes.
"""
from __future__ import annotations

import inspect
from collections.abc import Callable
from pathlib import Path

import pandas as pd
from sqlalchemy.orm import Session

from ..db import Base
from ..etl import pipeline as etl_pipeline
from ..ml import association, classifiers, clustering, mutual_info, regression
from ..ml.common import PRE_PUBLICATION_FEATURES
from ..ml.pipeline import latest_runs
from ..olap import engine as olap
from ..warehouse import build as warehouse_build
from . import experiments, similarity

_APP_ROOT = Path(__file__).resolve().parents[1]

STAR_TABLES = ["fact_post", "dim_date", "dim_platform", "dim_format", "dim_topic", "dim_hook", "dim_tone", "dim_daypart"]


def _src(fn: Callable) -> dict:
    path = Path(inspect.getsourcefile(fn) or "").resolve()
    lines, start = inspect.getsourcelines(fn)
    return {"function": fn.__name__, "file": f"backend/app/{path.relative_to(_APP_ROOT).as_posix()}",
            "line": start, "code": "".join(lines).rstrip()}


def star_schema() -> dict:
    tables = []
    for name in STAR_TABLES:
        t = Base.metadata.tables[name]
        fks = {c.name: next(iter(c.foreign_keys)).target_fullname for c in t.columns if c.foreign_keys}
        tables.append({
            "name": name, "role": "fact" if name.startswith("fact_") else "dimension",
            "columns": [{"name": c.name, "type": str(c.type), "pk": c.primary_key, "references": fks.get(c.name)} for c in t.columns],
        })
    return {"grain": "One row in fact_post per published post.", "tables": tables}


def _olap_examples(frame: pd.DataFrame) -> list[dict]:
    """Canonical OLAP operations, parameterised from the live data and executed for real."""
    plats = list(frame["platform"].value_counts().index) if not frame.empty else []
    dayparts = list(frame["daypart"].value_counts().index) if not frame.empty else []
    specs: list[tuple[str, str, str, olap.OlapQuery]] = [
        ("Roll-up", "Aggregate up to a coarser level: every post collapses into one row per platform.",
         "rollup", olap.OlapQuery(rows=["platform"], measures=["posts", "engagement_rate", "median_engagement_rate"])),
        ("Drill-down", "Move to a finer level of the Channel hierarchy: platform splits into platform x format.",
         "drilldown", olap.OlapQuery(rows=["platform", "format"], measures=["posts", "engagement_rate"], limit=8)),
        ("Slice", "Fix one dimension to a single value and look at the rest.",
         "slice", olap.OlapQuery(rows=["format"], filters={"platform": plats[:1]}, measures=["posts", "engagement_rate"])),
        ("Dice", "Restrict several dimensions to value sets at once (a sub-cube).",
         "dice", olap.OlapQuery(rows=["topic"], filters={"platform": plats[:2], "daypart": dayparts[:2]}, measures=["posts", "engagement_rate"], limit=6)),
        ("Pivot", "Rotate a dimension onto the columns to compare it side by side.",
         "pivot", olap.OlapQuery(rows=["platform"], columns="daypart", measures=["engagement_rate", "posts"])),
        ("Roll-up with subtotals", "Detail rows plus a subtotal per platform (SQL ROLLUP).",
         "subtotals", olap.OlapQuery(rows=["platform", "format"], rollup=True, measures=["posts", "engagement_rate"], limit=40)),
    ]
    out = []
    for name, meaning, key, q in specs:
        entry = {"key": key, "name": name, "meaning": meaning, "query": q.model_dump(exclude_none=True), "sql": olap.to_sql(q),
                 "status": "empty", "preview": None}
        if len(frame):
            try:
                res = olap.run_query(frame, q)
            except ValueError:
                res = {"status": "empty"}
            entry["status"] = res["status"]
            if res["status"] == "ok":
                if res.get("pivot"):
                    p = res["pivot"]
                    entry["preview"] = {"kind": "pivot", "measure": p["measure"], "row_dimensions": p["row_dimensions"],
                                        "column_labels": p["column_labels"],
                                        "rows": [{"keys": r["keys"], "cells": [c["value"] if c else None for c in r["cells"]]} for r in p["rows"][:6]]}
                else:
                    entry["preview"] = {"kind": "table", "dimensions": res["dimensions"], "measures": res["measures"],
                                        "rows": [{"keys": r["keys"], "level": r["level"], **{m: r.get(m) for m in res["measures"]}} for r in res["rows"][:8]],
                                        "n_posts": res["n_posts"]}
        out.append(entry)
    return out


def _entry(key: str, name: str, group: str, summary: str, *, steps: list[str], why: str, guardrails: list[str], used_in: list[tuple[str, str]],
           functions: list[Callable], target: str | None = None, features: str | None = None, run=None) -> dict:
    d: dict = {
        "key": key, "name": name, "group": group, "summary": summary, "steps": steps, "why": why, "guardrails": guardrails,
        "target": target, "features": features, "used_in": [{"label": a, "href": b} for a, b in used_in],
        "source": [_src(f) for f in functions], "run": None,
    }
    if run is not None:
        d["run"] = {"status": run.status, "message": run.message, "metrics": run.metrics, "params": run.params,
                    "n_train": run.n_train, "n_test": run.n_test, "trained_at": run.created_at.isoformat(), "dataset_hash": run.dataset_hash[:12]}
    return d


def build_methods(session: Session, workspace_id: int, frame: pd.DataFrame) -> dict:
    runs = latest_runs(session, workspace_id)
    leakage_tail = "Pre-publication features only; `assert_no_leakage` raises before fitting if a post-publication field slips in."
    algos = [
        _entry("etl", "ETL", "Data warehousing",
               "Validates raw records, stages them in `posts`, then rebuilds the star schema. Every rejection is counted and reported.",
               steps=["Parse each raw record into `RawPostIn` (Pydantic): types, ranges, stripped strings.",
                      "Cross-field rules: engagements <= impressions, reach <= impressions, no future timestamps.",
                      "Reject duplicates by `external_id`; count every rejection by reason.",
                      "Load valid rows into the staging table, then call `build_warehouse`.",
                      "Write an `etl_runs` row with rows in / loaded / rejected."],
               why="Analytics are only as trustworthy as the load. Rejecting and counting bad rows is better than silently imputing them.",
               guardrails=["Nothing is silently dropped or imputed.", "Batch size is capped to bound memory."],
               used_in=[("Explore → Models & data", "/explore?tab=models")], functions=[etl_pipeline.RawPostIn, etl_pipeline.ingest_records]),
        _entry("warehouse", "Dimensional warehouse", "Data warehousing",
               "Staging rows become a star schema: one fact row per post, surrounded by conformed dimensions.",
               steps=["Derive text features from each caption (length, hashtags, emoji, question, CTA).",
                      "Compute measures: engagements, engagement / save / share / comment rates.",
                      "Look up or insert each dimension member and capture its surrogate key.",
                      "Insert `dim_date` rows keyed `yyyymmdd`, then bulk-insert `fact_post`."],
               why="A star schema makes slicing by any dimension a join + group-by and keeps rates computed once, consistently.",
               guardrails=["Idempotent: the workspace's facts are deleted and rebuilt, never duplicated.",
                           "Measures are stored apart from pre-publication attributes so models can't confuse them."],
               used_in=[("Explore → OLAP pivot", "/explore?tab=pivot")], functions=[warehouse_build.build_warehouse]),
        _entry("olap", "OLAP engine", "Data warehousing",
               "Roll-up, drill-down, slice, dice, pivot and subtotals over the star schema, with sample sizes and 95% intervals on every cell.",
               steps=["Validate the request (`OlapQuery`): whitelisted dimensions and measures only.",
                      "Slice / dice: filter the fact frame with `IN` sets per dimension.",
                      "Group by the row dimensions and aggregate each measure (mean of per-post rates, so each post counts once).",
                      "Attach a t-based 95% interval and flag cells below the low-sample threshold.",
                      "Roll-up: add subtotal rows per prefix of the row hierarchy. Pivot: group by rows + column dimension."],
               why="Aggregating per-post rates (not ratio-of-sums) stops one viral post from dominating a cell; intervals stop thin cells being over-read.",
               guardrails=["Cells with fewer than 8 posts are flagged.", "Dimension and measure names are whitelisted, never interpolated."],
               used_in=[("Explore → OLAP pivot", "/explore?tab=pivot"), ("Overview", "/")], functions=[olap.run_query, olap._aggregate, olap._finish]),
        _entry("linear_regression", "Linear regression", "Predictive",
               "One predictor (caption length) against log engagement rate, with slope, confidence interval and p-value.",
               steps=["Chronological 80/20 split: train on the past, test on the future.",
                      "Ordinary least squares via `scipy.stats.linregress` on the training period.",
                      "Report slope, Pearson r, p-value and a 95% interval for the slope.",
                      "Score the held-out period and compare R² with a predict-the-mean baseline."],
               why="The simplest possible model is the honest baseline: if multiple regression can't beat it, the extra features aren't earning their place.",
               guardrails=["A straight line can't express an optimum length; the result is labelled a descriptive baseline.", leakage_tail],
               used_in=[("Explore → Drivers", "/explore?tab=drivers")], functions=[regression.simple_linear_regression],
               target="log engagement rate", features="caption_length", run=runs.get("linear_regression")),
        _entry("multiple_linear_regression", "Multiple linear regression", "Predictive",
               "All pre-publication features together; coefficients are exponentiated into 'x% higher / lower' effects with p-values.",
               steps=["One-hot encode categoricals (first level dropped as reference); standardise numerics.",
                      "Fit `LinearRegression` on the training period (chronological split).",
                      "Compute standard errors and p-values from the OLS covariance (`pinv(X'X)`).",
                      "Evaluate on the future slice, plus 5-fold `TimeSeriesSplit` cross-validation.",
                      "Report a platform-adjusted R² so platform baselines don't flatter the fit."],
               why="Adjusts each feature for the others, so 'Reels do better' isn't just 'Reels are posted on Instagram'.",
               guardrails=["Coefficients are associations, not causal effects.", leakage_tail],
               used_in=[("Pre-Publish Lab", "/lab"), ("Explore → Drivers", "/explore?tab=drivers")], functions=[regression.multiple_linear_regression, regression._ols_inference],
               target="log engagement rate", features=", ".join(PRE_PUBLICATION_FEATURES), run=runs.get("multiple_linear_regression")),
        _entry("mutual_information", "Mutual information", "Predictive",
               "Ranks which attributes carry any statistical dependence with performance, linear or not.",
               steps=["Ordinal-encode categoricals; mark discrete vs continuous features.",
                      "Estimate MI against platform-relative log engagement (regression form) and against high-performer (classification form).",
                      "Shuffle the target 20 times to build a null distribution; take its 95th percentile as the noise floor.",
                      "Flag a feature only if it clears the noise floor."],
               why="Correlation misses non-linear and categorical structure. The shuffle floor stops tiny MI values being read as signal.",
               guardrails=["Exploratory over the whole history, not a predictive evaluation.", "MI is dependence, not cause."],
               used_in=[("Explore → Drivers", "/explore?tab=drivers")], functions=[mutual_info.mutual_information],
               target="platform-adjusted log engagement", features=", ".join(mutual_info.MI_FEATURES), run=runs.get("mutual_information")),
        _entry("decision_tree", "Decision tree", "Predictive",
               "Readable if-then rules for 'lands in the top quartile of its platform', with hit-rates confirmed on held-out posts.",
               steps=["Label high performers using per-platform 75th-percentile thresholds computed from the training period only.",
                      "Fit a depth-4 `DecisionTreeClassifier` (min 20 per leaf, balanced class weights).",
                      "Walk the tree to extract each leaf as a plain-English rule.",
                      "Measure each rule's hit-rate on the unweighted training labels and on the held-out period."],
               why="Rules are inspectable and explainable. Depth and leaf-size limits keep them from memorising noise.",
               guardrails=["Thresholds come from the past only (no label leakage).", "Rules describe history, not causes.", leakage_tail],
               used_in=[("Pre-Publish Lab", "/lab"), ("Explore → Drivers", "/explore?tab=drivers")], functions=[classifiers.decision_tree, classifiers._extract_rules],
               target="high performer (top quartile of platform)", features=", ".join(classifiers.TREE_FEATURES), run=runs.get("decision_tree")),
        _entry("gaussian_nb", "Gaussian Naive Bayes", "Predictive",
               "Probability that a draft becomes a high performer, calibrated so '60%' means roughly 60%.",
               steps=["Same labels and chronological split as the tree.",
                      "Standardise features and fit `GaussianNB` (class prior x per-feature Gaussian likelihoods).",
                      "Wrap in 5-fold sigmoid `CalibratedClassifierCV` because the independence assumption makes raw probabilities extreme.",
                      "Check calibration: mean predicted probability against the observed rate."],
               why="A fast probabilistic model with a different bias from the tree; agreement between them is more informative than either alone.",
               guardrails=["Reports accuracy against the majority-class baseline.", leakage_tail],
               used_in=[("Pre-Publish Lab", "/lab")], functions=[classifiers.gaussian_nb],
               target="high performer (top quartile of platform)", features=", ".join(PRE_PUBLICATION_FEATURES), run=runs.get("gaussian_nb")),
        _entry("kmeans", "K-Means clustering", "Descriptive",
               "Groups posts into archetypes by how they performed (engagement, saves, shares, comments, reach).",
               steps=["Log-transform five performance rates and standardise them.",
                      "Fit K-Means for k = 3..6 with 10 restarts; pick k by silhouette score.",
                      "Name each cluster from its dominant standardised centroid dimension.",
                      "List attributes that are over-represented in each cluster (lift >= 1.3, at least 8 posts)."],
               why="Archetypes show the distinct ways a post can succeed (shareable vs reference-worthy), which one average hides.",
               guardrails=["Uses post-publication performance, so it is descriptive only and never feeds prediction."],
               used_in=[("Content Memory", "/memory"), ("Explore → Segments", "/explore?tab=segments")], functions=[clustering.kmeans_archetypes, clustering._name_clusters],
               target=None, features=", ".join(clustering.PROFILE), run=runs.get("kmeans")),
        _entry("agglomerative", "Agglomerative clustering", "Descriptive",
               "Hierarchical clustering of platform x format x topic segments into families with similar relative performance.",
               steps=["Make performance platform-relative by subtracting each platform's mean.",
                      "Aggregate to segments (platform x format x topic); keep those with >= 6 posts.",
                      "Ward-linkage `AgglomerativeClustering` for k = 2..5; choose k by silhouette.",
                      "Report each family's members and mean relative engagement."],
               why="Clusters content strategies rather than individual posts; Ward linkage favours compact, comparable families.",
               guardrails=["Needs at least 8 qualifying segments, otherwise records `insufficient_data`.", "Descriptive only."],
               used_in=[("Explore → Segments", "/explore?tab=segments")], functions=[clustering.agglomerative_segments],
               target=None, features=", ".join(clustering.PROFILE), run=runs.get("agglomerative")),
        _entry("apriori", "Apriori association rules", "Descriptive",
               "Finds attribute combinations that co-occur with top- or bottom-quartile posts, corrected for multiple testing.",
               steps=["Turn every post into a transaction of boolean items (platform=..., caption=short, has_cta, ...).",
                      "Mine frequent itemsets with `mlxtend.apriori` (min support 3%, up to 3 items).",
                      "Derive rules `{attributes} -> high/low performer` with support, confidence and lift.",
                      "Fisher exact test per rule, then Benjamini-Hochberg across all candidates (FDR 10%)."],
               why="Mining thousands of candidate rules guarantees some look good by chance; the FDR step is what makes the survivors worth a look.",
               guardrails=["'Significant' means q < 0.10, not proof of cause.", "Rules need at least 12 matching posts and lift >= 1.2."],
               used_in=[("Overview", "/"), ("Explore → Drivers", "/explore?tab=drivers")], functions=[association.apriori_rules, association.build_items, association._bh],
               target=None, features="boolean attribute items", run=runs.get("apriori")),
        _entry("similarity", "Similarity search", "Retrieval",
               "Finds the past posts most like a draft by blending caption text similarity with attribute overlap.",
               steps=["Fit a TF-IDF vectoriser (1-2 grams, English stop words, sublinear tf) over all captions; cache per dataset hash.",
                      "Cosine similarity between the draft caption and every past caption.",
                      "Attribute overlap: share of platform / format / topic / hook / tone that match.",
                      "Score = 0.7 x text + 0.3 x attributes; return the top k with their performance vs platform median."],
               why="Concrete precedents are easier to trust than a model score, and they can be inspected.",
               guardrails=["Needs at least 15 posts.", "Neighbours show what happened, not what will happen."],
               used_in=[("Pre-Publish Lab", "/lab"), ("Content Autopsy", "/memory")], functions=[similarity._index, similarity.find_similar]),
        _entry("experiments", "Experiment comparison", "Experimentation",
               "Compares a variant to the control with Welch's t-test, Mann-Whitney, a bootstrap interval and an effect size.",
               steps=["Per-post engagement rates for each variant.",
                      "Welch's t-test (unequal variances), Bonferroni-adjusted across variant-vs-control comparisons.",
                      "Mann-Whitney U as a distribution-free cross-check.",
                      "10,000-resample bootstrap 95% interval for the difference in means (fixed seed).",
                      "Cohen's d and the minimum detectable difference at 80% power; verdict only once every variant has enough posts."],
               why="Small samples and heavy-tailed rates make a single t-test fragile; agreement across tests is the evidence.",
               guardrails=["Verdict is 'insufficient data' until the minimum per variant is met.",
                           "Causal wording appears only if assignment was randomised."],
               used_in=[("Experiments", "/experiments"), ("Learning", "/learning")], functions=[experiments.compare, experiments._bootstrap_diff_ci, experiments.analyze]),
    ]
    return {
        "has_data": bool(len(frame)), "n_posts": int(len(frame)),
        "star_schema": star_schema(),
        "olap": {"dimensions": olap.schema()["dimensions"], "hierarchies": olap.schema()["hierarchies"],
                 "measures": olap.schema()["measures"], "examples": _olap_examples(frame),
                 "note": ("The engine executes these groupings with pandas over the fact frame, which is itself the star join "
                          "(see `load_fact_frame`). The SQL shown is generated from the same query object and is what a SQL engine would run.")},
        "algorithms": algos,
    }
