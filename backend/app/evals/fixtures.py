"""The frozen corpus snapshot for the CI gate (SPEC §11.5): `evals/fixtures/chunks.jsonl`.

One line per chunk, sorted by document and chunk index so re-exports diff cleanly:

    {"id": "<point id>", "payload": {...}, "dense": [384 floats], "bm25": {"indices": [...],
     "values": [...]}}

Both vectors are copied from the live collection, so CI needs neither Docling nor the
embedding of every chunk: it loads the file into a fresh Qdrant collection and only
embeds the golden-set questions. The BM25 vectors are the term weights Qdrant stored at
ingestion; IDF is applied at query time from whatever the collection holds.

By default only `origin: lpu.in` documents are exported, because the file is committed
to a public repository and UMS-linked documents are not public pages (SPEC §3.2).
Golden-set questions whose evidence is not in the fixture are skipped by the gate.
"""

import hashlib
import json
from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient, models

from app.collection import DENSE_VECTOR, SPARSE_VECTOR, ensure_collection
from app.rag.retriever import search_filter

PUBLIC_ORIGINS = ("lpu.in",)
DECIMALS = 6  # vectors are rounded; the gate compares runs on the same file


def _round(values: Iterable[float]) -> list[float]:
    return [round(float(v), DECIMALS) for v in values]


def point_record(point: models.Record) -> dict[str, Any]:
    vectors = point.vector
    if not isinstance(vectors, dict):
        raise ValueError(f"point {point.id} has no named vectors")
    dense = vectors[DENSE_VECTOR]
    sparse = vectors[SPARSE_VECTOR]
    if not isinstance(sparse, models.SparseVector):
        raise ValueError(f"point {point.id} has no sparse BM25 vector")
    return {
        "id": str(point.id),
        "payload": point.payload or {},
        "dense": _round(dense),  # type: ignore[arg-type]
        "bm25": {"indices": list(sparse.indices), "values": _round(sparse.values)},
    }


def scroll_points(
    client: QdrantClient, collection: str, origins: Sequence[str]
) -> Iterator[models.Record]:
    offset = None
    while True:
        batch, offset = client.scroll(
            collection,
            scroll_filter=search_filter(None, origins),
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=[DENSE_VECTOR, SPARSE_VECTOR],
        )
        yield from batch
        if offset is None:
            return


def export_fixture(
    client: QdrantClient, collection: str, path: Path, origins: Sequence[str] = PUBLIC_ORIGINS
) -> int:
    """Write every chunk of the given origins to `path`. Returns the number written."""
    records = [point_record(point) for point in scroll_points(client, collection, origins)]
    records.sort(
        key=lambda r: (r["payload"].get("source_id", ""), r["payload"].get("chunk_index", 0))
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    return len(records)


def read_fixture(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def to_point(record: dict[str, Any]) -> models.PointStruct:
    sparse = record["bm25"]
    return models.PointStruct(
        id=record["id"],
        vector={
            DENSE_VECTOR: record["dense"],
            SPARSE_VECTOR: models.SparseVector(indices=sparse["indices"], values=sparse["values"]),
        },
        payload=record["payload"],
    )


def load_fixture(
    client: QdrantClient, collection: str, records: Sequence[dict[str, Any]], batch: int = 128
) -> None:
    """(Re)create `collection` and fill it with the fixture's points."""
    if not records:
        raise ValueError("the fixture is empty")
    if client.collection_exists(collection):
        client.delete_collection(collection)
    ensure_collection(client, collection, dim=len(records[0]["dense"]))
    for start in range(0, len(records), batch):
        points = [to_point(r) for r in records[start : start + batch]]
        client.upsert(collection, points=points, wait=True)


def fixture_source_ids(records: Iterable[dict[str, Any]]) -> set[str]:
    return {r["payload"]["source_id"] for r in records}


def file_sha256(path: Path) -> str:
    """Hash of a text file with line endings normalised, so a Windows checkout (CRLF)
    and the Linux CI runner (LF) agree."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
