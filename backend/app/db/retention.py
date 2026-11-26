"""Data retention (SPEC §13): what students send is kept for RETENTION_DAYS (30), then deleted.

The /privacy page promises this, so the API enforces it itself instead of relying on a
scheduler: it purges a minute after startup (so a cold start is not slowed) and then every
RETENTION_CHECK_HOURS while it runs. Cloud Run scales to zero, so instances start often;
with two instances both may purge at once, which is harmless because deleting is idempotent.

What goes:
- messages older than the cutoff, with their feedback (ON DELETE CASCADE);
- conversations older than the cutoff that have no messages left;
- answer-cache entries older than the cutoff (app/rag/cache.py).
Langfuse traces are not deleted here: the Hobby plan keeps 30 days of data.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, exists, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Conversation, Message
from app.rag.cache import AnswerCache

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Purged:
    messages: int
    conversations: int


def retention_cutoff(days: int, now: datetime | None = None) -> datetime:
    return (now or datetime.now(UTC)) - timedelta(days=days)


async def delete_expired(db: AsyncSession, cutoff: datetime) -> Purged:
    """Delete messages (and their feedback) and empty conversations older than `cutoff`."""
    messages = await db.execute(delete(Message).where(Message.created_at < cutoff))
    has_messages = exists(select(Message.id).where(Message.conversation_id == Conversation.id))
    conversations = await db.execute(
        delete(Conversation).where(Conversation.created_at < cutoff, ~has_messages)
    )
    return Purged(messages=messages.rowcount or 0, conversations=conversations.rowcount or 0)


async def purge_once(
    sessionmaker: async_sessionmaker[AsyncSession],
    cache: AnswerCache | None,
    days: int,
) -> None:
    """One purge. Failures are logged, never raised: the API keeps serving."""
    cutoff = retention_cutoff(days)
    try:
        async with sessionmaker() as db:
            purged = await delete_expired(db, cutoff)
            await db.commit()
        logger.info(
            "Retention: deleted %d messages and %d conversations older than %d days",
            purged.messages,
            purged.conversations,
            days,
        )
    except Exception:
        logger.warning("Retention purge of Postgres failed", exc_info=True)
    if cache is not None:
        try:
            await cache.delete_older_than(cutoff.timestamp())
        except Exception:
            logger.warning("Retention purge of the answer cache failed", exc_info=True)


async def run_retention(
    sessionmaker: async_sessionmaker[AsyncSession],
    cache: AnswerCache | None,
    days: int,
    every_hours: float,
    first_delay_seconds: float = 60,
) -> None:
    """Purge after `first_delay_seconds`, then every `every_hours`, until cancelled."""
    await asyncio.sleep(first_delay_seconds)
    while True:
        await purge_once(sessionmaker, cache, days)
        await asyncio.sleep(every_hours * 3600)
