"""Shared fixtures for unit tests. These need no running services."""

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api.chat import get_pipeline
from app.config import Settings
from app.db.session import get_db, get_session_factory
from app.main import create_app

VALID_SESSION_ID = "3f2b8c1e-6a4d-4e2f-9b7a-1c5d8e9f0a2b"
OTHER_UUID = "9d7c6b5a-4e3f-4a2b-8c1d-0e9f8a7b6c5d"


@pytest.fixture
def settings() -> Settings:
    # _env_file=None: a developer's backend/.env never changes test results.
    return Settings(_env_file=None, ready_timeout_seconds=0.2)


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    # No ONNX models in unit tests: the lifespan gets a stub instead of the real pipeline.
    return create_app(settings, pipeline_factory=lambda *args: StubBackend())


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    # Not entered as a context manager, so the lifespan (real Postgres/Qdrant clients)
    # does not run. Tests override the dependencies they need instead.
    return TestClient(app)


@pytest.fixture
def session_headers() -> dict[str, str]:
    return {"X-Session-Id": VALID_SESSION_ID, "X-Client": "web", "X-App-Version": "1.0.0"}


STUB_STATUS = 418


class StubBackend:
    """Stands in for Postgres and the pipeline in tests that run no services.

    Any use answers 418, which proves the request got past body validation and the
    session check. (FastAPI resolves dependencies before it reports body errors, so
    creating one must not fail.)
    """

    def __getattr__(self, name: str):
        raise HTTPException(STUB_STATUS, "stub backend")

    def __call__(self, *args, **kwargs):
        raise HTTPException(STUB_STATUS, "stub backend")


@pytest.fixture
def stub_backends(app: FastAPI) -> None:
    for dependency in (get_db, get_session_factory, get_pipeline):
        app.dependency_overrides[dependency] = StubBackend
