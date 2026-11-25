"""GET /api/v1/conversations/{id}: messages of one conversation, for its own session only."""

import uuid
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import CurrentSession, not_implemented
from app.enums import Role

router = APIRouter(tags=["conversations"])


class CitationOut(BaseModel):
    # Stored shape from SPEC §7.1. The fields the UI displays are settled in Phase 2.
    n: int
    chunk_id: str
    document_id: uuid.UUID
    page_start: int
    page_end: int


class MessageOut(BaseModel):
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


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: uuid.UUID, session: CurrentSession) -> ConversationOut:
    not_implemented(phase=2)
