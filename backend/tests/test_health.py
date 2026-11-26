import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.datastructures import State

from app.api.health import check_models_loaded, readiness_checks
from app.observability import Tracer
from tests.conftest import StubBackend


async def passing_check() -> None:
    return None


async def failing_check() -> None:
    raise ConnectionError("secret-host.internal:5432 refused")


async def slow_check() -> None:
    await asyncio.sleep(5)


def use_checks(app: FastAPI, **checks) -> None:
    app.dependency_overrides[readiness_checks] = lambda: checks


def test_health_is_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_when_every_dependency_answers(app: FastAPI, client: TestClient) -> None:
    use_checks(app, postgres=passing_check, qdrant=passing_check)

    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {"postgres": "ok", "qdrant": "ok"}}


def test_not_ready_when_a_dependency_fails(app: FastAPI, client: TestClient) -> None:
    use_checks(app, postgres=failing_check, qdrant=passing_check)

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {"postgres": "error", "qdrant": "ok"},
    }
    # Error details stay in the logs.
    assert "secret-host" not in response.text


def test_not_ready_when_a_dependency_times_out(app: FastAPI, client: TestClient) -> None:
    # The settings fixture sets ready_timeout_seconds=0.2.
    use_checks(app, postgres=passing_check, qdrant=slow_check)

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["checks"] == {"postgres": "ok", "qdrant": "timeout"}


def test_lifespan_creates_and_closes_shared_clients(app: FastAPI) -> None:
    # Creating the engine and Qdrant client does not connect, so no services are needed.
    with TestClient(app):
        assert app.state.engine is not None
        assert app.state.sessionmaker is not None
        assert app.state.qdrant is not None
        assert isinstance(app.state.pipeline, StubBackend)
        # No Langfuse keys in the test settings: the tracer is a no-op.
        assert isinstance(app.state.tracer, Tracer) and not app.state.tracer.enabled


async def test_models_check_fails_until_the_pipeline_is_loaded() -> None:
    state = State()
    with pytest.raises(RuntimeError, match="models not loaded"):
        await check_models_loaded(state)

    state.pipeline = object()
    await check_models_loaded(state)
