"""The v1 chat API against real Postgres, with a mocked LLM, retriever and re-ranker.

Requests go through httpx2's ASGITransport, so they run in the test's own event loop
and share its rolled-back database session.
"""

import json
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import nullcontext
from typing import Any

import httpx2
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.chat import get_pipeline
from app.config import Settings
from app.db.models import Conversation, Document, Feedback, Message
from app.db.session import get_db, get_session_factory
from app.enums import Client, DocumentCategory, DocumentStatus, FeedbackReason, Role
from app.main import create_app
from app.rag.citations import UNVERIFIED_NOTICE
from app.rag.generator import LlmUnavailableError
from app.rag.pipeline import PipelineConfig, RagPipeline
from app.rag.prompts import NOT_FOUND_ANSWER
from tests.conftest import OTHER_UUID, VALID_SESSION_ID
from tests.rag.fakes import FakeGenerator, FakeRetriever, FakeScorer, busy_generator, make_chunk

pytestmark = pytest.mark.integration

ATTENDANCE = make_chunk(1, "Students need 75% attendance to sit the end-term exam.")
FEES = make_chunk(2, "A late fee applies after the due date.", category="fees")
SCORES = {"75%": 5.0, "late fee": 1.0}
ANSWER = "You need 75% attendance [1]."

HEADERS = {"X-Session-Id": VALID_SESSION_ID, "X-Client": "android", "X-App-Version": "1.2.0"}
OTHER_HEADERS = {"X-Session-Id": OTHER_UUID, "X-Client": "web"}

ClientFactory = Callable[..., httpx2.AsyncClient]


def parse_sse(body: str) -> list[tuple[str, Any]]:
    events = []
    for frame in body.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in frame.splitlines())
        events.append((fields["event"], json.loads(fields["data"])))
    return events


def pipeline(generator: FakeGenerator, retriever: Any = None) -> RagPipeline:
    return RagPipeline(
        retriever or FakeRetriever([ATTENDANCE, FEES]),
        FakeScorer(SCORES),
        generator,
        PipelineConfig(abstain_threshold=0.0, abstain_sources=2),
    )


@pytest.fixture
async def make_client(db_session: AsyncSession) -> AsyncIterator[ClientFactory]:
    clients: list[httpx2.AsyncClient] = []

    def factory(rag: RagPipeline | None = None) -> httpx2.AsyncClient:
        app: FastAPI = create_app(Settings(_env_file=None))
        app.dependency_overrides[get_db] = lambda: db_session
        app.dependency_overrides[get_session_factory] = lambda: lambda: nullcontext(db_session)
        app.dependency_overrides[get_pipeline] = lambda: rag or pipeline(FakeGenerator(ANSWER))
        client = httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url="http://test")
        clients.append(client)
        return client

    yield factory
    for client in clients:
        await client.aclose()


async def ask(client: httpx2.AsyncClient, body: dict, headers=HEADERS) -> list[tuple[str, Any]]:
    response = await client.post("/api/v1/chat", json=body, headers=headers)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    return parse_sse(response.text)


async def messages_of(db: AsyncSession, conversation_id: str) -> list[Message]:
    result = await db.scalars(
        select(Message)
        .where(Message.conversation_id == uuid.UUID(conversation_id))
        .order_by(Message.created_at)
    )
    return list(result)


# --- POST /chat ------------------------------------------------------------------------


async def test_chat_streams_the_events_in_order_and_saves_both_messages(
    make_client: ClientFactory, db_session: AsyncSession
) -> None:
    events = await ask(make_client(), {"message": "  Attendance rule?  "})

    names = [name for name, _ in events]
    assert names[0] == "meta" and names[-2:] == ["citations", "done"]
    assert set(names[1:-2]) == {"token"}
    assert "".join(data["t"] for name, data in events if name == "token") == ANSWER

    meta, citations, done = events[0][1], events[-2][1], events[-1][1]
    assert [(c["n"], c["title"], c["page"], c["url"]) for c in citations] == [
        (1, "Academic Rules", 4, "https://www.lpu.in/academic-rules.pdf")
    ]
    assert done["abstained"] is False and done["cache_hit"] is False
    assert done["latency_ms"] >= 0

    conversation = await db_session.get(Conversation, uuid.UUID(meta["conversation_id"]))
    assert (conversation.session_id, conversation.client, conversation.app_version) == (
        VALID_SESSION_ID,
        Client.ANDROID,
        "1.2.0",
    )
    question, answer = await messages_of(db_session, meta["conversation_id"])
    assert (question.role, question.content) == (Role.USER, "Attendance rule?")
    assert answer.id == uuid.UUID(meta["message_id"])
    assert (answer.role, answer.content, answer.abstained) == (Role.ASSISTANT, ANSWER, False)
    assert answer.citations == citations
    assert (answer.model, answer.tokens_in) == ("fake-model", 900)
    assert answer.latency_ms is not None and answer.ttft_ms is not None


