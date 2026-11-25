"""Ingestion orchestration (SPEC §8): fetch -> parse -> chunk -> embed -> upsert -> register.

For each source:
- unchanged file (same sha256 as the active version): skipped. If only its
  sources.yaml metadata changed, the row and every chunk's payload are updated;
- new or changed file: parsed, chunked, embedded and upserted as a new version;
  the old version's points are deleted and its row marked `superseded`;
- `force`: re-index an unchanged file in place (e.g. after changing chunk size).

Each source is committed on its own, so one bad file never blocks the rest, and a run
that changes anything records one new `corpus_version` (which invalidates the answer
cache, SPEC §7.2). Document IDs are deterministic (source id + version) and the new
ID's points are cleared before upserting, so re-running after a crash, or against a
fresh database, never leaves duplicate or orphaned chunks.

Changing only an entry's `origin` is not detected (Postgres does not store it);
re-run that source with `force`.
"""

import logging
from collections.abc import Callable, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from qdrant_client import QdrantClient
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document
from app.enums import DocumentStatus
from app.ingest import index, registry
from app.ingest.chunk import Chunk
from app.ingest.fetch import FetchedFile, FetchError
from app.ingest.parse import ParsedDocument, ParseError
from app.ingest.sources import Source

logger = logging.getLogger(__name__)


class Outcome(StrEnum):
    INGESTED = "ingested"  # first version of a source
    UPDATED = "updated"  # file changed: new version, old one superseded
    REINDEXED = "reindexed"  # same file, re-chunked because of --force
    METADATA = "metadata"  # same file, sources.yaml details changed
    UNCHANGED = "unchanged"
    PRUNED = "pruned"  # no longer in sources.yaml: removed from the index
    FAILED = "failed"


@dataclass(frozen=True)
class SourceResult:
    source_id: str
    outcome: Outcome
    detail: str = ""
    chunks: int = 0
    version: int | None = None


class FetcherLike(Protocol):
    def get(self, source: Source) -> FetchedFile: ...


class ParserLike(Protocol):
    def parse(self, path: Path) -> ParsedDocument: ...


class EmbedderLike(Protocol):
    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]
ChunkFn = Callable[[ParsedDocument], list[Chunk]]


def metadata_differs(doc: Document, source: Source) -> bool:
    return (doc.title, doc.source_url, doc.category, doc.academic_year) != (
        source.title,
        source.url,
        source.category,
        source.academic_year,
    )


def apply_metadata(doc: Document, source: Source) -> None:
    doc.title = source.title
    doc.source_url = source.url
    doc.category = source.category
    doc.academic_year = source.academic_year


