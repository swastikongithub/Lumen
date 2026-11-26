"""GET /api/v1/sources: every active indexed document. Public, no session needed."""

from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.db.models import Document
from app.db.session import DbSession
from app.enums import DocumentCategory, DocumentStatus

router = APIRouter(tags=["sources"])


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source_id: str  # stable id from data/sources.yaml
    title: str
    category: DocumentCategory
    source_url: str
    academic_year: str | None
    ingested_at: datetime


@router.get("/sources")
async def list_sources(db: DbSession) -> list[SourceOut]:
    """Grouped by category, then alphabetical."""
    documents = await db.scalars(
        select(Document)
        .where(Document.status == DocumentStatus.ACTIVE)
        .order_by(Document.category, Document.title)
    )
    return [SourceOut.model_validate(document) for document in documents]
