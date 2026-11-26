"""Run retrieval configurations over the golden set (SPEC §11.2-11.3).

A configuration is a search mode (dense only, BM25 only, or hybrid RRF) plus an optional
cross-encoder re-ranker over the hybrid candidates. Hybrid search goes through the same
`HybridRetriever` the API uses, and re-ranking through the same `rerank`, so the numbers
describe what production serves.

Each question's ranked top 10 is scored with Hit@5, Recall@5 and MRR@10. Re-ranked runs
also record each question's best re-rank score (unanswerable questions included), which
is what the abstention threshold τ is tuned on (app/evals/threshold.py), and how long
retrieval and re-ranking took.
"""

import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from qdrant_client import AsyncQdrantClient

from app.collection import DENSE_VECTOR, SPARSE_VECTOR, bm25_document
from app.evals.golden import GoldenCase
from app.evals.metrics import CaseScore, Summary, score_case, summarize
from app.rag.reranker import Scorer, rerank
from app.rag.retriever import (
    DenseEncoder,
    HybridRetriever,
    RetrievedChunk,
    SparseEncoder,
    search_filter,
)

RANKED_DEPTH = 10  # MRR@10 needs the top 10


class Mode(StrEnum):
    DENSE = "dense"
    BM25 = "bm25"
    HYBRID = "hybrid"


@dataclass(frozen=True)
class RetrievalConfig:
    name: str
    mode: Mode
    reranker: str | None = None  # FastEmbed cross-encoder model name
    candidates: int = 20  # hybrid candidates the re-ranker scores


@dataclass(frozen=True)
class RunResult:
    config: RetrievalConfig
    scores: list[CaseScore]  # answerable and multi questions only
    best_scores: dict[str, float | None] = field(default_factory=dict)  # every question
    retrieve_seconds: list[float] = field(default_factory=list)
    rerank_seconds: list[float] = field(default_factory=list)

    @property
    def summary(self) -> Summary:
        return summarize(self.scores)


class Searcher:
    """Dense, BM25 and hybrid search over one collection, without filters by category."""

    def __init__(
        self,
        client: AsyncQdrantClient,
        collection: str,
        dense: DenseEncoder,
        *,
        sparse: SparseEncoder = bm25_document,
        prefetch_limit: int = 30,
        origins: Sequence[str] = (),
    ) -> None:
        self._client = client
        self._collection = collection
        self._dense = dense
        self._sparse = sparse
        self._prefetch_limit = prefetch_limit
        self._origins = tuple(origins)

    async def search(self, mode: Mode, question: str, limit: int) -> list[RetrievedChunk]:
        if mode is Mode.HYBRID:
            retriever = HybridRetriever(
                self._client,
                self._collection,
                self._dense,
                sparse=self._sparse,
                dense_limit=self._prefetch_limit,
                sparse_limit=self._prefetch_limit,
                fused_limit=limit,
                origins=self._origins,
            )
            return await retriever.search(question)
        query = self._dense(question) if mode is Mode.DENSE else self._sparse(question)
        response = await self._client.query_points(
            collection_name=self._collection,
            query=query,
            using=DENSE_VECTOR if mode is Mode.DENSE else SPARSE_VECTOR,
            query_filter=search_filter(None, self._origins),
            limit=limit,
            with_payload=True,
        )
        return [RetrievedChunk.from_point(point) for point in response.points]


async def run_config(
    cases: Sequence[GoldenCase],
    searcher: Searcher,
    config: RetrievalConfig,
    scorer: Scorer | None = None,
) -> RunResult:
    """Score one configuration. `scorer` is required when the config re-ranks."""
    if config.reranker and scorer is None:
        raise ValueError(f"{config.name} re-ranks but no scorer was given")
    scores: list[CaseScore] = []
    best_scores: dict[str, float | None] = {}
    retrieve_seconds: list[float] = []
    rerank_seconds: list[float] = []
    for case in cases:
        started = time.perf_counter()
        if config.reranker:
            assert scorer is not None
            candidates = await searcher.search(Mode.HYBRID, case.question, config.candidates)
            retrieved = time.perf_counter()
            ranked = rerank(scorer, case.question, candidates, RANKED_DEPTH)
            rerank_seconds.append(time.perf_counter() - retrieved)
            best_scores[case.id] = ranked[0].score if ranked else None
        else:
            ranked = await searcher.search(config.mode, case.question, RANKED_DEPTH)
            retrieved = time.perf_counter()
        retrieve_seconds.append(retrieved - started)
        if case.answerable:
            scores.append(score_case(case, ranked, time.perf_counter() - started))
    return RunResult(config, scores, best_scores, retrieve_seconds, rerank_seconds)
