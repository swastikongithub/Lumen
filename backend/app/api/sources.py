"""GET /api/v1/sources: every active indexed document. Public, no session needed."""

from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import not_implemented
from app.enums import DocumentCategory

router = APIRouter(tags=["sources"])


class SourceOut(BaseModel):
    source_id: str  # stable id from data/sources.yaml
    title: str
    category: DocumentCategory
    source_url: str
    academic_year: str | None
    ingested_at: datetime


@router.get("/sources")
async def list_sources() -> list[SourceOut]:
    not_implemented(phase=2)
