"""`lumen stats` (SPEC §8): documents, chunks, average chunk tokens, corpus version."""

from collections import Counter
from dataclasses import dataclass, field

from qdrant_client import QdrantClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document
from app.enums import DocumentStatus
from app.ingest import registry


@dataclass(frozen=True)
class CorpusStats:
    corpus_version: int
    active_documents: int
    superseded_documents: int
    chunks: int
    avg_chunk_tokens: float
    max_chunk_tokens: int
    documents_by_category: dict[str, int] = field(default_factory=dict)
    chunks_by_origin: dict[str, int] = field(default_factory=dict)


async def collect_stats(
    session: AsyncSession, qdrant: QdrantClient, collection: str
) -> CorpusStats:
    active = await registry.active_documents(session)
    superseded = await session.scalar(
        select(func.count()).where(Document.status == DocumentStatus.SUPERSEDED)
    )

    tokens: list[int] = []
    origins: Counter[str] = Counter()
    if qdrant.collection_exists(collection):
        offset = None
        while True:
            points, offset = qdrant.scroll(
                collection,
                limit=512,
                offset=offset,
                with_payload=["token_count", "origin"],
                with_vectors=False,
            )
            for point in points:
                payload = point.payload or {}
                tokens.append(int(payload.get("token_count", 0)))
                origins[str(payload.get("origin", "unknown"))] += 1
            if offset is None:
                break

    return CorpusStats(
        corpus_version=await registry.current_corpus_version(session),
        active_documents=len(active),
        superseded_documents=int(superseded or 0),
        chunks=len(tokens),
        avg_chunk_tokens=sum(tokens) / len(tokens) if tokens else 0.0,
        max_chunk_tokens=max(tokens, default=0),
        documents_by_category=dict(sorted(Counter(d.category.value for d in active).items())),
        chunks_by_origin=dict(sorted(origins.items())),
    )
