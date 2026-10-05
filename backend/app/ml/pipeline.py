"""Orchestrates training; every run's metrics, params and results are persisted in `model_runs`."""
from __future__ import annotations

import logging
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

import joblib
import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import ModelRun, PostLabel
from ..warehouse.frames import dataset_hash, load_fact_frame
from .association import apriori_rules
from .classifiers import decision_tree, gaussian_nb
from .clustering import agglomerative_segments, kmeans_archetypes
from .common import ModelOutcome, label_performance, platform_thresholds, prepare
from .mutual_info import mutual_information
from .regression import multiple_linear_regression, simple_linear_regression

log = logging.getLogger("signal.ml")

TRAINERS: list[tuple[str, str, Callable[[pd.DataFrame], ModelOutcome]]] = [
    ("linear_regression", "regression", simple_linear_regression),
    ("multiple_linear_regression", "regression", multiple_linear_regression),
    ("mutual_information", "ranking", mutual_information),
    ("decision_tree", "classification", decision_tree),
    ("gaussian_nb", "classification", gaussian_nb),
    ("kmeans", "clustering", kmeans_archetypes),
    ("agglomerative", "clustering", agglomerative_segments),
    ("apriori", "association", apriori_rules),
]
ALGORITHMS = [t[0] for t in TRAINERS]


def latest_run(session: Session, workspace_id: int, algorithm: str) -> ModelRun | None:
    return session.execute(
        select(ModelRun).where(ModelRun.workspace_id == workspace_id, ModelRun.algorithm == algorithm)
        .order_by(ModelRun.id.desc()).limit(1)
    ).scalar_one_or_none()


def latest_runs(session: Session, workspace_id: int) -> dict[str, ModelRun]:
    runs = {}
    for algo in ALGORITHMS:
        r = latest_run(session, workspace_id, algo)
        if r:
            runs[algo] = r
    return runs


@lru_cache(maxsize=32)
def _load(path: str):
    return joblib.load(path)


def load_artifact(run: ModelRun | None):
    if run is None or not run.artifact_path or not Path(run.artifact_path).exists():
        return None
    return _load(run.artifact_path)


def train_all(session: Session, workspace_id: int, force: bool = False) -> list[ModelRun]:
    settings = get_settings()
    frame = load_fact_frame(session, workspace_id)
    digest = dataset_hash(frame)
    runs: list[ModelRun] = []

    if len(frame) < settings.min_posts_for_models:
        msg = f"{len(frame)} posts available; at least {settings.min_posts_for_models} are required to train reliable models."
        for algo, task, _ in TRAINERS:
            prev = latest_run(session, workspace_id, algo)
            if prev and prev.dataset_hash == digest and prev.status == "insufficient_data":
                runs.append(prev)
                continue
            run = ModelRun(workspace_id=workspace_id, algorithm=algo, task=task, dataset_hash=digest,
                           status="insufficient_data", message=msg, n_train=len(frame))
            session.add(run)
            runs.append(run)
        session.commit()
        return runs

    df = prepare(frame)
    df = label_performance(df, platform_thresholds(df))
    for algo, task, trainer in TRAINERS:
        prev = latest_run(session, workspace_id, algo)
        # Artifacts live on local disk (ephemeral on Railway); a stored run whose file is gone must be retrained.
        artifact_missing = bool(prev and prev.status == "ok" and prev.artifact_path and not Path(prev.artifact_path).exists())
        if prev and not force and not artifact_missing and prev.dataset_hash == digest and prev.status in ("ok", "insufficient_data"):
            runs.append(prev)
            continue
        try:
            out = trainer(df)
        except Exception as exc:  # recorded, never swallowed
            log.exception("trainer %s failed", algo)
            out = ModelOutcome(algo, task, None, [], {}, {}, {}, len(df), 0, status="failed", message=f"{type(exc).__name__}: {exc}")
        labels = out.results.pop("labels", None)
        run = ModelRun(
            workspace_id=workspace_id, algorithm=out.algorithm, task=out.task, target=out.target, features=out.features,
            params=out.params, metrics=out.metrics, results=out.results, n_train=out.n_train, n_test=out.n_test,
            dataset_hash=digest, status=out.status, message=out.message,
        )
        session.add(run)
        session.flush()
        if out.artifact is not None:
            path = get_settings().artifacts_dir / f"ws{workspace_id}_{out.algorithm}_{run.id}.joblib"
            path.parent.mkdir(parents=True, exist_ok=True)
            joblib.dump(out.artifact, path)
            run.artifact_path = str(path)
        if labels:
            session.execute(delete(PostLabel))
            session.add_all(PostLabel(post_id=pid, run_id=run.id, archetype=lab) for pid, lab in labels.items())
        runs.append(run)
    session.commit()
    return runs
