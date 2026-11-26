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

from app.api.deps import CurrentSession
from app.db.chats import add_message, find_conversation, start_conversation
from app.db.session import SessionFactory, Sessions
from app.enums import DocumentCategory, Role
from app.rag.generator import LlmBusyError, LlmUnavailableError
from app.rag.pipeline import Answer, RagPipeline

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


def get_pipeline(request: Request) -> RagPipeline:
    return request.app.state.pipeline


Pipeline = Annotated[RagPipeline, Depends(get_pipeline)]


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
    },
)
async def chat(
    body: ChatRequest, session: CurrentSession, sessions: Sessions, pipeline: Pipeline
) -> StreamingResponse:
    started = time.perf_counter()
    async with sessions() as db:
        if body.conversation_id:
            conversation = await find_conversation(db, session.session_id, body.conversation_id)
            if conversation is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
        else:
            conversation = await start_conversation(
                db, session.session_id, session.client, session.app_version
            )
        conversation_id = conversation.id
        await add_message(db, conversation_id, Role.USER, body.message)
        await db.commit()

    turn = ChatTurn(
        conversation_id=conversation_id,
        message_id=uuid.uuid4(),
        question=body.message,
        category=body.category.value if body.category else None,
        started=started,
    )
    return StreamingResponse(
        stream_answer(pipeline, sessions, turn),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


async def stream_answer(
    pipeline: RagPipeline, sessions: SessionFactory, turn: ChatTurn
) -> AsyncIterator[str]:
    yield sse_event(
        "meta", {"conversation_id": str(turn.conversation_id), "message_id": str(turn.message_id)}
    )
    answer: Answer | None = None
    ttft_ms: int | None = None
    try:
        async for item in pipeline.run(turn.question, turn.category):
            if isinstance(item, Answer):
                answer = item
                continue
            if ttft_ms is None:
                ttft_ms = elapsed_ms(turn.started)
            yield sse_event("token", {"t": item})
        if answer is None:
            raise RuntimeError("the pipeline finished without an answer")
        latency_ms = elapsed_ms(turn.started)
        await save_answer(sessions, turn, answer, latency_ms, ttft_ms)
    except LlmBusyError as error:
        logger.warning("Every LLM is rate-limited; retry after %ss", error.retry_after)
        yield sse_event("error", {"code": "rate_limited", "retry_after": error.retry_after})
        return
    except LlmUnavailableError as error:
        logger.warning("No LLM could answer: %s", error)
        yield sse_event("error", {"code": "unavailable"})
        return
    except Exception:
        logger.exception("Chat request failed")
        yield sse_event("error", {"code": "internal"})
        return

    # Scores and timings only: the question itself stays out of the logs.
    logger.info(
        "Answered: abstained=%s best_score=%s citations=%d model=%s latency_ms=%d ttft_ms=%s",
        answer.abstained,
        f"{answer.best_score:.2f}" if answer.best_score is not None else None,
        len(answer.citations),
        answer.model,
        latency_ms,
        ttft_ms,
    )
    yield sse_event("citations", answer.citations)
    yield sse_event(
        "done", {"abstained": answer.abstained, "cache_hit": False, "latency_ms": latency_ms}
    )


async def save_answer(
    sessions: SessionFactory,
    turn: ChatTurn,
    answer: Answer,
    latency_ms: int,
    ttft_ms: int | None,
) -> None:
    async with sessions() as db:
        await add_message(
            db,
            turn.conversation_id,
            Role.ASSISTANT,
            answer.content,
            message_id=turn.message_id,
            citations=answer.citations,
            abstained=answer.abstained,
            model=answer.model,
            tokens_in=answer.tokens_in,
            tokens_out=answer.tokens_out,
            latency_ms=latency_ms,
            ttft_ms=ttft_ms,
        )
        await db.commit()
