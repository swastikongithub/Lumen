"""Idempotent re-ingestion (SPEC §8): real Postgres, in-memory Qdrant, fake models.

The fetcher, Docling and FastEmbed are replaced by small fakes, so these tests check
the bookkeeping (versions, supersede, corpus versions, point IDs), not the models.
"""

import hashlib
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from qdrant_client import QdrantClient, models
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.collection import ensure_collection
from app.db.models import CorpusVersion, Document
from app.enums import DocumentCategory, DocumentStatus
from app.ingest.chunk import Chunk
from app.ingest.fetch import FetchedFile, FetchError
from app.ingest.parse import ParsedDocument, ParseError
from app.ingest.pipeline import Ingestor, Outcome
from app.ingest.sources import Source
from app.ingest.stats import collect_stats

pytestmark = pytest.mark.integration

COLLECTION = "kb_chunks"


class FakeFetcher:
    """Serves file contents from a dict, written to data/raw-like files."""

    def __init__(self, raw_dir: Path) -> None:
        self.raw_dir = raw_dir
        self.files: dict[str, str] = {}

    def get(self, source: Source) -> FetchedFile:
        if source.id not in self.files:
            raise FetchError("HTTP 404")
        path = self.raw_dir / f"{source.id}.md"
        path.write_text(self.files[source.id], encoding="utf-8")
        return FetchedFile(path, hashlib.sha256(path.read_bytes()).hexdigest(), downloaded=True)


class FakeParser:
    def parse(self, path: Path) -> ParsedDocument:
        text = path.read_text(encoding="utf-8")
        if text.startswith("BROKEN"):
            raise ParseError("3 of 4 pages have no text")
        return ParsedDocument(document=text, page_count=1)  # type: ignore[arg-type]


def chunk_lines(parsed: ParsedDocument) -> list[Chunk]:
    lines = [line for line in str(parsed.document).splitlines() if line.strip()]
    return [
        Chunk(i, line, f"Heading\n{line}", ("Heading",), 1, 1, 2) for i, line in enumerate(lines)
    ]


class FakeEmbedder:
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[float(len(t)), 1.0, 0.5, 0.25] for t in texts]


def fake_sparse(text: str) -> models.SparseVector:
    return models.SparseVector(indices=[len(text) % 97], values=[1.0])


def source(sid: str = "exam-rules", title: str = "Exam Rules") -> Source:
    return Source(
        id=sid, title=title, url=f"https://www.lpu.in/{sid}.pdf", category=DocumentCategory.EXAMS
    )


@pytest.fixture
def qdrant() -> QdrantClient:
    client = QdrantClient(":memory:")
    ensure_collection(client, COLLECTION, dim=4)
    return client


@pytest.fixture
def fetcher(tmp_path: Path) -> FakeFetcher:
    return FakeFetcher(tmp_path)


@pytest.fixture
def ingestor(db_session: AsyncSession, qdrant: QdrantClient, fetcher: FakeFetcher) -> Ingestor:
    @asynccontextmanager
    async def same_session() -> AsyncIterator[AsyncSession]:
        yield db_session  # the fixture rolls everything back after the test

    return Ingestor(
        qdrant=qdrant,
        collection=COLLECTION,
        session_factory=same_session,
        fetcher=fetcher,
        parser=FakeParser(),
        chunk=chunk_lines,
        embedder=FakeEmbedder(),
        embed_model="test-embedder",
        sparse=fake_sparse,
    )


def point_ids(qdrant: QdrantClient) -> set[str]:
    points, _ = qdrant.scroll(COLLECTION, limit=1000)
    return {str(p.id) for p in points}


def payloads(qdrant: QdrantClient) -> list[dict]:
    points, _ = qdrant.scroll(COLLECTION, limit=1000, with_payload=True)
    return [p.payload or {} for p in points]


async def documents(session: AsyncSession) -> list[Document]:
    return list(await session.scalars(select(Document).order_by(Document.version)))


async def corpus_versions(session: AsyncSession) -> list[int]:
    return list(
        await session.scalars(select(CorpusVersion.version).order_by(CorpusVersion.version))
    )


async def test_first_run_indexes_and_registers(
    ingestor: Ingestor, fetcher: FakeFetcher, qdrant: QdrantClient, db_session: AsyncSession
) -> None:
    fetcher.files["exam-rules"] = "rule one\nrule two\nrule three"

    (result,) = await ingestor.run([source()])

    assert (result.outcome, result.chunks, result.version) == (Outcome.INGESTED, 3, 1)
    (doc,) = await documents(db_session)
    assert (doc.status, doc.chunk_count, doc.version) == (DocumentStatus.ACTIVE, 3, 1)
    assert len(point_ids(qdrant)) == 3
    assert {p["document_id"] for p in payloads(qdrant)} == {str(doc.id)}
    assert {p["corpus_version"] for p in payloads(qdrant)} == {1}
    assert await corpus_versions(db_session) == [1]


