"""POST /api/v1/chat: ask a question, get an SSE stream back (SPEC §9, §10).

Phase 0 defines the request contract and the session check. The pipeline comes in Phase 2.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter
from pydantic import BaseModel, StringConstraints

from app.api.deps import CurrentSession, not_implemented
from app.enums import DocumentCategory

MAX_MESSAGE_CHARS = 1000

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    # Omit to start a new conversation.
    conversation_id: uuid.UUID | None = None
    message: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_MESSAGE_CHARS)
    ]
    # Omit (or null) for "All".
    category: DocumentCategory | None = None


@router.post(
    "/chat",
    response_model=None,
    responses={200: {"content": {"text/event-stream": {}}, "description": "SSE stream"}},
)
async def chat(body: ChatRequest, session: CurrentSession) -> None:
    not_implemented(phase=2)
