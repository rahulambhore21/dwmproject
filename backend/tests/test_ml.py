import pytest

from app.ml.common import POST_PUBLICATION, PRE_PUBLICATION_FEATURES, LeakageError, assert_no_leakage, chrono_split, prepare
from app.ml.pipeline import ALGORITHMS, latest_run, train_all
from app.models import ModelRun, PostLabel, Workspace
from app.warehouse.frames import load_fact_frame


def test_leakage_guard_blocks_post_publication_fields():
    for bad in ("likes", "comments", "shares", "saves", "reach", "impressions", "engagement_rate"):
        with pytest.raises(LeakageError):
            assert_no_leakage(["platform", bad])
    with pytest.raises(LeakageError):
        assert_no_leakage(["totally_unknown"])
    assert_no_leakage(PRE_PUBLICATION_FEATURES)


def test_feature_set_has_no_post_publication_columns():
    assert not set(PRE_PUBLICATION_FEATURES) & POST_PUBLICATION


def test_chronological_split_has_no_overlap(seeded):
    s, ws = seeded
    df = prepare(load_fact_frame(s, ws.id))
    train, test = chrono_split(df)
    assert train["published_at"].max() <= test["published_at"].min()
    assert len(train) + len(test) == len(df)


def test_all_algorithms_stored_with_metrics(seeded):
    s, ws = seeded
    for algo in ALGORITHMS:
        run = latest_run(s, ws.id, algo)
        assert run is not None, algo
        assert run.status == "ok", (algo, run.message)
        assert run.metrics and run.dataset_hash and run.params is not None


def test_models_beat_naive_baseline_and_report_it(seeded):
    s, ws = seeded
    mlr = latest_run(s, ws.id, "multiple_linear_regression")
    assert mlr.metrics["r2"] > mlr.metrics["baseline_r2"]
    assert "r2_platform_adjusted" in mlr.metrics and "cv_r2_mean" in mlr.metrics
    assert set(mlr.features) == set(PRE_PUBLICATION_FEATURES)
    for algo in ("decision_tree", "gaussian_nb"):
        m = latest_run(s, ws.id, algo).metrics
        assert 0 <= m["roc_auc"] <= 1 and "baseline_accuracy" in m


def test_mutual_information_has_noise_floor(seeded):
    s, ws = seeded
    ranking = latest_run(s, ws.id, "mutual_information").results["ranking"]
    assert all("noise_floor_performance_index" in r for r in ranking)
    assert not {r["feature"] for r in ranking} & POST_PUBLICATION


def test_apriori_uses_multiple_testing_correction(seeded):
    s, ws = seeded
    run = latest_run(s, ws.id, "apriori")
    assert run.params["multiple_testing"] == "Benjamini-Hochberg"
    for r in run.results["rules"]:
        assert 0 <= r["q_value"] <= 1 and r["q_value"] >= r["p_value"] - 1e-12
        if r["significant"]:
            assert r["q_value"] < 0.10 and r["lift"] >= 1.2


def test_clusters_cover_all_posts(seeded):
    s, ws = seeded
    km = latest_run(s, ws.id, "kmeans")
    assert sum(c["n"] for c in km.results["clusters"]) == 720
    assert s.query(PostLabel).count() == 720


def test_retraining_is_noop_when_data_unchanged_and_reproducible_when_forced(seeded):
    s, ws = seeded
    before = s.query(ModelRun).count()
    train_all(s, ws.id)
    assert s.query(ModelRun).count() == before
    first = latest_run(s, ws.id, "multiple_linear_regression").metrics["r2"]
    train_all(s, ws.id, force=True)
    assert s.query(ModelRun).count() == before + len(ALGORITHMS)
    assert latest_run(s, ws.id, "multiple_linear_regression").metrics["r2"] == pytest.approx(first)


def test_insufficient_data_is_reported_not_faked(empty_session):
    from app.etl.pipeline import ingest_records

    s = empty_session
    ws = Workspace(name="tiny", slug="tiny")
    s.add(ws)
    s.commit()
    recs = [dict(external_id=f"T{i}", platform="X", format="Text", topic="a", hook_type="None", tone="Direct", caption="hello",
                 published_at="2026-01-05T09:00:00", impressions=500, reach=400, likes=10, comments=1, shares=1, saves=0)
            for i in range(10)]
    ingest_records(s, ws.id, recs, source="t")
    runs = train_all(s, ws.id)
    assert runs and all(r.status == "insufficient_data" for r in runs)
    assert all(not r.metrics for r in runs)
