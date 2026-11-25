"""Sessions come from the X-Session-Id header, never cookies (SPEC §10, CLAUDE.md rule 12)."""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.deps import parse_session_headers
from app.enums import Client
from tests.conftest import OTHER_UUID, VALID_SESSION_ID

# Routes that read or write a session's data, with a valid request body.
SESSION_ROUTES = [
    ("POST", "/api/v1/chat", {"message": "What is the minimum attendance?"}),
    ("GET", f"/api/v1/conversations/{OTHER_UUID}", None),
    ("POST", "/api/v1/feedback", {"message_id": OTHER_UUID, "rating": -1, "reason": "offensive"}),
    ("DELETE", "/api/v1/session", None),
]


def send(client: TestClient, method: str, path: str, body: dict | None, headers: dict):
    return client.request(method, path, json=body, headers=headers)


# --- parse_session_headers -------------------------------------------------------------


def test_valid_headers_are_parsed_and_normalised() -> None:
    session = parse_session_headers(VALID_SESSION_ID.upper(), "Android", " 1.2.0 ")

    assert session.session_id == VALID_SESSION_ID
    assert session.client is Client.ANDROID
    assert session.app_version == "1.2.0"


def test_client_defaults_to_web_and_version_to_none() -> None:
    session = parse_session_headers(VALID_SESSION_ID, None, "  ")

    assert session.client is Client.WEB
    assert session.app_version is None


@pytest.mark.parametrize(
    ("session_id", "client", "app_version", "message"),
    [
        (None, None, None, "X-Session-Id header is required"),
        ("", None, None, "X-Session-Id header is required"),
        ("not-a-uuid", None, None, "X-Session-Id must be a UUID"),
        (VALID_SESSION_ID, "ios", None, "X-Client must be one of: web, android"),
        (VALID_SESSION_ID, "web", "1" * 33, "X-App-Version must be at most 32 characters"),
    ],
)
def test_bad_headers_are_rejected_with_400(session_id, client, app_version, message) -> None:
    with pytest.raises(HTTPException) as error:
        parse_session_headers(session_id, client, app_version)

    assert error.value.status_code == 400
    assert error.value.detail == message


# --- over HTTP -------------------------------------------------------------------------


@pytest.mark.parametrize(("method", "path", "body"), SESSION_ROUTES)
def test_session_routes_require_the_header(client: TestClient, method, path, body) -> None:
    response = send(client, method, path, body, headers={})

    assert response.status_code == 400
    assert response.json() == {"detail": "X-Session-Id header is required"}


@pytest.mark.parametrize(("method", "path", "body"), SESSION_ROUTES)
def test_session_routes_accept_a_valid_header(
    client: TestClient, session_headers: dict, method, path, body
) -> None:
    response = send(client, method, path, body, headers=session_headers)

    # Past the session check; the handler itself is a Phase 2 placeholder.
    assert response.status_code == 501


@pytest.mark.parametrize(("method", "path", "body"), SESSION_ROUTES)
def test_a_cookie_is_not_a_session(client: TestClient, method, path, body) -> None:
    cookie = f"X-Session-Id={VALID_SESSION_ID}; session_id={VALID_SESSION_ID}"
    response = send(client, method, path, body, headers={"Cookie": cookie})

    assert response.status_code == 400


def test_public_routes_need_no_session(client: TestClient) -> None:
    # /sources is a placeholder for now: 501, not 400, proves no session is required.
    assert client.get("/api/v1/sources").status_code == 501


@pytest.mark.parametrize(("method", "path", "body"), SESSION_ROUTES)
def test_api_never_sets_cookies(
    client: TestClient, session_headers: dict, method, path, body
) -> None:
    response = send(client, method, path, body, headers=session_headers)

    assert "set-cookie" not in response.headers