async def test_follow_up_continues_the_same_conversation(
    make_client: ClientFactory, db_session: AsyncSession
) -> None:
    client = make_client()
    first = await ask(client, {"message": "Attendance rule?"})
    conversation_id = first[0][1]["conversation_id"]

    second = await ask(client, {"message": "And fees?", "conversation_id": conversation_id})

    assert second[0][1]["conversation_id"] == conversation_id
    assert len(await messages_of(db_session, conversation_id)) == 4


async def test_another_sessions_conversation_is_not_found(make_client: ClientFactory) -> None:
    client = make_client()
    first = await ask(client, {"message": "Attendance rule?"})
    body = {"message": "Follow-up", "conversation_id": first[0][1]["conversation_id"]}

    response = await client.post("/api/v1/chat", json=body, headers=OTHER_HEADERS)

    assert response.status_code == 404


async def test_category_reaches_the_retriever(make_client: ClientFactory) -> None:
    retriever = FakeRetriever([ATTENDANCE])

    await ask(
        make_client(pipeline(FakeGenerator(ANSWER), retriever)),
        {"message": "Late fee?", "category": "fees"},
    )

    assert retriever.calls == [("Late fee?", "fees")]


async def test_abstained_answer_is_flagged_and_saved(
    make_client: ClientFactory, db_session: AsyncSession
) -> None:
    llm = FakeGenerator("never used")
    weak = RagPipeline(
        FakeRetriever([ATTENDANCE, FEES]),
        FakeScorer(SCORES),
        llm,
        PipelineConfig(abstain_threshold=9.0, abstain_sources=2),
    )

    events = await ask(make_client(weak), {"message": "Wifi password?"})

    assert [data["t"] for name, data in events if name == "token"] == [NOT_FOUND_ANSWER]
    assert [c["chunk_id"] for c in events[-2][1]] == ["chunk-1", "chunk-2"]  # closest sources
    assert events[-1][1]["abstained"] is True
    assert llm.calls == []
    _, answer = await messages_of(db_session, events[0][1]["conversation_id"])
    assert answer.abstained and answer.model is None


async def test_answer_without_citations_carries_the_notice(make_client: ClientFactory) -> None:
    events = await ask(make_client(pipeline(FakeGenerator("You need 75%."))), {"message": "Rule?"})

    text = "".join(data["t"] for name, data in events if name == "token")
    assert text.endswith(UNVERIFIED_NOTICE)
    assert events[-2] == ("citations", [])


async def test_rate_limit_sends_retry_after_and_saves_no_answer(
    make_client: ClientFactory, db_session: AsyncSession
) -> None:
    events = await ask(make_client(pipeline(busy_generator(retry_after=24))), {"message": "Rule?"})

    assert [name for name, _ in events] == ["meta", "error"]
    assert events[1][1] == {"code": "rate_limited", "retry_after": 24}
    saved = await messages_of(db_session, events[0][1]["conversation_id"])
    assert [message.role for message in saved] == [Role.USER]


async def test_llm_outage_is_reported_as_unavailable(make_client: ClientFactory) -> None:
    rag = pipeline(FakeGenerator(error=LlmUnavailableError("no key")))

    events = await ask(make_client(rag), {"message": "Rule?"})

    assert events[-1] == ("error", {"code": "unavailable"})


async def test_unexpected_failures_are_internal_errors_without_details(
    make_client: ClientFactory,
) -> None:
    class BrokenRetriever:
        async def search(self, question, category=None):
            raise ConnectionError("qdrant.internal:6333 refused")

    events = await ask(
        make_client(pipeline(FakeGenerator(ANSWER), BrokenRetriever())), {"message": "Rule?"}
    )

    assert events[-1] == ("error", {"code": "internal"})
    assert "qdrant.internal" not in json.dumps(events)


# --- GET /conversations/{id} -----------------------------------------------------------


