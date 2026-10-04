from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select

from .config import get_settings
from .db import SessionLocal, init_db
from .models import Post
from .routers.api import router
from .services.common import ApiError

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("signal")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    settings = get_settings()
    if settings.auto_seed:
        with SessionLocal() as session:
            if session.execute(select(Post.id).limit(1)).first() is None:
                from .seed.run import seed_demo

                log.info("Empty database: seeding demo workspace (one-time, ~10s)...")
                seed_demo(session)
                log.info("Demo workspace ready.")
            else:
                from .ml.pipeline import train_all
                from .seed.run import get_demo_workspace

                ws = get_demo_workspace(session)
                if ws:
                    train_all(session, ws.id)  # no-op when data unchanged (hash match)
    yield


app = FastAPI(title="SIGNAL API", version="1.0.0", lifespan=lifespan,
              description="Content intelligence & experimentation engine.")
app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_list, allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(ApiError)
async def api_error_handler(_: Request, exc: ApiError):
    return JSONResponse(status_code=exc.status, content={"error": {"code": exc.code, "message": exc.message}})


@app.exception_handler(RequestValidationError)
async def validation_handler(_: Request, exc: RequestValidationError):
    errors = [{"field": ".".join(str(p) for p in e["loc"][1:]) or "body", "message": e["msg"]} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"error": {"code": "validation_error", "message": "Invalid request.", "details": errors}})


app.include_router(router)
