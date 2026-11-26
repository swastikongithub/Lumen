"""Exporting the frozen CI fixture from Qdrant and loading it back (SPEC §11.5)."""

import json
from pathlib import Path

import pytest
from qdrant_client import QdrantClient, models

from app.collection import DENSE_VECTOR, SPARSE_VECTOR, ensure_collection
from app.evals.fixtures import (
    export_fixture,
    file_sha256,
    fixture_source_ids,
    load_fixture,
    read_fixture,
)

POINTS = [
    # id, source_id, chunk_index, origin, dense
    ("00000000-0000-0000-0000-000000000002", "b-doc", 1, "lpu.in", [0.0, 1.0, 0.0, 0.0]),
    ("00000000-0000-0000-0000-000000000001", "b-doc", 0, "lpu.in", [1.0, 0.0, 0.0, 0.0]),
    ("00000000-0000-0000-0000-000000000003", "a-doc", 0, "lpu.in", [0.12345678, 0.5, 0.5, 0.0]),
    ("00000000-0000-0000-0000-000000000004", "ums-doc", 0, "ums", [0.0, 0.0, 1.0, 0.0]),
]


@pytest.fixture
def qdrant() -> QdrantClient:
    client = QdrantClient(":memory:")
    ensure_collection(client, "kb_chunks", dim=4)
    client.upsert(
        "kb_chunks",
        points=[
            models.PointStruct(
                id=point_id,
                vector={
                    DENSE_VECTOR: dense,
                    SPARSE_VECTOR: models.SparseVector(indices=[7, 3], values=[0.5, 1.25]),
                },
                payload={"source_id": source_id, "chunk_index": index, "origin": origin},
            )
            for point_id, source_id, index, origin, dense in POINTS
        ],
    )
    return client


def test_export_keeps_public_documents_sorted(qdrant: QdrantClient, tmp_path: Path) -> None:
    path = tmp_path / "fixtures" / "chunks.jsonl"
    assert export_fixture(qdrant, "kb_chunks", path) == 3
    records = read_fixture(path)
    assert [(r["payload"]["source_id"], r["payload"]["chunk_index"]) for r in records] == [
        ("a-doc", 0),
        ("b-doc", 0),
        ("b-doc", 1),
    ]
    assert fixture_source_ids(records) == {"a-doc", "b-doc"}
    first = records[0]
    # Qdrant stores cosine vectors normalised; the export rounds them to 6 decimals.
    assert first["dense"][0] == 0.171992
    assert all(round(v, 6) == v for v in first["dense"])
    assert sorted(zip(first["bm25"]["indices"], first["bm25"]["values"], strict=True)) == [
        (3, 1.25),
        (7, 0.5),
    ]
    assert path.read_bytes().count(b"\r") == 0  # LF only, same hash everywhere


def test_export_other_origins_on_request(qdrant: QdrantClient, tmp_path: Path) -> None:
    path = tmp_path / "chunks.jsonl"
    assert export_fixture(qdrant, "kb_chunks", path, origins=("lpu.in", "ums")) == 4


def test_load_recreates_the_collection(qdrant: QdrantClient, tmp_path: Path) -> None:
    path = tmp_path / "chunks.jsonl"
    export_fixture(qdrant, "kb_chunks", path)
    records = read_fixture(path)
    load_fixture(qdrant, "kb_chunks_ci", records)
    load_fixture(qdrant, "kb_chunks_ci", records)  # again: replaced, not doubled
    assert qdrant.count("kb_chunks_ci").count == 3
    hits = qdrant.query_points(
        "kb_chunks_ci", query=[1.0, 0.0, 0.0, 0.0], using=DENSE_VECTOR, limit=1
    ).points
    assert str(hits[0].id) == "00000000-0000-0000-0000-000000000001"
    sparse = qdrant.query_points(
        "kb_chunks_ci",
        query=models.SparseVector(indices=[3], values=[1.0]),
        using=SPARSE_VECTOR,
        limit=5,
    ).points
    assert len(sparse) == 3


def test_load_rejects_an_empty_fixture(qdrant: QdrantClient) -> None:
    with pytest.raises(ValueError, match="empty"):
        load_fixture(qdrant, "kb_chunks_ci", [])


def test_hash_ignores_line_endings(tmp_path: Path) -> None:
    lf, crlf = tmp_path / "lf.jsonl", tmp_path / "crlf.jsonl"
    lines = [json.dumps({"a": 1}), json.dumps({"b": 2})]
    lf.write_bytes(("\n".join(lines) + "\n").encode())
    crlf.write_bytes(("\r\n".join(lines) + "\r\n").encode())
    assert file_sha256(lf) == file_sha256(crlf)
