"""GET /api/v1/conversations/{id}: messages of one conversation, for its own session only.

Another session's conversation gets the same 404 as one that doesn't exist, so the
response never reveals that an ID is in use.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict

from app.api.deps import CurrentSession
from app.db.chats import conversation_messages, find_conversation
from app.db.session import DbSession
from app.enums import DocumentCategory, Role

router = APIRouter(tags=["conversations"])


class CitationOut(BaseModel):
    """The citation shape streamed by POST /chat and stored in messages.citations."""

    n: int
    chunk_id: str
    document_id: str
    source_id: str
    title: str
    url: str
    category: DocumentCategory
    section: str | None
    page: int | None  # first page; None for documents without pages
    page_end: int | None
    text: str  # the cited passage


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: Role
    content: str
    citations: list[CitationOut]
    abstained: bool
    created_at: datetime


class ConversationOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    messages: list[MessageOut]


@router.get(
    "/conversations/{conversation_id}",
    responses={404: {"description": "Conversation not found for this session"}},
)
async def get_conversation(
    conversation_id: uuid.UUID, session: CurrentSession, db: DbSession
) -> ConversationOut:
    conversation = await find_conversation(db, session.session_id, conversation_id)
    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    messages = await conversation_messages(db, conversation.id)
    return ConversationOut(
        id=conversation.id,
        created_at=conversation.created_at,
        messages=[MessageOut.model_validate(message) for message in messages],
    )
