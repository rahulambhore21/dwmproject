"""HTTP API. Thin: validation + delegation to services (all analytics live outside the routers)."""
from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_session
from ..etl.pipeline import REQUIRED_COLUMNS, ingest_records
from ..ml.pipeline import ALGORITHMS, latest_run, latest_runs, train_all
from ..models import EtlRun, ModelRun
from ..olap import engine as olap
from ..services import ai, autopsy, evidence, overview, prediction, similarity
from ..services import experiments as exp_svc
from ..services.common import ApiError, Context, get_context
from ..warehouse.frames import load_fact_frame

router = APIRouter(prefix="/api")
Session_ = Annotated[Session, Depends(get_session)]


def ctx(session: Session_) -> Context:
    return get_context(session)


Ctx = Annotated[Context, Depends(ctx)]


@router.get("/health")
def health(session: Session_) -> dict:
    ws = None
    n = 0
    try:
        from ..models import Workspace

        ws = session.execute(select(Workspace).limit(1)).scalar_one_or_none()
        if ws:
            n = len(load_fact_frame(session, ws.id))
    except Exception as exc:  # pragma: no cover - surfaced to the client
        return {"status": "degraded", "error": str(exc)}
    return {"status": "ok" if ws and n else "empty", "workspace": ws.name if ws else None, "posts": n,
            "llm_configured": bool(ai.get_settings().anthropic_api_key)}


@router.get("/overview")
def get_overview(c: Ctx) -> dict:
    return overview.build_overview(c.session, c.workspace, c.frame)


@router.get("/vocabulary")
def get_vocabulary(c: Ctx) -> dict:
    return prediction.vocabulary(c.frame)


class PostQuery(BaseModel):
    platform: str | None = None
    format: str | None = None
    topic: str | None = None
    hook: str | None = None
    tone: str | None = None
    search: str | None = Field(default=None, max_length=100)
    sort: Literal["published_at", "engagement_rate", "impressions", "perf_index"] = "published_at"
    order: Literal["asc", "desc"] = "desc"
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=25, ge=1, le=100)


@router.get("/posts")
def list_posts(c: Ctx, q: Annotated[PostQuery, Query()]) -> dict:
    if c.frame.empty:
        return {"total": 0, "page": 1, "page_size": q.page_size, "items": []}
    params = q.model_dump()
    if params["sort"] == "perf_index":
        params["sort"] = "perf_index"
    return autopsy.list_posts(c.frame, q=params)


@router.get("/posts/{post_id}/autopsy")
def post_autopsy(post_id: int, c: Ctx) -> dict:
    return autopsy.build_autopsy(c.session, c.workspace.id, c.frame, post_id)


@router.post("/lab/predict")
def lab_predict(draft: prediction.Draft, c: Ctx) -> dict:
    if c.frame.empty:
        raise ApiError(409, "no_data", "No history to learn from yet.")
    result = prediction.predict(c.session, c.workspace.id, c.frame, draft)
    if result["status"] == "invalid":
        raise ApiError(422, "invalid_draft", result["message"])
    return result


class SimilarityQuery(BaseModel):
    caption: str = Field(min_length=1, max_length=5000)
    platform: str | None = None
    format: str | None = None
    topic: str | None = None
    hook: str | None = None
    tone: str | None = None
    k: int = Field(default=5, ge=1, le=20)


@router.post("/similarity/search")
def similarity_search(body: SimilarityQuery, c: Ctx) -> dict:
    attrs = {k: v for k, v in body.model_dump(include={"platform", "format", "topic", "hook", "tone"}).items() if v}
    return similarity.find_similar(c.session, c.workspace.id, c.frame, caption=body.caption, attrs=attrs, k=body.k)


@router.get("/olap/schema")
def olap_schema() -> dict:
    return olap.schema()


@router.post("/olap/query")
def olap_query(q: olap.OlapQuery, c: Ctx) -> dict:
    try:
        return olap.run_query(c.frame, q)
    except ValueError as exc:
        raise ApiError(422, "invalid_query", str(exc)) from exc


def _run_json(r: ModelRun, full: bool) -> dict:
    d = {"id": r.id, "algorithm": r.algorithm, "task": r.task, "target": r.target, "status": r.status, "message": r.message,
         "metrics": r.metrics, "params": r.params, "features": r.features, "n_train": r.n_train, "n_test": r.n_test,
         "dataset_hash": r.dataset_hash, "created_at": r.created_at.isoformat()}
    if full:
        d["results"] = r.results
    return d


@router.get("/models")
def list_models(c: Ctx) -> dict:
    runs = latest_runs(c.session, c.workspace.id)
    total_runs = len(c.session.execute(select(ModelRun.id).where(ModelRun.workspace_id == c.workspace.id)).all())
    return {"algorithms": ALGORITHMS, "runs": [_run_json(r, False) for r in runs.values()], "total_runs_stored": total_runs}


@router.get("/models/{algorithm}")
def get_model(algorithm: str, c: Ctx) -> dict:
    if algorithm not in ALGORITHMS:
        raise ApiError(404, "unknown_algorithm", f"Unknown algorithm '{algorithm}'.")
    run = latest_run(c.session, c.workspace.id, algorithm)
    if run is None:
        raise ApiError(404, "no_run", f"{algorithm} has not been trained yet.")
    return _run_json(run, True)


