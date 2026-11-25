"""GET /api/v1/meta: version info the clients check on launch. Public, no session needed.

The Android app shows "Update required" when its version is below `min_app_version`.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.deps import AppSettings
from app.db.models import CorpusVersion
from app.db.session import DbSession

router = APIRouter(tags=["meta"])


class MetaOut(BaseModel):
    min_app_version: str
    latest_app_version: str
    notice: str | None
    corpus_version: int


async def current_corpus_version(db: DbSession) -> int:
    """Highest corpus version, or 0 before the first ingestion."""
    version = await db.scalar(select(func.max(CorpusVersion.version)))
    return version or 0


@router.get("/meta")
async def get_meta(
    settings: AppSettings,
    corpus_version: Annotated[int, Depends(current_corpus_version)],
) -> MetaOut:
    return MetaOut(
        min_app_version=settings.min_app_version,
        latest_app_version=settings.latest_app_version,
        notice=settings.app_notice,
        corpus_version=corpus_version,
    )
