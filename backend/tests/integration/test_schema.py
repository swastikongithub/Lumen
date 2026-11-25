"""The real Postgres schema: migrations, constraints and the queries Phase 0 already runs."""

import uuid

import httpx2
import pytest
from alembic import command
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.meta import current_corpus_version
from app.config import Settings
from app.db.models import Conversation, CorpusVersion, Document, Feedback, Message
from app.db.session import get_db
from app.enums import Client, DocumentCategory, DocumentStatus, FeedbackReason, Role
from app.main import create_app
from tests.integration.conftest import alembic_config

pytestmark = pytest.mark.integration


def make_document(source_id: str, version: int, status: DocumentStatus) -> Document:
    return Document(
        source_id=source_id,
        title="Examination Policy",
        source_url="https://example.org/exam-policy.pdf",
        category=DocumentCategory.EXAMS,
        academic_year="2025-26",
        content_hash=f"{version:064d}",
        version=version,
        status=status,
        page_count=20,
        chunk_count=48,
    )


async def make_message(db: AsyncSession, session_id: str) -> Message:
    conversation = Conversation(session_id=session_id, client=Client.ANDROID, app_version="1.0.0")
    db.add(conversation)
    await db.flush()
    message = Message(conversation_id=conversation.id, role=Role.ASSISTANT, content="Answer [1]")
    db.add(message)
    await db.flush()
    return message


async def make_message_with_feedback(db: AsyncSession, session_id: str) -> Message:
    message = await make_message(db, session_id)
    db.add(Feedback(message_id=message.id, rating=-1, reason=FeedbackReason.OFFENSIVE))
    await db.flush()
    return message


def test_migrations_round_trip_and_match_the_models(migrated_database_url: str) -> None:
    config = alembic_config(migrated_database_url)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    # Raises if the models and the migrations disagree.
    command.check(config)


async def test_corpus_version_is_zero_before_ingestion_then_the_highest(
    db_session: AsyncSession,
) -> None:
    assert await current_corpus_version(db_session) == 0

    versions = [CorpusVersion(), CorpusVersion()]
    db_session.add_all(versions)
    await db_session.flush()

    assert await current_corpus_version(db_session) == max(v.version for v in versions)


async def test_meta_endpoint_reads_corpus_version_from_postgres(db_session: AsyncSession) -> None:
    db_session.add(CorpusVersion())
    await db_session.flush()
    expected = await current_corpus_version(db_session)

    app = create_app(Settings(_env_file=None))
    app.dependency_overrides[get_db] = lambda: db_session
    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/meta")

    assert response.status_code == 200
    assert response.json()["corpus_version"] == expected


async def test_message_defaults(db_session: AsyncSession) -> None:
    conversation = Conversation(session_id=str(uuid.uuid4()), client=Client.WEB)
    db_session.add(conversation)
    await db_session.flush()
    message = Message(conversation_id=conversation.id, role=Role.USER, content="Hostel timings?")
    db_session.add(message)
    await db_session.flush()
    await db_session.refresh(message)

    assert message.citations == []
    assert message.abstained is False
    assert message.cache_hit is False
    assert message.model is None
    assert message.created_at is not None


async def test_one_active_version_per_source_document(db_session: AsyncSession) -> None:
    db_session.add(make_document("exam-policy", 1, DocumentStatus.SUPERSEDED))
    db_session.add(make_document("exam-policy", 2, DocumentStatus.ACTIVE))
    await db_session.flush()  # an old superseded version next to the active one is fine

    db_session.add(make_document("exam-policy", 3, DocumentStatus.ACTIVE))
    with pytest.raises(IntegrityError, match="uq_documents_one_active_per_source"):
        await db_session.flush()


async def test_source_version_pairs_are_unique(db_session: AsyncSession) -> None:
    db_session.add(make_document("hostel-rules", 1, DocumentStatus.SUPERSEDED))
    db_session.add(make_document("hostel-rules", 1, DocumentStatus.SUPERSEDED))
    with pytest.raises(IntegrityError, match="uq_documents_source_id_version"):
        await db_session.flush()


async def test_one_feedback_row_per_message(db_session: AsyncSession) -> None:
    message = await make_message_with_feedback(db_session, str(uuid.uuid4()))

    db_session.add(Feedback(message_id=message.id, rating=1))
    with pytest.raises(IntegrityError, match="uq_feedback_message_id"):
        await db_session.flush()


@pytest.mark.parametrize(
    ("statement", "constraint"),
    [
        (
            "INSERT INTO conversations (id, session_id, client) "
            "VALUES (gen_random_uuid(), 's', 'ios')",
            "ck_conversations_client",
        ),
        (
            "INSERT INTO documents (id, source_id, title, source_url, category, content_hash, "
            "version, status, page_count, chunk_count) VALUES (gen_random_uuid(), 'x', 't', "
            "'u', 'sports', 'h', 1, 'active', 1, 1)",
            "ck_documents_category",
        ),
    ],
)
async def test_check_constraints_reject_unknown_enum_values(
    db_session: AsyncSession, statement: str, constraint: str
) -> None:
    with pytest.raises(IntegrityError, match=constraint):
        await db_session.execute(text(statement))


async def test_feedback_rating_must_be_plus_or_minus_one(db_session: AsyncSession) -> None:
    message = await make_message(db_session, str(uuid.uuid4()))

    db_session.add(Feedback(message_id=message.id, rating=0))
    with pytest.raises(IntegrityError, match="ck_feedback_rating"):
        await db_session.flush()


async def test_clearing_a_session_deletes_its_messages_and_feedback(
    db_session: AsyncSession,
) -> None:
    mine, theirs = str(uuid.uuid4()), str(uuid.uuid4())
    my_message = await make_message_with_feedback(db_session, mine)
    their_message = await make_message_with_feedback(db_session, theirs)

    # The statement DELETE /api/v1/session will run; ON DELETE CASCADE does the rest.
    await db_session.execute(delete(Conversation).where(Conversation.session_id == mine))

    async def count(model, column, value) -> int:
        return await db_session.scalar(
            select(func.count()).select_from(model).where(column == value)
        )

    assert await count(Message, Message.id, my_message.id) == 0
    assert await count(Feedback, Feedback.message_id, my_message.id) == 0
    assert await count(Message, Message.id, their_message.id) == 1
    assert await count(Feedback, Feedback.message_id, their_message.id) == 1
