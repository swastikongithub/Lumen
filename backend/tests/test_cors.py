"""CORS (SPEC §10): the web app, the Vite dev server and the Capacitor WebView may call the API."""

import pytest
from fastapi.testclient import TestClient

SESSION_HEADERS = "content-type,x-session-id,x-client,x-app-version"


def preflight(client: TestClient, origin: str):
    return client.options(
        "/api/v1/chat",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": SESSION_HEADERS,
        },
    )


@pytest.mark.parametrize("origin", ["http://localhost:5173", "https://localhost"])
def test_allowed_origins_may_send_session_headers(client: TestClient, origin: str) -> None:
    response = preflight(client, origin)

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    allowed = response.headers["access-control-allow-headers"].lower()
    for header in SESSION_HEADERS.split(","):
        assert header in allowed
    # Sessions use a header, so credentials (cookies) are never allowed.
    assert "access-control-allow-credentials" not in response.headers


def test_unknown_origin_is_refused(client: TestClient) -> None:
    response = preflight(client, "https://evil.example")

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
