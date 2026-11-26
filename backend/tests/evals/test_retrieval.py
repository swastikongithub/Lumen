"""Retrieval configurations scored against Qdrant's in-memory mode with fake vectors."""

import pytest
from qdrant_client import AsyncQdrantClient, models

from app.collection import DENSE_VECTOR, SPARSE_VECTOR
from app.evals.golden import CaseType, Evidence, GoldenCase
from app.evals.retrieval import Mode, RetrievalConfig, Searcher, run_config
from tests.rag.fakes import FakeScorer
from tests.rag.test_retriever import CHUNKS, fake_dense, fake_sparse, payload

COLLECTION = "kb_chunks"


@pytest.fixture
async def searcher() -> Searcher:
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
    return Searcher(client, COLLECTION, fake_dense, sparse=fake_sparse)


def case(id: str, question: str, source: str | None) -> GoldenCase:
    answerable = source is not None
    return GoldenCase(
        id=id,
        type=CaseType.ANSWERABLE if answerable else CaseType.UNANSWERABLE,
        category="other",
        question=question,
        reference_answer="a",
        relevant=(Evidence(source_id=source),) if source else (),
    )


CASES = [
    case("q1", "hostel gates", "source-2"),  # dense and BM25 both find chunk 2
    case("q2", "form er-5", "source-4"),  # only BM25 knows "er-5"
    case("q3", "wifi password", None),
]


async def test_each_mode_searches(searcher: Searcher) -> None:
    dense = await searcher.search(Mode.DENSE, "hostel", 10)
    bm25 = await searcher.search(Mode.BM25, "form er-5", 10)
    hybrid = await searcher.search(Mode.HYBRID, "form er-5", 10)
    assert dense[0].source_id == "source-2"
    assert [c.source_id for c in bm25] == ["source-4"]  # the only chunk with those words
    assert "source-4" in [c.source_id for c in hybrid[:2]]


async def test_run_config_scores_answerable_questions_only(searcher: Searcher) -> None:
    result = await run_config(CASES, searcher, RetrievalConfig("BM25 only", Mode.BM25))
    assert [s.case_id for s in result.scores] == ["q1", "q2"]
    assert result.summary.hit_at_5 == 1.0
    assert result.summary.mrr_at_10 == 1.0
    assert result.best_scores == {}  # no re-ranker
    assert len(result.retrieve_seconds) == 3
    assert result.rerank_seconds == []


async def test_rerank_records_best_scores_for_every_question(searcher: Searcher) -> None:
    scorer = FakeScorer({"hostel": 5.0, "er-5": 3.0})
    config = RetrievalConfig("Hybrid + fake", Mode.HYBRID, reranker="fake", candidates=4)
    result = await run_config(CASES, searcher, config, scorer)
    assert result.best_scores["q1"] == 5.0
    assert result.best_scores["q3"] == 5.0  # the best candidate, even when irrelevant
    assert len(result.rerank_seconds) == 3
    assert result.summary.hit_at_5 == 1.0
    assert result.scores[0].first_rank == 1  # "hostel" scored highest


async def test_rerank_needs_a_scorer(searcher: Searcher) -> None:
    with pytest.raises(ValueError, match="no scorer"):
        await run_config(CASES, searcher, RetrievalConfig("x", Mode.HYBRID, reranker="m"))
