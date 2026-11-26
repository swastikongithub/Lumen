"""The 30-day retention purge (SPEC §13) against real Postgres."""

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Conversation, Feedback, Message
from app.db.retention import delete_expired, purge_once, retention_cutoff
from app.enums import Client, Role

pytestmark = pytest.mark.integration

NOW = datetime.now(UTC)
OLD = NOW - timedelta(days=40)
RECENT = NOW - timedelta(days=2)


async def conversation(db: AsyncSession, created_at: datetime, *message_times: datetime):
    chat = Conversation(session_id=str(uuid.uuid4()), client=Client.WEB, created_at=created_at)
    db.add(chat)
    await db.flush()
    messages = [
        Message(conversation_id=chat.id, role=Role.USER, content="q", created_at=at)
        for at in message_times
    ]
    db.add_all(messages)
    await db.flush()
    return chat, messages


async def count(db: AsyncSession, model, *where) -> int:
    return await db.scalar(select(func.count()).select_from(model).where(*where))


async def test_old_messages_feedback_and_empty_conversations_are_deleted(
    db_session: AsyncSession,
) -> None:
    gone, (old_message,) = await conversation(db_session, OLD, OLD)
    db_session.add(Feedback(message_id=old_message.id, rating=-1))
    ongoing, _ = await conversation(db_session, OLD, OLD, RECENT)
    fresh, _ = await conversation(db_session, RECENT, RECENT)

    purged = await delete_expired(db_session, retention_cutoff(30))

    assert (purged.messages, purged.conversations) == (2, 1)
    assert await count(db_session, Conversation, Conversation.id == gone.id) == 0
    assert await count(db_session, Feedback) == 0
    # A conversation that is still in use keeps its recent messages.
    assert await count(db_session, Message, Message.conversation_id == ongoing.id) == 1
    assert await count(db_session, Message, Message.conversation_id == fresh.id) == 1


async def test_nothing_younger_than_the_cutoff_is_touched(db_session: AsyncSession) -> None:
    await conversation(db_session, RECENT, RECENT, RECENT)

    purged = await delete_expired(db_session, retention_cutoff(30))

    assert (purged.messages, purged.conversations) == (0, 0)


class RecordingCache:
    def __init__(self) -> None:
        self.cutoffs: list[float] = []

    async def delete_older_than(self, cutoff: float) -> None:
        self.cutoffs.append(cutoff)


async def test_purge_once_clears_postgres_and_the_answer_cache(db_session: AsyncSession) -> None:
    await conversation(db_session, OLD, OLD)
    cache = RecordingCache()

    @asynccontextmanager
    async def sessions():
        yield db_session

    await purge_once(sessions, cache, days=30)

    assert await count(db_session, Message) == 0
    assert cache.cutoffs == [pytest.approx(retention_cutoff(30).timestamp(), abs=5)]


async def test_a_failed_purge_is_logged_not_raised(caplog: pytest.LogCaptureFixture) -> None:
    @asynccontextmanager
    async def broken_sessions():
        raise OSError("database is down")
        yield

    class BrokenCache:
        async def delete_older_than(self, cutoff: float) -> None:
            raise OSError("qdrant is down")

    await purge_once(broken_sessions, BrokenCache(), days=30)

    assert "Retention purge of Postgres failed" in caplog.text
    assert "Retention purge of the answer cache failed" in caplog.text
