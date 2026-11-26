"""The v1 API surface (SPEC §10): which routes exist, where they live and what they accept."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.chat import ChatRequest
from app.api.feedback import FeedbackRequest
from app.api.meta import current_corpus_version
from app.config import Settings
from app.enums import FeedbackReason
from tests.conftest import OTHER_UUID

PLANNED_PUBLIC_ROUTES = {
    ("POST", "/api/v1/chat"),
    ("GET", "/api/v1/conversations/{conversation_id}"),
    ("POST", "/api/v1/feedback"),
    ("GET", "/api/v1/sources"),
    ("GET", "/api/v1/meta"),
    ("DELETE", "/api/v1/session"),
}
# The probes are the only documented routes allowed outside /api/v1.
PATHS_OUTSIDE_V1 = {"/health", "/ready"}


def documented_routes(app: FastAPI) -> set[tuple[str, str]]:
    """(METHOD, path) pairs from the OpenAPI document, which is the published API contract."""
    return {
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        for method in operations
    }


def test_exactly_the_planned_routes_are_published(app: FastAPI) -> None:
    published = {route for route in documented_routes(app) if route[1] not in PATHS_OUTSIDE_V1}
    assert published == PLANNED_PUBLIC_ROUTES


def test_public_routes_live_under_api_v1(app: FastAPI) -> None:
    outside = {
        path
        for _, path in documented_routes(app)
        if not path.startswith("/api/v1/") and path not in PATHS_OUTSIDE_V1
    }
    assert outside == set()


def test_offensive_feedback_reason_exists() -> None:
    # Google Play AI-Generated Content policy (CLAUDE.md rule 13).
    assert FeedbackReason("offensive") is FeedbackReason.OFFENSIVE


# --- meta ------------------------------------------------------------------------------


def test_meta_returns_app_versions_and_corpus_version(app: FastAPI, client: TestClient) -> None:
    app.state.settings = Settings(
        _env_file=None, min_app_version="1.1.0", latest_app_version="1.3.0", app_notice="Hi"
    )
    app.dependency_overrides[current_corpus_version] = lambda: 7

    response = client.get("/api/v1/meta")

    assert response.status_code == 200
    assert response.json() == {
        "min_app_version": "1.1.0",
        "latest_app_version": "1.3.0",
        "notice": "Hi",
        "corpus_version": 7,
    }


# --- request validation ----------------------------------------------------------------
# Valid bodies are checked against the models directly; the routes behind them need
# Postgres and the pipeline (tests/integration/test_chat_api.py). Invalid bodies must be
# rejected with 422 before any of that runs.


@pytest.mark.parametrize(
    "body",
    [
        {"message": "What is the minimum attendance?"},
        {"message": "x" * 1000},
        {"message": "Hostel timings?", "category": "hostel"},
        {"message": "Hostel timings?", "category": None},
        {"message": "Follow-up", "conversation_id": OTHER_UUID},
    ],
)
def test_valid_chat_requests(body: dict) -> None:
    ChatRequest.model_validate(body)


@pytest.mark.parametrize(
    "body",
    [
        {"message": ""},
        {"message": "   "},
        {"message": "x" * 1001},
        {"message": "Hostel timings?", "category": "sports"},
        {"message": "Follow-up", "conversation_id": "42"},
        {},
    ],
)
def test_invalid_chat_requests_are_rejected(
    client: TestClient, session_headers: dict, stub_backends: None, body: dict
) -> None:
    response = client.post("/api/v1/chat", json=body, headers=session_headers)
    assert response.status_code == 422


def test_chat_message_is_stripped() -> None:
    request = ChatRequest.model_validate({"message": "  Hostel timings?  "})

    assert request.message == "Hostel timings?"


@pytest.mark.parametrize(
    "body",
    [
        {"message_id": OTHER_UUID, "rating": 1},
        {"message_id": OTHER_UUID, "rating": -1},
        {"message_id": OTHER_UUID, "rating": -1, "reason": "offensive", "comment": "Rude"},
    ],
)
def test_valid_feedback_requests(body: dict) -> None:
    FeedbackRequest.model_validate(body)


@pytest.mark.parametrize(
    "body",
    [
        {"message_id": OTHER_UUID, "rating": 0},
        {"message_id": OTHER_UUID, "rating": 1, "reason": "wrong"},
        {"message_id": OTHER_UUID, "rating": -1, "reason": "boring"},
        {"message_id": OTHER_UUID, "rating": -1, "comment": "x" * 1001},
        {"message_id": "not-a-uuid", "rating": 1},
    ],
)
def test_invalid_feedback_requests_are_rejected(
    client: TestClient, session_headers: dict, stub_backends: None, body: dict
) -> None:
    response = client.post("/api/v1/feedback", json=body, headers=session_headers)
    assert response.status_code == 422


def test_conversation_id_must_be_a_uuid(
    client: TestClient, session_headers: dict, stub_backends: None
) -> None:
    response = client.get("/api/v1/conversations/123", headers=session_headers)
    assert response.status_code == 422
