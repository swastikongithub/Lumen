"""Queries for conversations, messages and feedback (SPEC §7.1).

A conversation belongs to the anonymous session that started it. Every lookup here
takes the caller's session ID, so one device can never read or rate another's chat.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Conversation, Feedback, Message
from app.enums import Client, FeedbackReason, Role


async def find_conversation(
    db: AsyncSession, session_id: str, conversation_id: uuid.UUID
) -> Conversation | None:
    """The conversation if it exists and belongs to this session, else None."""
    return await db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id, Conversation.session_id == session_id
        )
    )


async def start_conversation(
    db: AsyncSession, session_id: str, client: Client, app_version: str | None
) -> Conversation:
    conversation = Conversation(
        id=uuid.uuid4(),
        session_id=session_id,
        client=client,
        app_version=app_version,
        created_at=datetime.now(UTC),
    )
    db.add(conversation)
    await db.flush()
    return conversation


async def add_message(
    db: AsyncSession,
    conversation_id: uuid.UUID,
    role: Role,
    content: str,
    *,
    message_id: uuid.UUID | None = None,
    **fields: Any,
) -> Message:
    """`created_at` is set here, not by Postgres: now() is fixed for a whole transaction,
    so a question and its answer saved together would otherwise tie."""
    message = Message(
        id=message_id or uuid.uuid4(),
        conversation_id=conversation_id,
        role=role,
        content=content,
        created_at=datetime.now(UTC),
        **fields,
    )
    db.add(message)
    await db.flush()
    return message


async def conversation_messages(db: AsyncSession, conversation_id: uuid.UUID) -> list[Message]:
    result = await db.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at, Message.id)
    )
    return list(result)


async def recent_messages(
    db: AsyncSession, conversation_id: uuid.UUID, limit: int
) -> list[Message]:
    """The conversation's last `limit` messages, oldest first (the follow-up rewrite's input)."""
    if limit <= 0:
        return []
    result = await db.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(limit)
    )
    return list(reversed(list(result)))


async def find_answer(db: AsyncSession, session_id: str, message_id: uuid.UUID) -> Message | None:
    """An assistant message in one of this session's conversations, else None."""
    return await db.scalar(
        select(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(
            Message.id == message_id,
            Message.role == Role.ASSISTANT,
            Conversation.session_id == session_id,
        )
    )


async def save_feedback(
    db: AsyncSession,
    message_id: uuid.UUID,
    rating: int,
    reason: FeedbackReason | None,
    comment: str | None,
) -> None:
    """One rating per message: a second rating replaces the first."""
    values = {"rating": rating, "reason": reason, "comment": comment}
    statement = insert(Feedback).values(
        id=uuid.uuid4(), message_id=message_id, created_at=datetime.now(UTC), **values
    )
    await db.execute(
        statement.on_conflict_do_update(
            index_elements=[Feedback.message_id],
            set_={**values, "created_at": statement.excluded.created_at},
        )
    )


async def delete_session_data(db: AsyncSession, session_id: str) -> int:
    """Delete the session's conversations; messages and feedback go with them (CASCADE)."""
    result = await db.execute(delete(Conversation).where(Conversation.session_id == session_id))
    return result.rowcount or 0
