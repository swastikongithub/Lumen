"""Step 4 of the query pipeline (SPEC §9): hybrid search in Qdrant.

One Query API call runs two searches and fuses them:
- `dense`: the question embedded with the same FastEmbed model as the chunks
  (meaning: "attendance shortage" finds "below 75% of classes");
- `bm25`: the question as a `models.Document`, which Qdrant turns into BM25 terms
  itself (exact words: "Section 34.0", "Form ER-5").
Reciprocal Rank Fusion (RRF) merges the two lists using only rank positions, so the
two score scales never have to be compared.

Only active documents are searched. Ingestion deletes a superseded version's points
(SPEC §8 step 6), so every point in `kb_chunks` already belongs to an active document
and no status filter is needed. The optional filters are the category the student
picked and the document groups this deployment serves (`origin`, SPEC §3.2).
"""

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from qdrant_client import AsyncQdrantClient, models

from app.collection import DENSE_VECTOR, SPARSE_VECTOR, bm25_document

DenseEncoder = Callable[[str], list[float]]
SparseEncoder = Callable[[str], models.Document | models.SparseVector]


@dataclass(frozen=True)
class RetrievedChunk:
    """One chunk with the payload fields answers and citations need (SPEC §7.2)."""

    chunk_id: str
    document_id: str
    source_id: str
    title: str
    source_url: str
    category: str
    academic_year: str | None
    page_start: int | None
    page_end: int | None
    headings: tuple[str, ...]
    text: str
    token_count: int
    score: float  # RRF score from retrieval; the re-ranker replaces it

    @classmethod
    def from_point(cls, point: models.ScoredPoint) -> "RetrievedChunk":
        payload: dict[str, Any] = point.payload or {}
        return cls(
            chunk_id=payload["chunk_id"],
            document_id=payload["document_id"],
            source_id=payload["source_id"],
            title=payload["title"],
            source_url=payload["source_url"],
            category=payload["category"],
            academic_year=payload.get("academic_year"),
            page_start=payload.get("page_start"),
            page_end=payload.get("page_end"),
            headings=tuple(payload.get("headings") or ()),
            text=payload["text"],
            token_count=payload.get("token_count", 0),
            score=point.score,
        )

    @property
    def section(self) -> str | None:
        """The innermost heading, shown as "Section" in citations."""
        return self.headings[-1] if self.headings else None

    @property
    def text_with_headings(self) -> str:
        """Heading path + text: what was embedded, and what the re-ranker reads."""
        return "\n".join([*self.headings, self.text])


def search_filter(category: str | None, origins: Sequence[str]) -> models.Filter | None:
    conditions: list[models.Condition] = []
    if category:
        conditions.append(
            models.FieldCondition(key="category", match=models.MatchValue(value=category))
        )
    if origins:
        conditions.append(
            models.FieldCondition(key="origin", match=models.MatchAny(any=list(origins)))
        )
    return models.Filter(must=conditions) if conditions else None


class QueryEmbedder:
    """FastEmbed dense query vectors. Loading the ONNX model takes a few seconds."""

    def __init__(self, model_name: str) -> None:
        from fastembed import TextEmbedding

        self._model = TextEmbedding(model_name=model_name)

    def embed(self, text: str) -> list[float]:
        return next(iter(self._model.query_embed(text))).tolist()


class HybridRetriever:
    def __init__(
        self,
        client: AsyncQdrantClient,
        collection: str,
        dense: DenseEncoder,
        *,
        sparse: SparseEncoder = bm25_document,
        dense_limit: int = 30,
        sparse_limit: int = 30,
        fused_limit: int = 20,
        origins: Sequence[str] = (),
    ) -> None:
        self._client = client
        self._collection = collection
        self._dense = dense
        self._sparse = sparse
        self._dense_limit = dense_limit
        self._sparse_limit = sparse_limit
        self._fused_limit = fused_limit
        self._origins = tuple(origins)

    async def search(self, question: str, category: str | None = None) -> list[RetrievedChunk]:
        """The top `fused_limit` chunks, best first."""
        # Embedding is CPU work; a thread keeps the event loop free for other requests.
        dense_vector = await asyncio.to_thread(self._dense, question)
        where = search_filter(category, self._origins)
        response = await self._client.query_points(
            collection_name=self._collection,
            prefetch=[
                models.Prefetch(
                    query=dense_vector, using=DENSE_VECTOR, limit=self._dense_limit, filter=where
                ),
                models.Prefetch(
                    query=self._sparse(question),
                    using=SPARSE_VECTOR,
                    limit=self._sparse_limit,
                    filter=where,
                ),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=self._fused_limit,
            with_payload=True,
        )
        return [RetrievedChunk.from_point(point) for point in response.points]