async def test_conversation_history_matches_what_was_streamed(make_client: ClientFactory) -> None:
    client = make_client()
    events = await ask(client, {"message": "Attendance rule?"})
    conversation_id = events[0][1]["conversation_id"]

    response = await client.get(f"/api/v1/conversations/{conversation_id}", headers=HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == conversation_id
    question, answer = body["messages"]
    assert (question["role"], question["content"], question["citations"]) == (
        "user",
        "Attendance rule?",
        [],
    )
    assert (answer["role"], answer["content"]) == ("assistant", ANSWER)
    assert answer["id"] == events[0][1]["message_id"]
    assert answer["citations"] == events[-2][1]


async def test_conversation_history_is_private_to_its_session(make_client: ClientFactory) -> None:
    client = make_client()
    events = await ask(client, {"message": "Attendance rule?"})
    path = f"/api/v1/conversations/{events[0][1]['conversation_id']}"

    assert (await client.get(path, headers=OTHER_HEADERS)).status_code == 404
    assert (
        await client.get(f"/api/v1/conversations/{OTHER_UUID}", headers=HEADERS)
    ).status_code == 404


# --- POST /feedback --------------------------------------------------------------------


async def test_rating_an_answer_again_replaces_the_first_rating(
    make_client: ClientFactory, db_session: AsyncSession
) -> None:
    client = make_client()
    events = await ask(client, {"message": "Attendance rule?"})
    message_id = events[0][1]["message_id"]

    report = {"message_id": message_id, "rating": -1, "reason": "offensive", "comment": "Rude"}
    assert (await client.post("/api/v1/feedback", json=report, headers=HEADERS)).status_code == 204
    thumbs_up = {"message_id": message_id, "rating": 1}
    assert (
        await client.post("/api/v1/feedback", json=thumbs_up, headers=HEADERS)
    ).status_code == 204

    rows = list(await db_session.scalars(select(Feedback)))
    assert [(row.rating, row.reason, row.comment) for row in rows] == [(1, None, None)]


async def test_offensive_reports_are_stored(
    make_client: ClientFactory, db_session: AsyncSession
) -> None:
    client = make_client()
    events = await ask(client, {"message": "Attendance rule?"})
    report = {"message_id": events[0][1]["message_id"], "rating": -1, "reason": "offensive"}

    await client.post("/api/v1/feedback", json=report, headers=HEADERS)

    row = await db_session.scalar(select(Feedback))
    assert (row.rating, row.reason) == (-1, FeedbackReason.OFFENSIVE)


async def test_only_your_own_answers_can_be_rated(
    make_client: ClientFactory, db_session: AsyncSession
) -> None:
    client = make_client()
    events = await ask(client, {"message": "Attendance rule?"})
    question, _ = await messages_of(db_session, events[0][1]["conversation_id"])

    others = {"message_id": events[0][1]["message_id"], "rating": 1}
    own_question = {"message_id": str(question.id), "rating": 1}
    unknown = {"message_id": OTHER_UUID, "rating": 1}

    assert (
        await client.post("/api/v1/feedback", json=others, headers=OTHER_HEADERS)
    ).status_code == 404
    assert (
        await client.post("/api/v1/feedback", json=own_question, headers=HEADERS)
    ).status_code == 404
    assert (await client.post("/api/v1/feedback", json=unknown, headers=HEADERS)).status_code == 404


# --- DELETE /session -------------------------------------------------------------------


async def test_clearing_data_deletes_only_the_callers_conversations(
    make_client: ClientFactory, db_session: AsyncSession
) -> None:
    client = make_client()
    mine = await ask(client, {"message": "Attendance rule?"})
    await client.post(
        "/api/v1/feedback",
        json={"message_id": mine[0][1]["message_id"], "rating": 1},
        headers=HEADERS,
    )
    theirs = await ask(client, {"message": "Late fee?"}, headers=OTHER_HEADERS)

    response = await client.delete("/api/v1/session", headers=HEADERS)

    assert response.status_code == 204
    count = func.count()
    assert await db_session.scalar(select(count).select_from(Feedback)) == 0
    assert await messages_of(db_session, mine[0][1]["conversation_id"]) == []
    assert len(await messages_of(db_session, theirs[0][1]["conversation_id"])) == 2
    sessions = await db_session.scalars(select(Conversation.session_id))
    assert list(sessions) == [OTHER_UUID]


# --- GET /sources ----------------------------------------------------------------------


def document(
    source_id: str, title: str, category: DocumentCategory, status: DocumentStatus, version: int = 1
) -> Document:
    return Document(
        source_id=source_id,
        title=title,
        source_url=f"https://www.lpu.in/{source_id}.pdf",
        category=category,
        academic_year="2025-26",
        content_hash="a" * 64,
        version=version,
        status=status,
        page_count=3,
        chunk_count=5,
    )


async def test_sources_lists_active_documents_by_category_and_title(
    make_client: ClientFactory, db_session: AsyncSession
) -> None:
    db_session.add_all(
        [
            document(
                "hostel-rules", "Hostel Rules", DocumentCategory.HOSTEL, DocumentStatus.ACTIVE
            ),
            document("exam-b", "Reappear Exams", DocumentCategory.EXAMS, DocumentStatus.ACTIVE),
            document("exam-a", "End-Term Exams", DocumentCategory.EXAMS, DocumentStatus.ACTIVE),
            document(
                "exam-a",
                "End-Term Exams (old)",
                DocumentCategory.EXAMS,
                DocumentStatus.SUPERSEDED,
                version=0,
            ),
        ]
    )
    await db_session.flush()

    response = await make_client().get("/api/v1/sources")

    assert response.status_code == 200
    assert [(item["source_id"], item["category"]) for item in response.json()] == [
        ("exam-a", "exams"),
        ("exam-b", "exams"),
        ("hostel-rules", "hostel"),
    ]
    assert set(response.json()[0]) == {
        "source_id",
        "title",
        "category",
        "source_url",
        "academic_year",
        "ingested_at",
    }
