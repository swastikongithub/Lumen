"""Step 7 of ingestion (SPEC §7.1, §8): document and corpus versions in Postgres."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CorpusVersion, Document
from app.enums import DocumentStatus


async def active_document(session: AsyncSession, source_id: str) -> Document | None:
    return await session.scalar(
        select(Document).where(
            Document.source_id == source_id, Document.status == DocumentStatus.ACTIVE
        )
    )


async def active_documents(session: AsyncSession) -> list[Document]:
    result = await session.scalars(
        select(Document)
        .where(Document.status == DocumentStatus.ACTIVE)
        .order_by(Document.source_id)
    )
    return list(result)


async def latest_version(session: AsyncSession, source_id: str) -> int:
    """Highest version stored for this source, 0 if it was never ingested."""
    value = await session.scalar(
        select(func.coalesce(func.max(Document.version), 0)).where(Document.source_id == source_id)
    )
    return int(value or 0)


async def current_corpus_version(session: AsyncSession) -> int:
    value = await session.scalar(select(func.coalesce(func.max(CorpusVersion.version), 0)))
    return int(value or 0)


async def add_corpus_version(session: AsyncSession) -> int:
    """Record a new corpus version (explicit number, so it always follows the highest)."""
    version = await current_corpus_version(session) + 1
    session.add(CorpusVersion(version=version))
    await session.flush()
    return version
