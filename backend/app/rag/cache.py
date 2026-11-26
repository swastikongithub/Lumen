"""Step 3 of the query pipeline (SPEC §7.2, §9): the semantic answer cache.

A question that means the same as one answered before gets the stored answer and its
citations at once: no retrieval, no re-ranking, no LLM call. "Means the same" is a cosine
similarity of at least CACHE_THRESHOLD (0.95) between the two questions' embeddings,
after normalising case, spaces and end punctuation. A hit also needs:
- the same `corpus_version`. Re-ingestion bumps it, so an answer built from older
  documents is never served again, with no clean-up job;
- the same category filter: "attendance?" under Exams is a different search from "All".

Only grounded answers are stored: no abstentions, no answers without a valid citation.
Each entry is one Qdrant point (`answer_cache`) with the question's vector and the payload
{answer, citations, corpus_version, category_filter, created_at}. The question text itself
is not stored. Entries older than RETENTION_DAYS are deleted (app/db/retention.py).

The cache must never break an answer: if Qdrant fails, a lookup is a miss and a store is
skipped, each with a warning in the log.
"""

import asyncio
import logging
import re
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from qdrant_client import AsyncQdrantClient, models

from app.collection import DENSE_VECTOR

logger = logging.getLogger(__name__)

DenseEncoder = Callable[[str], list[float]]

# category_filter for questions asked under "All".
ALL_CATEGORIES = "all"
# Fixed namespace, so the same question, filter and corpus version map to the same point.
CACHE_NAMESPACE = uuid.UUID("6f1c2a0e-5d1b-4c39-9a57-0b6f4b8e2d11")

PAYLOAD_INDEXES = {
    "corpus_version": models.PayloadSchemaType.INTEGER,
    "category_filter": models.PayloadSchemaType.KEYWORD,
    "created_at": models.PayloadSchemaType.INTEGER,
}


def normalize(question: str) -> str:
    """Lowercase, single spaces, no trailing ?, ! or full stop."""
    return re.sub(r"\s+", " ", question).strip().lower().rstrip("?!. ")


def cache_point_id(question: str, category: str | None, corpus_version: int) -> str:
    key = f"{corpus_version}|{category or ALL_CATEGORIES}|{normalize(question)}"
    return str(uuid.uuid5(CACHE_NAMESPACE, key))


@dataclass(frozen=True)
class CachedAnswer:
    content: str
    citations: list[dict[str, Any]]
    score: float  # cosine similarity to the cached question


class AnswerCache:
    def __init__(
        self,
        client: AsyncQdrantClient,
        collection: str,
        embed: DenseEncoder,
        *,
        dim: int,
        threshold: float = 0.95,
    ) -> None:
        self._client = client
        self._collection = collection
        self._embed = embed
        self._dim = dim
        self._threshold = threshold

    async def ensure_collection(self) -> None:
        """Create the collection and its payload indexes if they are missing."""
        if await self._client.collection_exists(self._collection):
            return
        await self._client.create_collection(
            collection_name=self._collection,
            vectors_config={
                DENSE_VECTOR: models.VectorParams(size=self._dim, distance=models.Distance.COSINE)
            },
        )
        for field_name, schema in PAYLOAD_INDEXES.items():
            await self._client.create_payload_index(
                self._collection, field_name=field_name, field_schema=schema
            )

    async def _vector(self, question: str) -> list[float]:
        # Embedding is CPU work; a thread keeps the event loop free.
        return await asyncio.to_thread(self._embed, normalize(question))

    async def lookup(
        self, question: str, category: str | None, corpus_version: int
    ) -> CachedAnswer | None:
        """The cached answer to an equivalent question, or None."""
        try:
            response = await self._client.query_points(
                collection_name=self._collection,
                query=await self._vector(question),
                using=DENSE_VECTOR,
                query_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="corpus_version", match=models.MatchValue(value=corpus_version)
                        ),
                        models.FieldCondition(
                            key="category_filter",
                            match=models.MatchValue(value=category or ALL_CATEGORIES),
                        ),
                    ]
                ),
                score_threshold=self._threshold,
                limit=1,
                with_payload=True,
            )
        except Exception as error:
            logger.warning("Answer cache lookup failed, treated as a miss: %s", error)
            return None
        if not response.points:
            return None
        point = response.points[0]
        payload = point.payload or {}
        return CachedAnswer(
            content=payload["answer"], citations=payload["citations"], score=point.score
        )

    async def store(
        self,
        question: str,
        category: str | None,
        corpus_version: int,
        content: str,
        citations: list[dict[str, Any]],
    ) -> None:
        """Save a grounded answer. Asking the same question again replaces the entry."""
        try:
            await self._client.upsert(
                collection_name=self._collection,
                points=[
                    models.PointStruct(
                        id=cache_point_id(question, category, corpus_version),
                        vector={DENSE_VECTOR: await self._vector(question)},
                        payload={
                            "answer": content,
                            "citations": citations,
                            "corpus_version": corpus_version,
                            "category_filter": category or ALL_CATEGORIES,
                            "created_at": int(time.time()),
                        },
                    )
                ],
            )
        except Exception as error:
            logger.warning("Answer cache store failed, answer not cached: %s", error)

    async def delete_older_than(self, cutoff: float) -> None:
        """Delete entries created before `cutoff` (Unix seconds)."""
        await self._client.delete(
            collection_name=self._collection,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[models.FieldCondition(key="created_at", range=models.Range(lt=cutoff))]
                )
            ),
        )
