"""Experiment engine: create, record observations, analyse, conclude, learn."""
from __future__ import annotations

from datetime import datetime
from typing import Any

import numpy as np
from pydantic import BaseModel, Field, field_validator, model_validator
from scipy import stats
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..clock import utcnow
from ..models import Experiment, ExperimentObservation, ExperimentVariant, Learning
from .common import ApiError

VARIABLES = ["format", "hook", "tone", "topic", "daypart", "caption_length", "has_question", "has_cta", "hashtags", "other"]
N_BOOT = 10000
ALPHA = 0.05
SEED = 42


class VariantIn(BaseModel):
    label: str = Field(min_length=1, max_length=8)
    description: str = Field(min_length=1, max_length=240)
    is_control: bool = False


class ExperimentIn(BaseModel):
    name: str = Field(min_length=3, max_length=160)
    hypothesis: str = Field(min_length=5, max_length=1000)
    variable: str
    platform: str = Field(min_length=1, max_length=32)
    variants: list[VariantIn] = Field(min_length=2, max_length=3)
    min_per_variant: int = Field(default=6, ge=3, le=100)
    randomized: bool = False
    source: str = Field(default="manual", max_length=32)
    prediction_snapshot: dict | None = None

    @field_validator("variable")
    @classmethod
    def _var(cls, v: str) -> str:
        if v not in VARIABLES:
            raise ValueError(f"variable must be one of {VARIABLES}")
        return v

    @model_validator(mode="after")
    def _one_control(self) -> ExperimentIn:
        controls = [v for v in self.variants if v.is_control]
        if len(controls) != 1:
            raise ValueError("exactly one variant must be the control")
        if len({v.label for v in self.variants}) != len(self.variants):
            raise ValueError("variant labels must be unique")
        return self


class ObservationIn(BaseModel):
    variant_id: int
    published_at: datetime
    impressions: int = Field(ge=1, le=1_000_000_000)
    engagements: int = Field(ge=0)
    saves: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _ok(self) -> ObservationIn:
        if self.engagements > self.impressions:
            raise ValueError("engagements cannot exceed impressions")
        if self.saves > self.engagements:
            raise ValueError("saves cannot exceed engagements")
        return self


def create_experiment(session: Session, workspace_id: int, payload: ExperimentIn) -> Experiment:
    exp = Experiment(
        workspace_id=workspace_id, name=payload.name, hypothesis=payload.hypothesis, variable=payload.variable,
        platform=payload.platform, min_per_variant=payload.min_per_variant, randomized=payload.randomized,
        source=payload.source, prediction_snapshot=payload.prediction_snapshot, status="running",
        variants=[ExperimentVariant(label=v.label, description=v.description, is_control=v.is_control) for v in payload.variants],
    )
    session.add(exp)
    session.commit()
    return get_experiment(session, workspace_id, exp.id)


def get_experiment(session: Session, workspace_id: int, experiment_id: int) -> Experiment:
    exp = session.execute(
        select(Experiment).options(selectinload(Experiment.variants).selectinload(ExperimentVariant.observations))
        .where(Experiment.id == experiment_id, Experiment.workspace_id == workspace_id)
    ).scalar_one_or_none()
    if exp is None:
        raise ApiError(404, "experiment_not_found", f"Experiment {experiment_id} not found.")
    return exp


def list_experiments(session: Session, workspace_id: int) -> list[Experiment]:
    return list(session.execute(
        select(Experiment).options(selectinload(Experiment.variants).selectinload(ExperimentVariant.observations))
        .where(Experiment.workspace_id == workspace_id).order_by(Experiment.created_at.desc(), Experiment.id.desc())
    ).scalars())


def add_observation(session: Session, workspace_id: int, experiment_id: int, payload: ObservationIn) -> Experiment:
    exp = get_experiment(session, workspace_id, experiment_id)
    if exp.status != "running":
        raise ApiError(409, "experiment_closed", "This experiment is completed; observations can no longer be added.")
    variant = next((v for v in exp.variants if v.id == payload.variant_id), None)
    if variant is None:
        raise ApiError(404, "variant_not_found", "Variant does not belong to this experiment.")
    variant.observations.append(ExperimentObservation(
        published_at=payload.published_at, impressions=payload.impressions, engagements=payload.engagements, saves=payload.saves))
    session.commit()
    return get_experiment(session, workspace_id, experiment_id)


def _rates(variant: ExperimentVariant) -> np.ndarray:
    return np.array([o.engagements / o.impressions for o in variant.observations], dtype=float)


def _bootstrap_diff_ci(a: np.ndarray, b: np.ndarray) -> tuple[float, float]:
    rng = np.random.default_rng(SEED)
    ia = rng.integers(0, len(a), size=(N_BOOT, len(a)))
    ib = rng.integers(0, len(b), size=(N_BOOT, len(b)))
    diffs = b[ib].mean(axis=1) - a[ia].mean(axis=1)
    lo, hi = np.quantile(diffs, [0.025, 0.975])
    return float(lo), float(hi)


