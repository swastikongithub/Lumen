"""Steps 4 and 5 of ingestion (SPEC §7.2, §8): embed chunks and upsert them into Qdrant.

Each chunk becomes one point in `kb_chunks` with two named vectors:
- `dense`: FastEmbed bge-small-en-v1.5 (384-d, cosine), computed here;
- `bm25`: sent as `models.Document(text, model="Qdrant/bm25")`. Qdrant (1.15.3+) turns
  it into a sparse BM25 vector itself, and the collection's IDF modifier weights terms
  by how rare they are across the corpus. Queries use the same call (app/rag/retriever.py).
The collection layout itself is in app/collection.py.

Point IDs are UUIDv5 of document id + chunk index + content hash, so re-ingesting the
same file overwrites the same points instead of duplicating them.
"""

import uuid
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from qdrant_client import QdrantClient, models

from app.collection import DENSE_VECTOR, SPARSE_VECTOR, bm25_document
from app.ingest.chunk import Chunk

# Fixed namespaces: changing either would change every ID.
POINT_NAMESPACE = uuid.UUID("6f1c2a4e-3b5d-4c7e-9a1f-2d8e0b6c4a10")
DOCUMENT_NAMESPACE = uuid.UUID("0b9e7d2c-5a4f-4e1b-8c3d-7f6a2e1d9b05")

SparseFactory = Callable[[str], models.Document | models.SparseVector]


def document_id(source_id: str, version: int) -> uuid.UUID:
    """Deterministic, so a run that crashes before committing reuses the same IDs."""
    return uuid.uuid5(DOCUMENT_NAMESPACE, f"{source_id}:{version}")


def point_id(doc_id: uuid.UUID, chunk_index: int, content_hash: str) -> str:
    return str(uuid.uuid5(POINT_NAMESPACE, f"{doc_id}:{chunk_index}:{content_hash}"))


@dataclass(frozen=True)
class DocumentMeta:
    """Document-level fields repeated in every chunk's payload."""

    document_id: uuid.UUID
    source_id: str
    title: str
    source_url: str
    category: str
    academic_year: str | None
    origin: str  # "lpu.in" or "ums" (SPEC §3.2)
    content_hash: str
    corpus_version: int
    embed_model: str


def document_payload(meta: DocumentMeta) -> dict[str, Any]:
    """The payload fields that change when sources.yaml metadata changes."""
    return {
        "title": meta.title,
        "source_url": meta.source_url,
        "category": meta.category,
        "academic_year": meta.academic_year,
        "origin": meta.origin,
    }


def chunk_payload(meta: DocumentMeta, chunk: Chunk) -> dict[str, Any]:
    return {
        "chunk_id": point_id(meta.document_id, chunk.index, meta.content_hash),
        "document_id": str(meta.document_id),
        "source_id": meta.source_id,
        **document_payload(meta),
        "chunk_index": chunk.index,
        "page_start": chunk.page_start,
        "page_end": chunk.page_end,
        "headings": list(chunk.headings),
        "text": chunk.text,
        "token_count": chunk.token_count,
        "corpus_version": meta.corpus_version,
        "embed_model": meta.embed_model,
    }


def build_points(
    meta: DocumentMeta,
    chunks: Sequence[Chunk],
    dense_vectors: Sequence[Sequence[float]],
    sparse: SparseFactory = bm25_document,
) -> list[models.PointStruct]:
    if len(chunks) != len(dense_vectors):
        raise ValueError("one dense vector per chunk is required")
    return [
        models.PointStruct(
            id=point_id(meta.document_id, chunk.index, meta.content_hash),
            vector={DENSE_VECTOR: list(vector), SPARSE_VECTOR: sparse(chunk.embed_text)},
            payload=chunk_payload(meta, chunk),
        )
        for chunk, vector in zip(chunks, dense_vectors, strict=True)
    ]


def _document_filter(doc_id: uuid.UUID) -> models.Filter:
    return models.Filter(
        must=[models.FieldCondition(key="document_id", match=models.MatchValue(value=str(doc_id)))]
    )


def upsert_points(
    client: QdrantClient, collection: str, points: Sequence[models.PointStruct], batch: int = 64
) -> None:
    for start in range(0, len(points), batch):
        client.upsert(collection, points=list(points[start : start + batch]), wait=True)


def delete_document_points(client: QdrantClient, collection: str, doc_id: uuid.UUID) -> None:
    client.delete(
        collection,
        points_selector=models.FilterSelector(filter=_document_filter(doc_id)),
        wait=True,
    )


def update_document_payload(
    client: QdrantClient, collection: str, doc_id: uuid.UUID, payload: dict[str, Any]
) -> None:
    client.set_payload(collection, payload=payload, points=_document_filter(doc_id), wait=True)


def count_document_points(client: QdrantClient, collection: str, doc_id: uuid.UUID) -> int:
    return client.count(collection, count_filter=_document_filter(doc_id), exact=True).count


class Embedder:
    """FastEmbed dense embeddings; the ONNX model loads on first use."""

    def __init__(self, model_name: str, batch_size: int) -> None:
        self.model_name = model_name
        self.batch_size = batch_size
        self._model: Any = None

    def embed(self, texts: Iterable[str]) -> list[list[float]]:
        if self._model is None:
            from fastembed import TextEmbedding  # imported lazily: loading it is slow

            self._model = TextEmbedding(model_name=self.model_name)
        vectors = self._model.passage_embed(list(texts), batch_size=self.batch_size)
        return [vector.tolist() for vector in vectors]
