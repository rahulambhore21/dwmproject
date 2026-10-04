import os
import tempfile
from datetime import datetime

_TMP = tempfile.mkdtemp(prefix="signal-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP}/api.db"
os.environ["ARTIFACTS_DIR"] = f"{_TMP}/artifacts"

import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app import models  # noqa: E402,F401
from app.db import Base  # noqa: E402

AS_OF = datetime(2026, 10, 4)


def make_session() -> Session:
    eng = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    return Session(eng, expire_on_commit=False)


@pytest.fixture(scope="session")
def seeded():
    """Demo workspace seeded once with a fixed clock (deterministic)."""
    from app.seed.run import seed_demo

    s = make_session()
    ws = seed_demo(s, as_of=AS_OF, seed=7)
    yield s, ws
    s.close()


@pytest.fixture()
def empty_session():
    s = make_session()
    yield s
    s.close()


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c