def compare(control: ExperimentVariant, variant: ExperimentVariant, n_comparisons: int) -> dict:
    a, b = _rates(control), _rates(variant)
    out: dict = {"control": control.label, "variant": variant.label, "n_control": int(len(a)), "n_variant": int(len(b))}
    if len(a) < 2 or len(b) < 2:
        return {**out, "testable": False}
    mean_a, mean_b = float(a.mean()), float(b.mean())
    welch = stats.ttest_ind(b, a, equal_var=False)
    try:
        mw_p = float(stats.mannwhitneyu(b, a, alternative="two-sided").pvalue)
    except ValueError:
        mw_p = None
    lo, hi = _bootstrap_diff_ci(a, b)
    pooled_sd = float(np.sqrt((a.var(ddof=1) + b.var(ddof=1)) / 2))
    se = float(np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b)))
    p_adj = min(float(welch.pvalue) * n_comparisons, 1.0)  # Bonferroni across variant-vs-control comparisons
    return {
        **out, "testable": True, "mean_control": mean_a, "mean_variant": mean_b, "diff_pp": (mean_b - mean_a) * 100,
        "relative_lift_pct": (mean_b / mean_a - 1) * 100 if mean_a > 0 else None,
        "ci95_diff_pp": [lo * 100, hi * 100], "welch_p": float(welch.pvalue), "welch_p_adjusted": p_adj,
        "mann_whitney_p": mw_p, "cohens_d": float((mean_b - mean_a) / pooled_sd) if pooled_sd > 0 else None,
        "min_detectable_diff_pp": float((stats.norm.ppf(1 - ALPHA / 2) + stats.norm.ppf(0.8)) * se * 100),
        "significant": bool(p_adj < ALPHA and (lo > 0 or hi < 0)),
        "median_control": float(np.median(a)), "median_variant": float(np.median(b)),
    }


def analyze(exp: Experiment) -> dict:
    control = next(v for v in exp.variants if v.is_control)
    others = [v for v in exp.variants if not v.is_control]
    counts = {v.label: len(v.observations) for v in exp.variants}
    short = {k: n for k, n in counts.items() if n < exp.min_per_variant}
    comparisons = [compare(control, v, len(others)) for v in others]
    causal = (
        "Posts were assigned to variants at random, so a real difference can reasonably be attributed to the tested change (subject to sample size)."
        if exp.randomized else
        "Assignment was not randomised: other differences between posts (timing, audience mood, topic) may explain part of any gap."
    )
    base = {"counts": counts, "min_per_variant": exp.min_per_variant, "comparisons": comparisons,
            "randomized": exp.randomized, "causal_note": causal, "metric": exp.metric,
            "variant_summaries": [
                {"label": v.label, "description": v.description, "is_control": v.is_control, "n": len(v.observations),
                 "mean_engagement_rate": float(_rates(v).mean()) if v.observations else None,
                 "impressions": int(sum(o.impressions for o in v.observations))} for v in exp.variants]}
    if short:
        need = ", ".join(f"{k}: {counts[k]}/{exp.min_per_variant}" for k in short)
        return {**base, "verdict": "insufficient_data", "winner": None,
                "message": f"Not enough posts yet to conclude ({need})."}
    best = max((c for c in comparisons if c.get("significant") and c["diff_pp"] > 0), key=lambda c: c["diff_pp"], default=None)
    worse = [c for c in comparisons if c.get("significant") and c["diff_pp"] < 0]
    if best:
        return {**base, "verdict": "adopt", "winner": best["variant"], "message": None}
    if worse and len(worse) == len(comparisons):
        return {**base, "verdict": "keep_control", "winner": control.label, "message": None}
    return {**base, "verdict": "inconclusive", "winner": None, "message": None}


def prediction_check(exp: Experiment, analysis: dict) -> dict | None:
    snap = exp.prediction_snapshot or {}
    preds = snap.get("predicted_engagement_rate")
    if not preds:
        return None
    rows: list[dict[str, Any]] = []
    for v in exp.variants:
        if v.label in preds and v.observations:
            rows.append({"label": v.label, "predicted": float(preds[v.label]), "observed": float(_rates(v).mean())})
    if len(rows) < 2:
        return None
    pred_order = sorted(rows, key=lambda r: -r["predicted"])[0]["label"]
    obs_order = sorted(rows, key=lambda r: -r["observed"])[0]["label"]
    return {"rows": rows, "predicted_best": pred_order, "observed_best": obs_order, "direction_matched": pred_order == obs_order,
            "note": "A single experiment is one data point about model quality."}


