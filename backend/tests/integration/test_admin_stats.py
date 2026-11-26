"""GET /admin/stats (SPEC §10) against real Postgres: the key check and the numbers."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx2
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import Conversation, Feedback, Message
from app.db.session import get_db
from app.enums import Client, Role
from app.main import create_app

pytestmark = pytest.mark.integration

ADMIN_KEY = "test-admin-key-0123456789"
NOW = datetime.now(UTC)


@pytest.fixture
async def admin(db_session: AsyncSession) -> AsyncIterator[httpx2.AsyncClient]:
    app = create_app(Settings(_env_file=None, admin_api_key=ADMIN_KEY))
    app.dependency_overrides[get_db] = lambda: db_session
    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def get_stats(client: httpx2.AsyncClient, key: str | bytes | None = ADMIN_KEY, **params):
    headers = {"X-Admin-Key": key} if key is not None else {}
    return await client.get("/admin/stats", headers=headers, params=params)


async def add_exchange(
    db: AsyncSession,
    at: datetime,
    *,
    abstained=False,
    cache_hit=False,
    latency_ms=100,
    ttft_ms=50,
    rating: int | None = None,
) -> None:
    chat = Conversation(session_id=str(uuid.uuid4()), client=Client.WEB, created_at=at)
    db.add(chat)
    await db.flush()
    answer = Message(
        conversation_id=chat.id,
        role=Role.ASSISTANT,
        content="Answer [1]",
        abstained=abstained,
        cache_hit=cache_hit,
        latency_ms=latency_ms,
        ttft_ms=ttft_ms,
        created_at=at,
    )
    db.add_all(
        [Message(conversation_id=chat.id, role=Role.USER, content="q", created_at=at), answer]
    )
    await db.flush()
    if rating is not None:
        db.add(Feedback(message_id=answer.id, rating=rating))
        await db.flush()


async def test_without_a_configured_key_the_endpoint_does_not_exist() -> None:
    app = create_app(Settings(_env_file=None))
    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await get_stats(client, key="anything")

    assert response.status_code == 404


# "clé" as raw Latin-1 bytes: a non-ASCII header must be refused, not crash the comparison.
@pytest.mark.parametrize("key", [None, "", "wrong-key", ADMIN_KEY[:-1], "clé".encode("latin-1")])
async def test_a_missing_or_wrong_key_is_refused(admin: httpx2.AsyncClient, key) -> None:
    response = await get_stats(admin, key=key)

    assert response.status_code == 401


async def test_stats_over_the_window(admin: httpx2.AsyncClient, db_session: AsyncSession) -> None:
    yesterday = NOW - timedelta(days=1)
    await add_exchange(db_session, NOW, latency_ms=100, ttft_ms=40, rating=1)
    await add_exchange(db_session, NOW, abstained=True, latency_ms=300, ttft_ms=60, rating=-1)
    await add_exchange(db_session, yesterday, cache_hit=True, latency_ms=200, ttft_ms=50)
    await add_exchange(db_session, NOW - timedelta(days=20), rating=-1)  # outside 7 days

    response = await get_stats(admin, days=7)

    assert response.status_code == 200
    stats = response.json()
    assert (stats["days"], stats["questions"], stats["answers"]) == (7, 3, 3)
    assert [day["questions"] for day in stats["questions_per_day"]] == [1, 2]
    assert stats["questions_per_day"][-1]["date"] == NOW.date().isoformat()
    assert stats["abstain_rate"] == stats["cache_hit_rate"] == pytest.approx(1 / 3, abs=1e-4)
    assert (stats["thumbs_up"], stats["thumbs_down"], stats["thumbs_down_rate"]) == (1, 1, 0.5)
    assert stats["latency_ms"] == {"p50": 200.0, "p95": 290.0}
    assert stats["ttft_ms"]["p50"] == 50.0


async def test_an_empty_window_has_no_rates(admin: httpx2.AsyncClient) -> None:
    stats = (await get_stats(admin)).json()

    assert (stats["questions"], stats["answers"], stats["questions_per_day"]) == (0, 0, [])
    assert stats["abstain_rate"] is None and stats["thumbs_down_rate"] is None
    assert stats["latency_ms"] == {"p50": None, "p95": None}


@pytest.mark.parametrize("days", [0, 31])
async def test_the_window_is_one_to_thirty_days(admin: httpx2.AsyncClient, days: int) -> None:
    assert (await get_stats(admin, days=days)).status_code == 422
