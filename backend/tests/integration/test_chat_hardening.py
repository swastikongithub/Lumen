"""Phase 5 on POST /chat against real Postgres: follow-up rewriting, the answer cache,
tracing and rate limits (SPEC §9 steps 1-3 and 9), with a mocked LLM and retriever."""

import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import nullcontext

import httpx2
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.chat import get_pipeline
from app.api.meta import current_corpus_version
from app.config import Settings
from app.db.models import CorpusVersion, Message
from app.db.session import get_db, get_session_factory
from app.main import create_app
from app.observability import Tracer
from app.rag.pipeline import PipelineConfig, RagPipeline
from app.rag.rewrite import QueryRewriter
from tests.integration.test_chat_api import ANSWER, ATTENDANCE, FEES, HEADERS, SCORES, parse_sse
from tests.rag.fakes import (
    FakeCache,
    FakeGenerator,
    FakeRetriever,
    FakeScorer,
    FakeTracer,
    busy_generator,
)

pytestmark = pytest.mark.integration

STANDALONE = "What is the late fee?"


def pipeline(llm: FakeGenerator, *, cache=None, tracer=None) -> RagPipeline:
    return RagPipeline(
        FakeRetriever([ATTENDANCE, FEES]),
        FakeScorer(SCORES),
        llm,
        PipelineConfig(abstain_threshold=0.0),
        rewriter=QueryRewriter(llm),
        cache=cache,
        tracer=tracer,
    )


ClientFactory = Callable[..., httpx2.AsyncClient]


@pytest.fixture
async def make_client(db_session: AsyncSession) -> AsyncIterator[ClientFactory]:
    clients: list[httpx2.AsyncClient] = []

    def factory(
        rag: RagPipeline, *, settings: Settings | None = None, tracer: Tracer | None = None
    ) -> httpx2.AsyncClient:
        app: FastAPI = create_app(settings or Settings(_env_file=None))
        app.dependency_overrides[get_db] = lambda: db_session
        app.dependency_overrides[get_session_factory] = lambda: lambda: nullcontext(db_session)
        app.dependency_overrides[get_pipeline] = lambda: rag
        if tracer:
            app.state.tracer = tracer
        client = httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url="http://test")
        clients.append(client)
        return client

    yield factory
    for client in clients:
        await client.aclose()


async def ask(client: httpx2.AsyncClient, body: dict):
    response = await client.post("/api/v1/chat", json=body, headers=HEADERS)
    assert response.status_code == 200
    return parse_sse(response.text)


async def answer_saved(db: AsyncSession, events) -> Message:
    return await db.get(Message, uuid.UUID(events[0][1]["message_id"]))


async def test_a_follow_up_is_rewritten_from_the_conversation(
    make_client: ClientFactory, db_session: AsyncSession
) -> None:
    llm = FakeGenerator(ANSWER, rewrite=STANDALONE)
    rag = pipeline(llm)
    client = make_client(rag)
    first = await ask(client, {"message": "Attendance rule?"})

    second = await ask(
        client, {"message": "And the fee?", "conversation_id": first[0][1]["conversation_id"]}
    )

    assert len(llm.rewrite_calls) == 1  # the first question needed no rewrite
    sent = llm.rewrite_calls[0][1]["content"]
    assert "Student: Attendance rule?\nLumen: You need 75% attendance." in sent
    assert sent.endswith("LATEST MESSAGE: And the fee?")
    assert rag.retriever.calls[1] == (STANDALONE, None)
    assert (await answer_saved(db_session, first)).rewritten_query is None
    assert (await answer_saved(db_session, second)).rewritten_query == STANDALONE


async def test_a_repeated_question_is_answered_from_the_cache(
    make_client: ClientFactory, db_session: AsyncSession
) -> None:
    db_session.add(CorpusVersion())
    await db_session.flush()
    version = await current_corpus_version(db_session)
    cache, llm = FakeCache(), FakeGenerator(ANSWER)
    client = make_client(pipeline(llm, cache=cache))

    first = await ask(client, {"message": "Attendance rule?"})
    again = await ask(client, {"message": "attendance rule"})

    assert first[-1][1]["cache_hit"] is False
    assert again[-1][1]["cache_hit"] is True
    assert again[-2] == first[-2]  # the same citations
    assert len(llm.calls) == 1
    assert cache.lookups[-1] == ("attendance rule", None, version)
    saved = await answer_saved(db_session, again)
    assert saved.cache_hit and saved.model is None and saved.content == ANSWER


async def test_each_request_is_one_trace_and_its_id_is_saved(
    make_client: ClientFactory, db_session: AsyncSession
) -> None:
    tracer = FakeTracer()
    client = make_client(pipeline(FakeGenerator(ANSWER), tracer=tracer), tracer=tracer)

    events = await ask(client, {"message": "Attendance rule?", "category": "academics"})

    root = tracer.spans[0]
    assert root.name == "chat"
    assert root.fields["session_id"] == events[0][1]["conversation_id"]  # not the device ID
    assert root.input == {"question": "Attendance rule?", "category": "academics"}
    assert root.fields["output"]["answer"] == ANSWER
    assert tracer.names[1:] == ["retrieve", "rerank", "generate"]
    assert (await answer_saved(db_session, events)).trace_id == "trace-1"


async def test_a_failed_request_marks_its_trace(make_client: ClientFactory) -> None:
    tracer = FakeTracer()
    client = make_client(pipeline(busy_generator(retry_after=24)), tracer=tracer)

    events = await ask(client, {"message": "Attendance rule?"})

    assert events[-1][0] == "error"
    assert tracer.spans[0].fields["level"] == "WARNING"
    assert tracer.spans[0].fields["status_message"] == "rate_limited"


async def test_over_the_limit_a_question_gets_429_and_is_not_saved(
    make_client: ClientFactory, db_session: AsyncSession
) -> None:
    settings = Settings(_env_file=None, rate_limit_session="2/minute")
    client = make_client(pipeline(FakeGenerator(ANSWER)), settings=settings)
    await ask(client, {"message": "Attendance rule?"})
    await ask(client, {"message": "Late fee?"})

    response = await client.post("/api/v1/chat", json={"message": "Hostel?"}, headers=HEADERS)

    assert response.status_code == 429
    assert response.json()["code"] == "too_many_requests"
    assert int(response.headers["Retry-After"]) >= 1
    saved = await db_session.scalar(select(func.count()).select_from(Message))
    assert saved == 4  # two questions and two answers; the third question never got in
