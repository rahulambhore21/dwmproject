from datetime import datetime, timedelta

import numpy as np
import pytest
from pydantic import ValidationError

from app.models import Experiment, ExperimentObservation, ExperimentVariant
from app.services import ai, evidence, overview, prediction
from app.services import experiments as E
from app.services.common import ApiError
from app.services.similarity import find_similar
from app.warehouse.frames import load_fact_frame

DRAFT = dict(platform="LinkedIn", format="Carousel", topic="Education", hook="Numbered list", tone="Authoritative",
             caption="5 things we learned about A/B testing basics. Save this for later. #data",
             scheduled_at=datetime(2026, 10, 6, 8, 0))


# ---------------------------------------------------------------- prediction
def test_prediction_is_bounded_and_explained(seeded):
    s, ws = seeded
    frame = load_fact_frame(s, ws.id)
    res = prediction.predict(s, ws.id, frame, prediction.Draft(**DRAFT))
    assert res["status"] == "ok"
    p = res["prediction"]
    lo, hi = p["interval_80"]
    assert 0 < lo < p["engagement_rate"] < hi < 1
    assert "platform" not in {c["feature"] for c in p["contributions"]}
    assert 0 <= p["probability_top_quartile"]["blend"] <= 1
    assert res["model"]["n_test"] > 0 and res["caveats"]
    assert res["similar"]["status"] == "ok" and len(res["similar"]["neighbors"]) == 5


def test_prediction_uses_only_pre_publication_inputs():
    names = set(prediction.draft_frame(prediction.Draft(**DRAFT)).columns)
    from app.ml.common import POST_PUBLICATION

    assert not names & POST_PUBLICATION


def test_prediction_is_deterministic(seeded):
    s, ws = seeded
    frame = load_fact_frame(s, ws.id)
    a = prediction.predict(s, ws.id, frame, prediction.Draft(**DRAFT))
    b = prediction.predict(s, ws.id, frame, prediction.Draft(**DRAFT))
    assert a["prediction"] == b["prediction"]


def test_prediction_rejects_unknown_values_and_blank_caption(seeded):
    s, ws = seeded
    frame = load_fact_frame(s, ws.id)
    res = prediction.predict(s, ws.id, frame, prediction.Draft(**{**DRAFT, "platform": "Bluesky"}))
    assert res["status"] == "invalid"
    with pytest.raises(ValidationError):
        prediction.Draft(**{**DRAFT, "caption": "   "})


def test_prediction_insufficient_without_models(empty_session):
    import pandas as pd

    res = prediction.predict(empty_session, 1, pd.DataFrame(), prediction.Draft(**DRAFT))
    assert res["status"] == "insufficient_data"


def test_similarity_excludes_self_and_ranks(seeded):
    s, ws = seeded
    frame = load_fact_frame(s, ws.id)
    row = frame.iloc[10]
    res = find_similar(s, ws.id, frame, caption=row["caption"], attrs={"platform": row["platform"], "format": row["format"]},
                       k=5, exclude_post_id=int(row["post_id"]))
    ids = [n["post_id"] for n in res["neighbors"]]
    assert int(row["post_id"]) not in ids
    sims = [n["similarity"] for n in res["neighbors"]]
    assert sims == sorted(sims, reverse=True)


def test_overview_numbers_trace_to_data(seeded):
    s, ws = seeded
    frame = load_fact_frame(s, ws.id)
    o = overview.build_overview(s, ws, frame)
    assert o["data"]["posts"] == len(frame)
    assert o["kpis"]["avg_engagement_rate"] == pytest.approx(frame["engagement_rate"].mean())
    assert o["model_health"]["predictive_ready"] is True


# --------------------------------------------------------------- experiments
def _variant(label, rates, control=False, imp=10000):
    v = ExperimentVariant(label=label, description=f"variant {label}", is_control=control)
    v.observations = [ExperimentObservation(published_at=datetime(2026, 1, 1) + timedelta(days=i), impressions=imp,
                                            engagements=int(r * imp), saves=0) for i, r in enumerate(rates)]
    return v


def _exp(a_rates, b_rates, randomized=True):
    e = Experiment(name="t", hypothesis="h", variable="hook", platform="Instagram", min_per_variant=6, randomized=randomized)
    e.variants = [_variant("A", a_rates, True), _variant("B", b_rates)]
    return e


def test_experiment_detects_real_difference():
    rng = np.random.default_rng(1)
    a = rng.normal(0.05, 0.004, 12).clip(0.01)
    b = rng.normal(0.07, 0.004, 12).clip(0.01)
    res = E.analyze(_exp(a, b))
    assert res["verdict"] == "adopt" and res["winner"] == "B"
    c = res["comparisons"][0]
    assert c["ci95_diff_pp"][0] > 0 and c["welch_p_adjusted"] < 0.05


def test_experiment_inconclusive_when_no_difference_and_reports_power():
    rng = np.random.default_rng(2)
    a = rng.normal(0.05, 0.01, 10).clip(0.01)
    b = rng.normal(0.05, 0.01, 10).clip(0.01)
    res = E.analyze(_exp(a, b))
    assert res["verdict"] == "inconclusive"
    assert res["comparisons"][0]["min_detectable_diff_pp"] > 0


