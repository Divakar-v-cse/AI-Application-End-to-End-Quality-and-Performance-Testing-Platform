"""Shared pytest fixtures.

The suite runs against an isolated SQLite database created per session under
``.pytest-data/``. It never touches ``backend/data/quality.db`` and never needs a
running server, credentials or an AWS account.
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

DATA_DIR = ROOT / ".pytest-data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
TEST_DB = DATA_DIR / f"quality-test-{uuid.uuid4().hex[:8]}.db"

os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["DATA_DIR"] = str(DATA_DIR)
os.environ["ARTIFACT_DIR"] = str(DATA_DIR / "artifacts")
os.environ["SEED_ON_STARTUP"] = "true"
os.environ["ENABLE_UI_RUNNER"] = "false"
os.environ["AWS_ENABLED"] = "false"
os.environ["APP_ENV"] = "test"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app import database, seed  # noqa: E402
from app.config import settings  # noqa: E402


def _rebind_database() -> None:
    """Force every module onto the throwaway test database.

    ``backend/.env`` is loaded with override semantics, so a developer's local
    configuration must not be allowed to redirect tests at the real database.
    """
    engine = create_engine(
        f"sqlite:///{TEST_DB.as_posix()}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    database.engine = engine
    database.SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    # These modules imported SessionLocal by value; keep them in sync.
    import app.main as main_module

    main_module.SessionLocal = database.SessionLocal
    seed.SessionLocal = database.SessionLocal


_rebind_database()


@pytest.fixture(scope="session")
def client():
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def token(client) -> str:
    response = client.post(
        "/api/auth/login",
        json={"email": settings.demo_user_email, "password": settings.demo_user_password},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


@pytest.fixture(scope="session")
def auth(token) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def db():
    session = database.SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="session")
def seeded_counts(client) -> dict:
    return seed.ensure_seed_data(database.SessionLocal())


@pytest.fixture(scope="session")
def latest_run_key(client, auth) -> str:
    response = client.get("/api/runs?limit=1", headers=auth)
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert items, "seeded history should provide at least one run"
    return items[0]["run_key"]


def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001
    """Remove the throwaway database when the suite ends."""
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(f"{TEST_DB}{suffix}")
        if candidate.exists():
            try:
                candidate.unlink()
            except OSError:
                pass