async def test_rerun_without_changes_is_a_no_op(
    ingestor: Ingestor, fetcher: FakeFetcher, qdrant: QdrantClient, db_session: AsyncSession
) -> None:
    fetcher.files["exam-rules"] = "rule one\nrule two"
    await ingestor.run([source()])
    before = point_ids(qdrant)

    (result,) = await ingestor.run([source()])

    assert result.outcome is Outcome.UNCHANGED
    assert point_ids(qdrant) == before
    assert len(await documents(db_session)) == 1
    assert await corpus_versions(db_session) == [1]  # nothing changed, no new version


async def test_changed_file_supersedes_the_old_version(
    ingestor: Ingestor, fetcher: FakeFetcher, qdrant: QdrantClient, db_session: AsyncSession
) -> None:
    fetcher.files["exam-rules"] = "rule one\nrule two"
    await ingestor.run([source()])
    old_points = point_ids(qdrant)
    fetcher.files["exam-rules"] = "rule one (amended)\nrule two\nrule three"

    (result,) = await ingestor.run([source()])

    assert (result.outcome, result.version) == (Outcome.UPDATED, 2)
    old, new = await documents(db_session)
    assert (old.status, new.status) == (DocumentStatus.SUPERSEDED, DocumentStatus.ACTIVE)
    new_points = point_ids(qdrant)
    assert len(new_points) == 3 and not new_points & old_points  # old chunks are gone
    assert {p["document_id"] for p in payloads(qdrant)} == {str(new.id)}
    assert await corpus_versions(db_session) == [1, 2]


async def test_force_reindexes_the_same_file_in_place(
    ingestor: Ingestor, fetcher: FakeFetcher, qdrant: QdrantClient, db_session: AsyncSession
) -> None:
    fetcher.files["exam-rules"] = "rule one\nrule two"
    await ingestor.run([source()])
    before = point_ids(qdrant)

    (result,) = await ingestor.run([source()], force=True)

    assert (result.outcome, result.version) == (Outcome.REINDEXED, 1)
    assert point_ids(qdrant) == before  # same file, same deterministic IDs
    assert len(await documents(db_session)) == 1


async def test_metadata_change_updates_payloads_without_reindexing(
    ingestor: Ingestor, fetcher: FakeFetcher, qdrant: QdrantClient, db_session: AsyncSession
) -> None:
    fetcher.files["exam-rules"] = "rule one\nrule two"
    await ingestor.run([source()])
    before = point_ids(qdrant)

    (result,) = await ingestor.run([source(title="Examination Rules 2027")])

    assert result.outcome is Outcome.METADATA
    assert point_ids(qdrant) == before
    assert {p["title"] for p in payloads(qdrant)} == {"Examination Rules 2027"}
    (doc,) = await documents(db_session)
    assert doc.title == "Examination Rules 2027"


async def test_prune_removes_documents_dropped_from_the_manifest(
    ingestor: Ingestor, fetcher: FakeFetcher, qdrant: QdrantClient, db_session: AsyncSession
) -> None:
    fetcher.files["exam-rules"] = "rule one"
    fetcher.files["hostel-rules"] = "curfew at 10 pm"
    await ingestor.run([source(), source("hostel-rules", "Hostel Rules")])

    results = await ingestor.run([source()], prune_missing=True)

    assert [(r.source_id, r.outcome) for r in results] == [
        ("exam-rules", Outcome.UNCHANGED),
        ("hostel-rules", Outcome.PRUNED),
    ]
    assert {p["source_id"] for p in payloads(qdrant)} == {"exam-rules"}
    statuses = {d.source_id: d.status for d in await documents(db_session)}
    assert statuses["hostel-rules"] is DocumentStatus.SUPERSEDED


async def test_a_failing_source_does_not_block_the_others(
    ingestor: Ingestor, fetcher: FakeFetcher, qdrant: QdrantClient, db_session: AsyncSession
) -> None:
    fetcher.files["broken-scan"] = "BROKEN scan"
    fetcher.files["exam-rules"] = "rule one"

    results = await ingestor.run([source("broken-scan"), source("missing"), source()])

    assert [r.outcome for r in results] == [Outcome.FAILED, Outcome.FAILED, Outcome.INGESTED]
    assert "pages have no text" in results[0].detail
    assert "HTTP 404" in results[1].detail
    assert [d.source_id for d in await documents(db_session)] == ["exam-rules"]
    assert {p["source_id"] for p in payloads(qdrant)} == {"exam-rules"}


async def test_stats_report_what_is_indexed(
    ingestor: Ingestor, fetcher: FakeFetcher, qdrant: QdrantClient, db_session: AsyncSession
) -> None:
    fetcher.files["exam-rules"] = "rule one\nrule two"
    fetcher.files["hostel-rules"] = "curfew at 10 pm"
    await ingestor.run([source(), source("hostel-rules", "Hostel Rules")])
    fetcher.files["exam-rules"] = "rule one (amended)\nrule two\nrule three"
    await ingestor.run([source()])

    stats = await collect_stats(db_session, qdrant, COLLECTION)

    assert (stats.corpus_version, stats.active_documents, stats.superseded_documents) == (2, 2, 1)
    assert stats.chunks == 4
    assert (stats.avg_chunk_tokens, stats.max_chunk_tokens) == (2, 2)
    assert stats.documents_by_category == {"exams": 2}
    assert stats.chunks_by_origin == {"lpu.in": 4}
