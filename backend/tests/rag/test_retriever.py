"""Hybrid search against Qdrant's in-memory mode, with tiny fake vectors.

The fake dense encoder maps a text to a 3-d "topic" vector, and the fake sparse encoder
turns words into term ids, so each test can say which search should find what.
"""

import zlib
from dataclasses import replace

import pytest
from qdrant_client import AsyncQdrantClient, models

from app.collection import DENSE_VECTOR, SPARSE_VECTOR
from app.rag.retriever import HybridRetriever, RetrievedChunk, rrf_order, search_filter

COLLECTION = "kb_chunks"
TOPICS = ("attendance", "hostel", "fee")


def fake_dense(text: str) -> list[float]:
    lowered = text.lower()
    vector = [1.0 if topic in lowered else 0.0 for topic in TOPICS]
    return vector if any(vector) else [0.1, 0.1, 0.1]


def fake_sparse(text: str) -> models.SparseVector:
    ids = sorted({zlib.crc32(word.encode()) % 100_000 for word in text.lower().split()})
    return models.SparseVector(indices=ids, values=[1.0] * len(ids))


def payload(n: int, text: str, category: str, origin: str = "lpu.in") -> dict:
    return {
        "chunk_id": f"chunk-{n}",
        "document_id": f"doc-{n}",
        "source_id": f"source-{n}",
        "title": f"Document {n}",
        "source_url": f"https://www.lpu.in/{n}.pdf",
        "category": category,
        "academic_year": "2025-26",
        "origin": origin,
        "chunk_index": 0,
        "page_start": n,
        "page_end": n,
        "headings": ["Rules"],
        "text": text,
        "token_count": 20,
        "corpus_version": 1,
        "embed_model": "fake",
    }


CHUNKS = [
    (1, "attendance must be 75 percent", "academics", "lpu.in"),
    (2, "hostel gates close at 10 pm", "hostel", "lpu.in"),
    (3, "late fee is charged after the due date", "fees", "ums"),
    (4, "form er-5 is used for attendance appeals", "academics", "ums"),
]


@pytest.fixture
async def client() -> AsyncQdrantClient:
    client = AsyncQdrantClient(":memory:")
    await client.create_collection(
        COLLECTION,
        vectors_config={DENSE_VECTOR: models.VectorParams(size=3, distance=models.Distance.COSINE)},
        sparse_vectors_config={SPARSE_VECTOR: models.SparseVectorParams()},
    )
    await client.upsert(
        COLLECTION,
        points=[
            models.PointStruct(
                id=n,
                vector={DENSE_VECTOR: fake_dense(text), SPARSE_VECTOR: fake_sparse(text)},
                payload=payload(n, text, category, origin),
            )
            for n, text, category, origin in CHUNKS
        ],
    )
    return client


def retriever(client: AsyncQdrantClient, origins: tuple[str, ...] = ()) -> HybridRetriever:
    return HybridRetriever(
        client,
        COLLECTION,
        fake_dense,
        sparse=fake_sparse,
        dense_limit=3,
        sparse_limit=3,
        fused_limit=3,
        origins=origins,
    )


async def test_hybrid_search_returns_chunks_with_their_payload(client) -> None:
    results = await retriever(client).search("what attendance is required")

    assert results[0].source_id in {"source-1", "source-4"}
    first = next(chunk for chunk in results if chunk.chunk_id == "chunk-1")
    assert first == RetrievedChunk(
        chunk_id="chunk-1",
        document_id="doc-1",
        source_id="source-1",
        title="Document 1",
        source_url="https://www.lpu.in/1.pdf",
        category="academics",
        academic_year="2025-26",
        page_start=1,
        page_end=1,
        headings=("Rules",),
        text="attendance must be 75 percent",
        token_count=20,
        score=first.score,
    )


async def test_keyword_search_finds_exact_terms_dense_misses(client) -> None:
    # "er-5" has no topic, so the dense vector is uninformative; BM25 still matches it.
    results = await retriever(client).search("er-5")

    assert results[0].chunk_id == "chunk-4"


async def test_category_filter_applies_to_both_searches(client) -> None:
    results = await retriever(client).search("attendance hostel fee", category="hostel")

    assert {chunk.category for chunk in results} == {"hostel"}


async def test_origin_filter_leaves_out_other_document_groups(client) -> None:
    results = await retriever(client, origins=("lpu.in",)).search("late fee attendance")

    assert {chunk.chunk_id for chunk in results} <= {"chunk-1", "chunk-2"}
    assert results


def test_no_filter_when_nothing_is_restricted() -> None:
    assert search_filter(None, ()) is None


def test_chunk_section_is_the_innermost_heading() -> None:
    point = models.ScoredPoint(id=1, version=0, score=0.5, payload=payload(1, "x", "fees"))
    chunk = RetrievedChunk.from_point(point)

    assert chunk.section == "Rules"
    assert chunk.text_with_headings == "Rules\nx"


def test_rrf_ties_are_ordered_by_chunk_id() -> None:
    base = RetrievedChunk.from_point(
        models.ScoredPoint(id=1, version=0, score=0.0, payload=payload(1, "x", "fees"))
    )
    chunks = [
        replace(base, chunk_id=chunk_id, score=score)
        for chunk_id, score in [("c", 0.5), ("b", 0.25), ("a", 0.5), ("d", 1.0)]
    ]

    assert [chunk.chunk_id for chunk in rrf_order(chunks, 3)] == ["d", "a", "c"]


async def test_fused_limit_cuts_after_the_tie_break(client) -> None:
    def hybrid(fused_limit: int) -> HybridRetriever:
        return HybridRetriever(
            client,
            COLLECTION,
            fake_dense,
            sparse=fake_sparse,
            dense_limit=4,
            sparse_limit=4,
            fused_limit=fused_limit,
        )

    question = "attendance hostel fee"
    everything = await hybrid(8).search(question)
    top = await hybrid(2).search(question)

    assert everything == rrf_order(everything, len(everything))
    assert top == everything[:2]
