"""Qdrant layout and payloads (SPEC §7.2). Uses Qdrant's in-memory mode, no server."""

import uuid

import pytest
from qdrant_client import QdrantClient, models

from app.ingest.chunk import Chunk
from app.ingest.index import (
    DENSE_VECTOR,
    PAYLOAD_INDEXES,
    SPARSE_VECTOR,
    DocumentMeta,
    bm25_document,
    build_points,
    count_document_points,
    delete_document_points,
    document_id,
    ensure_collection,
    point_id,
    update_document_payload,
    upsert_points,
)

# Every field SPEC §7.2 lists, plus source_id and token_count.
PAYLOAD_FIELDS = {
    "chunk_id",
    "document_id",
    "source_id",
    "title",
    "source_url",
    "category",
    "academic_year",
    "origin",
    "chunk_index",
    "page_start",
    "page_end",
    "headings",
    "text",
    "token_count",
    "corpus_version",
    "embed_model",
}


def meta(doc_id: uuid.UUID | None = None, content_hash: str = "a" * 64) -> DocumentMeta:
    return DocumentMeta(
        document_id=doc_id or document_id("exam-rules", 1),
        source_id="exam-rules",
        title="Examination Rules",
        source_url="https://ums.lpu.in/exam.pdf",
        category="exams",
        academic_year="2026-27",
        origin="ums",
        content_hash=content_hash,
        corpus_version=3,
        embed_model="BAAI/bge-small-en-v1.5",
    )


def chunks(n: int = 2) -> list[Chunk]:
    return [
        Chunk(i, f"rule {i}", f"Exams\nrule {i}", ("Exams",), i + 1, i + 1, 3) for i in range(n)
    ]


def sparse(text: str) -> models.SparseVector:
    """Stand-in for server-side BM25, which the in-memory client cannot run offline."""
    return models.SparseVector(indices=[len(text) % 97], values=[1.0])


@pytest.fixture
def qdrant() -> QdrantClient:
    client = QdrantClient(":memory:")
    ensure_collection(client, "kb_chunks", dim=4)
    return client


def test_ids_are_deterministic_and_distinct() -> None:
    doc = document_id("exam-rules", 1)

    assert document_id("exam-rules", 1) == doc
    assert document_id("exam-rules", 2) != doc
    assert point_id(doc, 0, "h") == point_id(doc, 0, "h")
    assert len({point_id(doc, 0, "h"), point_id(doc, 1, "h"), point_id(doc, 0, "g")}) == 3


def test_payload_has_every_spec_field() -> None:
    (point,) = build_points(meta(), chunks(1), [[0.1, 0.2, 0.3, 0.4]], sparse)

    assert set(point.payload) == PAYLOAD_FIELDS
    assert point.payload["chunk_id"] == point.id
    assert point.payload["origin"] == "ums"
    assert point.payload["headings"] == ["Exams"]
    assert point.payload["text"] == "rule 0"


def test_bm25_is_computed_from_the_contextualized_text() -> None:
    (point,) = build_points(meta(), chunks(1), [[0.1, 0.2, 0.3, 0.4]])

    bm25 = point.vector[SPARSE_VECTOR]
    assert isinstance(bm25, models.Document)
    assert bm25.model == "Qdrant/bm25"
    assert bm25.text == "Exams\nrule 0"
    assert bm25_document("x").model == "Qdrant/bm25"


def test_vector_count_must_match_chunks() -> None:
    with pytest.raises(ValueError, match="one dense vector per chunk"):
        build_points(meta(), chunks(2), [[0.1, 0.2, 0.3, 0.4]], sparse)


def test_collection_has_named_vectors_idf_and_payload_indexes(qdrant: QdrantClient) -> None:
    info = qdrant.get_collection("kb_chunks")

    assert info.config.params.vectors[DENSE_VECTOR].size == 4
    assert info.config.params.vectors[DENSE_VECTOR].distance == models.Distance.COSINE
    assert info.config.params.sparse_vectors[SPARSE_VECTOR].modifier == models.Modifier.IDF
    assert set(PAYLOAD_INDEXES) == {
        "category",
        "document_id",
        "source_id",
        "academic_year",
        "origin",
        "corpus_version",
    }
    ensure_collection(qdrant, "kb_chunks", dim=4)  # a second call is a no-op


def test_upsert_is_idempotent_and_delete_is_per_document(qdrant: QdrantClient) -> None:
    first, second = meta(document_id("a", 1)), meta(document_id("b", 1))
    vectors = [[0.1, 0.2, 0.3, 0.4], [0.4, 0.3, 0.2, 0.1]]
    upsert_points(qdrant, "kb_chunks", build_points(first, chunks(2), vectors, sparse))
    upsert_points(qdrant, "kb_chunks", build_points(first, chunks(2), vectors, sparse))
    upsert_points(qdrant, "kb_chunks", build_points(second, chunks(2), vectors, sparse))

    assert count_document_points(qdrant, "kb_chunks", first.document_id) == 2

    delete_document_points(qdrant, "kb_chunks", first.document_id)

    assert count_document_points(qdrant, "kb_chunks", first.document_id) == 0
    assert count_document_points(qdrant, "kb_chunks", second.document_id) == 2


def test_payload_update_reaches_every_chunk_of_a_document(qdrant: QdrantClient) -> None:
    m = meta()
    vectors = [[0.1, 0.2, 0.3, 0.4], [0.4, 0.3, 0.2, 0.1]]
    upsert_points(qdrant, "kb_chunks", build_points(m, chunks(2), vectors, sparse))

    update_document_payload(qdrant, "kb_chunks", m.document_id, {"title": "Exam Rules 2027"})

    points, _ = qdrant.scroll("kb_chunks", limit=10)
    assert {p.payload["title"] for p in points} == {"Exam Rules 2027"}