class Ingestor:
    def __init__(
        self,
        *,
        qdrant: QdrantClient,
        collection: str,
        session_factory: SessionFactory,
        fetcher: FetcherLike,
        parser: ParserLike,
        chunk: ChunkFn,
        embedder: EmbedderLike,
        embed_model: str,
        sparse: index.SparseFactory = index.bm25_document,
    ) -> None:
        self.qdrant = qdrant
        self.collection = collection
        self.session_factory = session_factory
        self.fetcher = fetcher
        self.parser = parser
        self.chunk = chunk
        self.embedder = embedder
        self.embed_model = embed_model
        self.sparse = sparse
        self._run_corpus_version: int | None = None

    async def run(
        self, sources: Sequence[Source], *, force: bool = False, prune_missing: bool = False
    ) -> list[SourceResult]:
        """Ingest each source; with `prune_missing`, drop documents no longer listed."""
        self._run_corpus_version = None
        results = []
        for source in sources:
            try:
                result = await self._ingest(source, force=force)
            except (FetchError, ParseError) as error:
                result = SourceResult(source.id, Outcome.FAILED, str(error))
            log = logger.warning if result.outcome is Outcome.FAILED else logger.info
            log("%s: %s %s", source.id, result.outcome, result.detail)
            results.append(result)
        if prune_missing:
            results.extend(await self._prune({s.id for s in sources}))
        return results

    async def _ingest(self, source: Source, *, force: bool) -> SourceResult:
        fetched = self.fetcher.get(source)
        async with self.session_factory() as session:
            active = await registry.active_document(session, source.id)
            same_file = active is not None and active.content_hash == fetched.sha256
            if same_file and not force:
                assert active is not None
                if metadata_differs(active, source):
                    return await self._update_metadata(session, active, source)
                return SourceResult(
                    source.id,
                    Outcome.UNCHANGED,
                    fetched.note or "",
                    active.chunk_count,
                    active.version,
                )

            parsed = self.parser.parse(fetched.path)
            try:
                chunks = self.chunk(parsed)
            except Exception as error:  # docling-core raises assorted errors
                raise ParseError(f"chunking failed: {error}") from error
            if not chunks:
                raise ParseError("the document produced no text chunks")
            vectors = self.embedder.embed([c.embed_text for c in chunks])

            corpus_version = await self._corpus_version(session)
            if same_file and active is not None:
                version, doc_id = active.version, active.id
            else:
                version = await registry.latest_version(session, source.id) + 1
                doc_id = index.document_id(source.id, version)
            meta = index.DocumentMeta(
                document_id=doc_id,
                source_id=source.id,
                title=source.title,
                source_url=source.url,
                category=source.category.value,
                academic_year=source.academic_year,
                origin=source.origin_label,
                content_hash=fetched.sha256,
                corpus_version=corpus_version,
                embed_model=self.embed_model,
            )
            points = index.build_points(meta, chunks, vectors, self.sparse)
            # Clear this ID first: the chunk count may have changed, or a crashed run
            # (or a reset database) may have left points under it.
            index.delete_document_points(self.qdrant, self.collection, doc_id)
            index.upsert_points(self.qdrant, self.collection, points)

            if same_file and active is not None:
                apply_metadata(active, source)
                active.page_count = parsed.page_count
                active.chunk_count = len(chunks)
                active.ingested_at = func.now()
                outcome = Outcome.REINDEXED
            else:
                if active is not None:
                    index.delete_document_points(self.qdrant, self.collection, active.id)
                    active.status = DocumentStatus.SUPERSEDED
                    await session.flush()  # free the "one active row per source" slot
                session.add(
                    Document(
                        id=doc_id,
                        source_id=source.id,
                        title=source.title,
                        source_url=source.url,
                        category=source.category,
                        academic_year=source.academic_year,
                        content_hash=fetched.sha256,
                        version=version,
                        status=DocumentStatus.ACTIVE,
                        page_count=parsed.page_count,
                        chunk_count=len(chunks),
                    )
                )
                outcome = Outcome.UPDATED if active is not None else Outcome.INGESTED
            await session.commit()
        detail = f"{len(chunks)} chunks, {parsed.page_count} pages"
        if fetched.note:
            detail += f"; {fetched.note}"
        return SourceResult(source.id, outcome, detail, len(chunks), version)

    async def _update_metadata(
        self, session: AsyncSession, doc: Document, source: Source
    ) -> SourceResult:
        await self._corpus_version(session)
        payload = {
            "title": source.title,
            "source_url": source.url,
            "category": source.category.value,
            "academic_year": source.academic_year,
            "origin": source.origin_label,
        }
        index.update_document_payload(self.qdrant, self.collection, doc.id, payload)
        apply_metadata(doc, source)
        await session.commit()
        return SourceResult(
            source.id,
            Outcome.METADATA,
            "sources.yaml details updated",
            doc.chunk_count,
            doc.version,
        )

    async def _prune(self, listed_ids: set[str]) -> list[SourceResult]:
        results = []
        async with self.session_factory() as session:
            for doc in await registry.active_documents(session):
                if doc.source_id in listed_ids:
                    continue
                await self._corpus_version(session)
                index.delete_document_points(self.qdrant, self.collection, doc.id)
                doc.status = DocumentStatus.SUPERSEDED
                await session.commit()
                logger.info("%s: pruned (no longer in sources.yaml)", doc.source_id)
                results.append(
                    SourceResult(doc.source_id, Outcome.PRUNED, "no longer in sources.yaml")
                )
        return results

    async def _corpus_version(self, session: AsyncSession) -> int:
        """The run's corpus version, recorded the first time the run changes something."""
        if self._run_corpus_version is None:
            self._run_corpus_version = await registry.add_corpus_version(session)
            await session.commit()
        return self._run_corpus_version