def _fmt_pct(x: float) -> str:
    return f"{x * 100:.2f}%"


def learning_statement(exp: Experiment, analysis: dict) -> str:
    comps = analysis["comparisons"]
    c = next((c for c in comps if c.get("testable") and c["variant"] == analysis.get("winner")), comps[0] if comps else None)
    labels = {v.label: v.description for v in exp.variants}
    if analysis["verdict"] == "insufficient_data" or not c or not c.get("testable"):
        return f"Experiment '{exp.name}' did not collect enough posts to conclude."
    n_txt = f"n={c['n_variant']} vs {c['n_control']} posts"
    ci = c["ci95_diff_pp"]
    ci_txt = f"95% bootstrap interval for the difference {ci[0]:+.2f} to {ci[1]:+.2f} pp"
    caveat = "" if exp.randomized else " Assignment was not randomised, so this is suggestive rather than conclusive."
    where = f"On {exp.platform}, "
    if analysis["verdict"] == "adopt":
        return (f"{where}'{labels[c['variant']]}' outperformed '{labels[c['control']]}' on engagement rate "
                f"({_fmt_pct(c['mean_variant'])} vs {_fmt_pct(c['mean_control'])}; {n_txt}; {ci_txt}; adjusted p={c['welch_p_adjusted']:.3f}).{caveat}")
    if analysis["verdict"] == "keep_control":
        return (f"{where}'{labels[c['control']]}' did better than '{labels[c['variant']]}' "
                f"({_fmt_pct(c['mean_control'])} vs {_fmt_pct(c['mean_variant'])}; {n_txt}; {ci_txt}).{caveat}")
    return (f"{where}no reliable difference was detected between '{labels[c['control']]}' and '{labels[c['variant']]}' "
            f"({_fmt_pct(c['mean_control'])} vs {_fmt_pct(c['mean_variant'])}; {n_txt}; {ci_txt}). "
            f"With this sample the smallest difference we could reliably detect was about {c['min_detectable_diff_pp']:.2f} pp, "
            f"so a smaller real effect cannot be ruled out.")


def complete_experiment(session: Session, workspace_id: int, experiment_id: int, at: datetime | None = None) -> Experiment:
    exp = get_experiment(session, workspace_id, experiment_id)
    if exp.status == "completed":
        raise ApiError(409, "already_completed", "Experiment is already completed.")
    analysis = analyze(exp)
    if analysis["verdict"] == "insufficient_data":
        raise ApiError(422, "insufficient_data", analysis["message"])
    analysis["prediction_check"] = prediction_check(exp, analysis)
    exp.result = analysis
    exp.status = "completed"
    exp.completed_at = at or utcnow()
    session.add(Learning(
        workspace_id=workspace_id, experiment_id=exp.id, statement=learning_statement(exp, analysis),
        verdict=analysis["verdict"], evidence={"counts": analysis["counts"], "comparisons": analysis["comparisons"],
                                               "randomized": exp.randomized}, created_at=exp.completed_at))
    session.commit()
    return get_experiment(session, workspace_id, experiment_id)


def serialize(exp: Experiment, *, detail: bool = True) -> dict:
    analysis = exp.result if exp.status == "completed" and exp.result else analyze(exp)
    if analysis and "prediction_check" not in analysis:
        analysis = {**analysis, "prediction_check": prediction_check(exp, analysis)}
    data: dict[str, Any] = {
        "id": exp.id, "name": exp.name, "hypothesis": exp.hypothesis, "variable": exp.variable, "platform": exp.platform,
        "metric": exp.metric, "status": exp.status, "min_per_variant": exp.min_per_variant, "randomized": exp.randomized,
        "source": exp.source, "created_at": exp.created_at.isoformat(),
        "completed_at": exp.completed_at.isoformat() if exp.completed_at else None,
        "variants": [{"id": v.id, "label": v.label, "description": v.description, "is_control": v.is_control,
                      "n": len(v.observations)} for v in exp.variants],
        "analysis": analysis,
    }
    if detail:
        data["prediction_snapshot"] = exp.prediction_snapshot
        data["observations"] = [
            {"id": o.id, "variant_id": v.id, "variant_label": v.label, "published_at": o.published_at.isoformat(),
             "impressions": o.impressions, "engagements": o.engagements, "saves": o.saves,
             "engagement_rate": o.engagements / o.impressions}
            for v in exp.variants for o in v.observations]
        data["observations"].sort(key=lambda o: o["published_at"])
    return data


def list_learnings(session: Session, workspace_id: int, limit: int = 50) -> list[Learning]:
    return list(session.execute(
        select(Learning).where(Learning.workspace_id == workspace_id).order_by(Learning.created_at.desc(), Learning.id.desc()).limit(limit)
    ).scalars())
