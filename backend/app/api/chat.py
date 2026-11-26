"""POST /api/v1/chat: ask a question, get the answer as a Server-Sent Events stream.

Events (SPEC §10), in this order:

    meta       {"conversation_id": "...", "message_id": "..."}     always first
    token      {"t": "The minimum ..."}                             many, as text arrives
    citations  [{"n": 1, "title": ..., "page": 12, "url": ..., ...}]
    done       {"abstained": false, "cache_hit": false, "latency_ms": 1840}

When something fails, an `error` event replaces `citations` and `done`:

    error      {"code": "rate_limited", "retry_after": 30}   every LLM is rate-limited
               {"code": "unavailable"}                       no LLM could answer
               {"code": "internal"}                          anything else (details in the log)

A citation is {n, title, url, page, page_end, section, category, text, source_id,
document_id, chunk_id} (app/rag/citations.py). For an abstained answer the citations
are the closest sources rather than evidence.

The question is saved before streaming starts. The answer is saved just before
`citations`, so `message_id` can be rated (POST /feedback) as soon as `done` arrives.
Unknown conversation IDs, or ones from another session, get a plain 404 instead of a stream.

Before any of that, the request must pass the rate limits (app/api/rate_limit.py): over a
limit it gets 429 with Retry-After instead of a stream. A follow-up in an existing
conversation is rewritten with the conversation's last messages (app/rag/rewrite.py), and
every request is one Langfuse trace whose ID is stored with the answer.
"""

import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, StringConstraints

from app.api.deps import AppSettings, CurrentSession
from app.api.meta import current_corpus_version
from app.api.rate_limit import limit_per_ip, limit_per_session
from app.db.chats import add_message, find_conversation, recent_messages, start_conversation
from app.db.session import SessionFactory, Sessions
from app.enums import DocumentCategory, Role
from app.observability import Tracer
from app.rag.generator import LlmBusyError, LlmUnavailableError
from app.rag.pipeline import Answer, RagPipeline
from app.rag.rewrite import Turn

MAX_MESSAGE_CHARS = 1000

# no-cache: proxies must not store the stream. X-Accel-Buffering: nginx-style proxies
# must pass each event on at once instead of buffering the whole response.
SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    # Omit to start a new conversation.
    conversation_id: uuid.UUID | None = None
    message: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_MESSAGE_CHARS)
    ]
    # Omit (or null) for "All".
    category: DocumentCategory | None = None


@dataclass(frozen=True)
class ChatTurn:
    conversation_id: uuid.UUID
    message_id: uuid.UUID  # the answer's ID, announced in `meta` before it exists
    question: str
    category: str | None
    started: float  # time.perf_counter() when the request arrived
    history: tuple[Turn, ...] = ()  # earlier messages, oldest first, for the rewrite
    corpus_version: int | None = None  # for the answer cache


def get_pipeline(request: Request) -> RagPipeline:
    return request.app.state.pipeline


def get_tracer(request: Request) -> Tracer:
    return request.app.state.tracer


Pipeline = Annotated[RagPipeline, Depends(get_pipeline)]
CurrentTracer = Annotated[Tracer, Depends(get_tracer)]


def sse_event(event: str, data: object) -> str:
    """One SSE frame. json.dumps escapes newlines, so `data` is always a single line."""
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n"


def elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