@router.post("/models/retrain")
def retrain(c: Ctx, force: bool = False) -> dict:
    runs = train_all(c.session, c.workspace.id, force=force)
    return {"runs": [_run_json(r, False) for r in runs]}


# ------------------------------------------------------------- experiments
@router.get("/experiments")
def experiments_list(c: Ctx) -> dict:
    return {"items": [exp_svc.serialize(e, detail=False) for e in exp_svc.list_experiments(c.session, c.workspace.id)]}


@router.post("/experiments", status_code=201)
def experiments_create(body: exp_svc.ExperimentIn, c: Ctx) -> dict:
    return exp_svc.serialize(exp_svc.create_experiment(c.session, c.workspace.id, body))


@router.get("/experiments/{experiment_id}")
def experiments_get(experiment_id: int, c: Ctx) -> dict:
    return exp_svc.serialize(exp_svc.get_experiment(c.session, c.workspace.id, experiment_id))


@router.post("/experiments/{experiment_id}/observations", status_code=201)
def experiments_observe(experiment_id: int, body: exp_svc.ObservationIn, c: Ctx) -> dict:
    return exp_svc.serialize(exp_svc.add_observation(c.session, c.workspace.id, experiment_id, body))


@router.post("/experiments/{experiment_id}/complete")
def experiments_complete(experiment_id: int, c: Ctx) -> dict:
    return exp_svc.serialize(exp_svc.complete_experiment(c.session, c.workspace.id, experiment_id))


@router.get("/learnings")
def learnings(c: Ctx) -> dict:
    return {"items": [{"id": lr.id, "statement": lr.statement, "verdict": lr.verdict, "experiment_id": lr.experiment_id,
                       "created_at": lr.created_at.isoformat(), "evidence": lr.evidence}
                      for lr in exp_svc.list_learnings(c.session, c.workspace.id)]}


# --------------------------------------------------------------------- AI
class InterpretIn(BaseModel):
    scope: Literal["overview", "autopsy", "prediction", "experiment"]
    post_id: int | None = None
    experiment_id: int | None = None
    draft: prediction.Draft | None = None


@router.post("/ai/interpret")
def ai_interpret(body: InterpretIn, c: Ctx) -> dict:
    if c.frame.empty:
        return ai.interpret(body.scope, [], [])
    if body.scope == "overview":
        ev, st = evidence.overview_evidence(overview.build_overview(c.session, c.workspace, c.frame))
    elif body.scope == "autopsy":
        if body.post_id is None:
            raise ApiError(422, "missing_post_id", "post_id is required for autopsy interpretation.")
        ev, st = evidence.autopsy_evidence(autopsy.build_autopsy(c.session, c.workspace.id, c.frame, body.post_id))
    elif body.scope == "prediction":
        if body.draft is None:
            raise ApiError(422, "missing_draft", "draft is required for prediction interpretation.")
        res = prediction.predict(c.session, c.workspace.id, c.frame, body.draft)
        if res["status"] != "ok":
            raise ApiError(422 if res["status"] == "invalid" else 409, res["status"], res["message"])
        ev, st = evidence.prediction_evidence(res)
    else:
        if body.experiment_id is None:
            raise ApiError(422, "missing_experiment_id", "experiment_id is required for experiment interpretation.")
        ev, st = evidence.experiment_evidence(exp_svc.serialize(exp_svc.get_experiment(c.session, c.workspace.id, body.experiment_id)))
    return ai.interpret(body.scope, ev, st)


# --------------------------------------------------------------- ingestion
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
_INT_FIELDS = ("impressions", "reach", "likes", "comments", "shares", "saves", "media_count")


@router.post("/ingest/csv")
async def ingest_csv(c: Ctx, file: UploadFile = File(...)) -> dict:
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise ApiError(413, "file_too_large", "CSV must be 5 MB or smaller.")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ApiError(422, "bad_encoding", "CSV must be UTF-8 encoded.") from exc
    reader = csv.DictReader(io.StringIO(text))
    missing = [col for col in REQUIRED_COLUMNS if col not in (reader.fieldnames or [])]
    if missing:
        raise ApiError(422, "missing_columns", f"CSV is missing required columns: {', '.join(missing)}")
    records = []
    for row in reader:
        rec = {k: (v.strip() if isinstance(v, str) else v) for k, v in row.items() if k in REQUIRED_COLUMNS or k == "media_count"}
        for f in _INT_FIELDS:
            if rec.get(f) in ("", None):
                rec.pop(f, None)
        records.append(rec)
    if not records:
        raise ApiError(422, "empty_file", "CSV contains no rows.")
    try:
        report = ingest_records(c.session, c.workspace.id, records, source=f"csv:{file.filename}")
    except ValueError as exc:
        raise ApiError(413, "batch_too_large", str(exc)) from exc
    runs = train_all(c.session, c.workspace.id)
    return {"report": report, "models_retrained": len(runs)}


@router.get("/etl/runs")
def etl_runs(c: Ctx) -> dict:
    rows = c.session.execute(select(EtlRun).where(EtlRun.workspace_id == c.workspace.id).order_by(EtlRun.id.desc()).limit(10)).scalars()
    return {"items": [{"id": r.id, "source": r.source, "started_at": r.started_at.isoformat(), "rows_in": r.rows_in,
                       "rows_loaded": r.rows_loaded, "report": r.report} for r in rows],
            "required_columns": REQUIRED_COLUMNS}


_ = datetime  # (kept for type-checkers resolving annotations)
