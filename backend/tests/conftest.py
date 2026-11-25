"""Shared fixtures for unit tests. These need no running services."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

VALID_SESSION_ID = "3f2b8c1e-6a4d-4e2f-9b7a-1c5d8e9f0a2b"
OTHER_UUID = "9d7c6b5a-4e3f-4a2b-8c1d-0e9f8a7b6c5d"


@pytest.fixture
def settings() -> Settings:
    # _env_file=None: a developer's backend/.env never changes test results.
    return Settings(_env_file=None, ready_timeout_seconds=0.2)


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    # Not entered as a context manager, so the lifespan (real Postgres/Qdrant clients)
    # does not run. Tests override the dependencies they need instead.
    return TestClient(app)


@pytest.fixture
def session_headers() -> dict[str, str]:
    return {"X-Session-Id": VALID_SESSION_ID, "X-Client": "web", "X-App-Version": "1.0.0"}