@router.post(
    "/chat",
    response_class=StreamingResponse,
    responses={
        200: {"content": {"text/event-stream": {}}, "description": "SSE stream"},
        404: {"description": "Conversation not found for this session"},
        429: {"description": "Rate limit reached; see Retry-After"},
    },
)
@limit_per_ip
@limit_per_session  # innermost, so it is checked first (see app/api/rate_limit.py)
async def chat(
    request: Request,
    body: ChatRequest,
    session: CurrentSession,
    sessions: Sessions,
    pipeline: Pipeline,
    tracer: CurrentTracer,
    settings: AppSettings,
) -> StreamingResponse:
    started = time.perf_counter()
    history: list[Turn] = []
    async with sessions() as db:
        if body.conversation_id:
            conversation = await find_conversation(db, session.session_id, body.conversation_id)
            if conversation is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
            earlier = await recent_messages(db, conversation.id, settings.rewrite_history_turns)
            history = [Turn(message.role.value, message.content) for message in earlier]
        else:
            conversation = await start_conversation(
                db, session.session_id, session.client, session.app_version
            )
        conversation_id = conversation.id
        corpus_version = await current_corpus_version(db)
        await add_message(db, conversation_id, Role.USER, body.message)
        await db.commit()

    turn = ChatTurn(
        conversation_id=conversation_id,
        message_id=uuid.uuid4(),
        question=body.message,
        category=body.category.value if body.category else None,
        started=started,
        history=tuple(history),
        corpus_version=corpus_version,
    )
    return StreamingResponse(
        stream_answer(pipeline, sessions, turn, tracer),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


async def stream_answer(
    pipeline: RagPipeline,
    sessions: SessionFactory,
    turn: ChatTurn,
    tracer: Tracer | None = None,
) -> AsyncIterator[str]:
    tracer = tracer or Tracer()
    yield sse_event(
        "meta", {"conversation_id": str(turn.conversation_id), "message_id": str(turn.message_id)}
    )
    answer: Answer | None = None
    ttft_ms: int | None = None
    trace_input = {"question": turn.question, "category": turn.category}
    # Langfuse groups a conversation's traces by its ID; the device's session ID is never sent.
    with tracer.trace("chat", session_id=str(turn.conversation_id), input=trace_input) as root:
        try:
            async for item in pipeline.run(
                turn.question,
                turn.category,
                history=turn.history,
                corpus_version=turn.corpus_version,
            ):
                if isinstance(item, Answer):
                    answer = item
                    continue
                if ttft_ms is None:
                    ttft_ms = elapsed_ms(turn.started)
                yield sse_event("token", {"t": item})
            if answer is None:
                raise RuntimeError("the pipeline finished without an answer")
            latency_ms = elapsed_ms(turn.started)
            await save_answer(sessions, turn, answer, latency_ms, ttft_ms, root.trace_id)
        except LlmBusyError as error:
            logger.warning("Every LLM is rate-limited; retry after %ss", error.retry_after)
            root.update(level="WARNING", status_message="rate_limited")
            yield sse_event("error", {"code": "rate_limited", "retry_after": error.retry_after})
            return
        except LlmUnavailableError as error:
            logger.warning("No LLM could answer: %s", error)
            root.update(level="ERROR", status_message="unavailable")
            yield sse_event("error", {"code": "unavailable"})
            return
        except Exception:
            logger.exception("Chat request failed")
            root.update(level="ERROR", status_message="internal")
            yield sse_event("error", {"code": "internal"})
            return
        root.update(
            output={
                "answer": answer.content,
                "abstained": answer.abstained,
                "cache_hit": answer.cache_hit,
                "citations": len(answer.citations),
            },
            metadata={"latency_ms": latency_ms, "ttft_ms": ttft_ms},
        )

    # Scores and timings only: the question itself stays out of the logs.
    logger.info(
        "Answered: abstained=%s cache_hit=%s rewritten=%s best_score=%s citations=%d "
        "model=%s latency_ms=%d ttft_ms=%s",
        answer.abstained,
        answer.cache_hit,
        answer.rewritten_query is not None,
        f"{answer.best_score:.2f}" if answer.best_score is not None else None,
        len(answer.citations),
        answer.model,
        latency_ms,
        ttft_ms,
    )
    yield sse_event("citations", answer.citations)
    yield sse_event(
        "done",
        {"abstained": answer.abstained, "cache_hit": answer.cache_hit, "latency_ms": latency_ms},
    )


async def save_answer(
    sessions: SessionFactory,
    turn: ChatTurn,
    answer: Answer,
    latency_ms: int,
    ttft_ms: int | None,
    trace_id: str | None = None,
) -> None:
    async with sessions() as db:
        await add_message(
            db,
            turn.conversation_id,
            Role.ASSISTANT,
            answer.content,
            message_id=turn.message_id,
            rewritten_query=answer.rewritten_query,
            citations=answer.citations,
            abstained=answer.abstained,
            cache_hit=answer.cache_hit,
            model=answer.model,
            tokens_in=answer.tokens_in,
            tokens_out=answer.tokens_out,
            latency_ms=latency_ms,
            ttft_ms=ttft_ms,
            trace_id=trace_id,
        )
        await db.commit()
