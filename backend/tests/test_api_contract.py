"""The v1 API surface (SPEC §10): which routes exist, where they live and what they accept."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

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


@pytest.mark.parametrize(
    ("body", "expected_status"),
    [
        ({"message": "What is the minimum attendance?"}, 501),
        ({"message": "x" * 1000}, 501),
        ({"message": "Hostel timings?", "category": "hostel"}, 501),
        ({"message": "Hostel timings?", "category": None}, 501),
        ({"message": "Follow-up", "conversation_id": OTHER_UUID}, 501),
        ({"message": ""}, 422),
        ({"message": "   "}, 422),
        ({"message": "x" * 1001}, 422),
        ({"message": "Hostel timings?", "category": "sports"}, 422),
        ({"message": "Follow-up", "conversation_id": "42"}, 422),
        ({}, 422),
    ],
)
def test_chat_request_validation(
    client: TestClient, session_headers: dict, body: dict, expected_status: int
) -> None:
    response = client.post("/api/v1/chat", json=body, headers=session_headers)
    assert response.status_code == expected_status


@pytest.mark.parametrize(
    ("body", "expected_status"),
    [
        ({"message_id": OTHER_UUID, "rating": 1}, 501),
        ({"message_id": OTHER_UUID, "rating": -1}, 501),
        ({"message_id": OTHER_UUID, "rating": -1, "reason": "offensive", "comment": "Rude"}, 501),
        ({"message_id": OTHER_UUID, "rating": 0}, 422),
        ({"message_id": OTHER_UUID, "rating": 1, "reason": "wrong"}, 422),
        ({"message_id": OTHER_UUID, "rating": -1, "reason": "boring"}, 422),
        ({"message_id": OTHER_UUID, "rating": -1, "comment": "x" * 1001}, 422),
        ({"message_id": "not-a-uuid", "rating": 1}, 422),
    ],
)
def test_feedback_request_validation(
    client: TestClient, session_headers: dict, body: dict, expected_status: int
) -> None:
    response = client.post("/api/v1/feedback", json=body, headers=session_headers)
    assert response.status_code == expected_status


def test_conversation_id_must_be_a_uuid(client: TestClient, session_headers: dict) -> None:
    response = client.get("/api/v1/conversations/123", headers=session_headers)
    assert response.status_code == 422