def test_experiment_insufficient_data_blocks_conclusion():
    res = E.analyze(_exp([0.05, 0.06], [0.07, 0.08]))
    assert res["verdict"] == "insufficient_data" and "Not enough" in res["message"]


def test_experiment_bootstrap_is_reproducible():
    rng = np.random.default_rng(3)
    a, b = rng.normal(0.05, 0.01, 9), rng.normal(0.06, 0.01, 9)
    assert E.analyze(_exp(a, b))["comparisons"][0]["ci95_diff_pp"] == E.analyze(_exp(a, b))["comparisons"][0]["ci95_diff_pp"]


def test_causal_language_depends_on_randomisation():
    a, b = [0.05] * 8, [0.06] * 8
    assert "random" in E.analyze(_exp(a, b, True))["causal_note"].lower()
    assert "not randomised" in E.analyze(_exp(a, b, False))["causal_note"]


def test_experiment_input_validation():
    base = dict(name="Test exp", hypothesis="because reasons", variable="hook", platform="X",
                variants=[dict(label="A", description="a", is_control=True), dict(label="B", description="b")])
    E.ExperimentIn(**base)
    with pytest.raises(ValidationError):
        E.ExperimentIn(**{**base, "variable": "astrology"})
    with pytest.raises(ValidationError):
        E.ExperimentIn(**{**base, "variants": [dict(label="A", description="a"), dict(label="B", description="b")]})
    with pytest.raises(ValidationError):
        E.ObservationIn(variant_id=1, published_at=datetime(2026, 1, 1), impressions=100, engagements=200)


def test_experiment_lifecycle(seeded):
    s, ws = seeded
    exp = E.create_experiment(s, ws.id, E.ExperimentIn(
        name="Lifecycle", hypothesis="B beats A on average", variable="hook", platform="X", min_per_variant=3,
        variants=[E.VariantIn(label="A", description="a", is_control=True), E.VariantIn(label="B", description="b")]))
    with pytest.raises(ApiError) as err:
        E.complete_experiment(s, ws.id, exp.id)
    assert err.value.status == 422
    for i in range(3):
        for v, rate in zip(exp.variants, (0.02, 0.05), strict=True):
            E.add_observation(s, ws.id, exp.id, E.ObservationIn(
                variant_id=v.id, published_at=datetime(2026, 9, 1 + i), impressions=10000, engagements=int(10000 * rate * (1 + i * 0.02))))
    done = E.complete_experiment(s, ws.id, exp.id)
    assert done.status == "completed" and done.result["verdict"] in {"adopt", "inconclusive"}
    assert any(lr.experiment_id == exp.id for lr in E.list_learnings(s, ws.id))
    with pytest.raises(ApiError) as err2:
        E.add_observation(s, ws.id, exp.id, E.ObservationIn(variant_id=exp.variants[0].id, published_at=datetime(2026, 9, 9),
                                                           impressions=100, engagements=1))
    assert err2.value.status == 409


def test_seeded_experiments_cover_all_states(seeded):
    s, ws = seeded
    verdicts = {E.serialize(e, detail=False)["analysis"]["verdict"] for e in E.list_experiments(s, ws.id)}
    assert "insufficient_data" in verdicts and len(verdicts) >= 2


# ------------------------------------------------------------------------ AI
def test_validator_rejects_invented_numbers_ids_and_causation():
    ev = [{"id": "E1", "label": "x", "text": "Mean engagement 5.20% (n=40), lift 1.30.", "numbers": [5.2, 40, 1.3], "n": 40}]
    ok = [{"text": "Engagement was 5.2% across 40 posts.", "evidence_ids": ["E1"]}]
    assert ai.validate(ok, ev) is None
    assert "not found" in ai.validate([{"text": "Engagement was 9.9%.", "evidence_ids": ["E1"]}], ev)
    assert "evidence ids" in ai.validate([{"text": "Engagement was 5.2%.", "evidence_ids": ["E9"]}], ev)
    assert "evidence ids" in ai.validate([{"text": "Engagement was 5.2%.", "evidence_ids": []}], ev)
    assert "causal" in ai.validate([{"text": "Hooks cause 5.2% more engagement.", "evidence_ids": ["E1"]}], ev)
    assert "causal" in ai.validate([{"text": "This will increase reach.", "evidence_ids": ["E1"]}], ev)


def test_deterministic_statements_pass_the_same_validator(seeded):
    s, ws = seeded
    frame = load_fact_frame(s, ws.id)
    ev, st = evidence.overview_evidence(overview.build_overview(s, ws, frame))
    assert st and ai.validate(st, ev) is None
    res = prediction.predict(s, ws.id, frame, prediction.Draft(**DRAFT))
    ev, st = evidence.prediction_evidence(res)
    assert ai.validate(st, ev) is None


def test_interpret_without_key_is_deterministic_and_labelled(seeded):
    s, ws = seeded
    frame = load_fact_frame(s, ws.id)
    ev, st = evidence.overview_evidence(overview.build_overview(s, ws, frame))
    out = ai.interpret("overview", ev, st)
    assert out["source"] == "deterministic" and out["statements"] and "associations" in out["disclaimer"]
    empty = ai.interpret("overview", [], [])
    assert empty["statements"] == []
