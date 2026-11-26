"""Rate limits per session and per salted IP hash (SPEC §9 step 1, §13)."""

import uuid

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from slowapi.errors import RateLimitExceeded

from app.api import rate_limit
from app.api.rate_limit import (
    client_address,
    hash_address,
    limit_per_ip,
    limit_per_session,
    network_of,
)
from app.config import Settings
from tests.conftest import OTHER_UUID, VALID_SESSION_ID


def request_from(peer: str, forwarded: str | None = None) -> Request:
    headers = [(b"x-forwarded-for", forwarded.encode())] if forwarded else []
    return Request({"type": "http", "headers": headers, "client": (peer, 50000)})


# Defined once: slowapi files limits under the route function's name.
demo = FastAPI()
demo.add_exception_handler(RateLimitExceeded, rate_limit.rate_limited)


@demo.post("/ask")
@limit_per_ip
@limit_per_session
async def limited_route(request: Request) -> dict[str, bool]:
    return {"ok": True}


@pytest.fixture
def limited_app() -> FastAPI:
    demo.state.settings = Settings(
        _env_file=None, rate_limit_session="2/minute", rate_limit_ip="3/minute"
    )
    rate_limit.configure(demo.state.settings)
    return demo


def ask(client: TestClient, session_id: str = VALID_SESSION_ID) -> int:
    return client.post("/ask", headers={"X-Session-Id": session_id}).status_code


# --- the client's address -------------------------------------------------------------


def test_without_trusted_proxies_the_peer_address_is_used() -> None:
    request = request_from("203.0.113.7", forwarded="198.51.100.1")

    assert client_address(request, trusted_proxy_hops=0) == "203.0.113.7"


def test_behind_one_proxy_the_address_it_appended_is_used() -> None:
    # The first entry was sent by the client itself and is ignored.
    request = request_from("10.0.0.1", forwarded="1.2.3.4, 203.0.113.7")

    assert client_address(request, trusted_proxy_hops=1) == "203.0.113.7"


def test_a_short_forwarded_header_falls_back_to_the_peer() -> None:
    request = request_from("10.0.0.1", forwarded="203.0.113.7")

    assert client_address(request, trusted_proxy_hops=2) == "10.0.0.1"


def test_ipv6_addresses_count_per_64_network() -> None:
    assert network_of("2001:db8:1:2:aaaa::1") == "2001:db8:1:2::/64"
    assert network_of("::ffff:203.0.113.7") == "203.0.113.7"
    assert network_of("203.0.113.7") == "203.0.113.7"
    assert hash_address("2001:db8:1:2::1") == hash_address("2001:db8:1:2:ffff::9")


def test_the_ip_is_kept_only_as_a_salted_hash() -> None:
    key = hash_address("203.0.113.7")

    assert "203" not in key and len(key) == 32
    assert key == hash_address("203.0.113.7")
    assert key != hash_address("203.0.113.8")
    assert key != hash_address("203.0.113.7", salt=b"another process")


# --- limits through a route -----------------------------------------------------------


def test_the_session_limit_answers_429_with_retry_after(limited_app: FastAPI) -> None:
    client = TestClient(limited_app)

    statuses = [ask(client) for _ in range(3)]
    response = client.post("/ask", headers={"X-Session-Id": VALID_SESSION_ID})

    assert statuses == [200, 200, 429]
    assert response.status_code == 429
    body = response.json()
    assert body["code"] == "too_many_requests"
    assert 1 <= body["retry_after"] <= 60
    assert response.headers["Retry-After"] == str(body["retry_after"])


def test_sessions_are_limited_separately(limited_app: FastAPI) -> None:
    client = TestClient(limited_app)

    assert [ask(client), ask(client), ask(client)] == [200, 200, 429]
    assert ask(client, OTHER_UUID) == 200


def test_a_request_its_session_limit_refuses_leaves_the_ip_quota_alone(
    limited_app: FastAPI,
) -> None:
    client = TestClient(limited_app)

    assert [ask(client) for _ in range(5)] == [200, 200, 429, 429, 429]
    assert ask(client, OTHER_UUID) == 200  # the IP has used 3 of 3: the 2 answered + this one
    assert ask(client, str(uuid.uuid4())) == 429


def test_new_session_ids_do_not_escape_the_ip_limit(limited_app: FastAPI) -> None:
    client = TestClient(limited_app)  # every request comes from the same test address

    statuses = [ask(client, str(uuid.uuid4())) for _ in range(4)]

    assert statuses == [200, 200, 200, 429]


def test_configure_starts_with_empty_counters(limited_app: FastAPI) -> None:
    client = TestClient(limited_app)
    assert [ask(client), ask(client), ask(client)] == [200, 200, 429]

    rate_limit.configure(limited_app.state.settings)

    assert ask(client) == 200
