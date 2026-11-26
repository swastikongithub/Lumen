from app.rag.reranker import rerank
from tests.rag.fakes import FakeScorer, make_chunk


def test_rerank_orders_by_cross_encoder_score_and_keeps_top_n() -> None:
    chunks = [make_chunk(1, "weak"), make_chunk(2, "strong"), make_chunk(3, "middle")]
    scorer = FakeScorer({"weak": -2.0, "strong": 6.5, "middle": 1.0})

    ranked = rerank(scorer, "question", chunks, top_n=2)

    assert [(chunk.text, chunk.score) for chunk in ranked] == [("strong", 6.5), ("middle", 1.0)]


def test_scorer_reads_headings_with_the_text() -> None:
    seen: list[str] = []

    class RecordingScorer:
        def score(self, query: str, texts: list[str]) -> list[float]:
            seen.extend(texts)
            return [0.0] * len(texts)

    rerank(RecordingScorer(), "q", [make_chunk(1, "Body.", headings=("Fees", "Refunds"))], 5)

    assert seen == ["Fees\nRefunds\nBody."]


def test_equal_scores_keep_retrieval_order() -> None:
    chunks = [make_chunk(1, "a"), make_chunk(2, "b")]

    ranked = rerank(FakeScorer({"a": 1.0, "b": 1.0}), "q", chunks, top_n=5)

    assert [chunk.chunk_id for chunk in ranked] == ["chunk-1", "chunk-2"]


def test_no_candidates_means_no_scoring() -> None:
    class FailingScorer:
        def score(self, query: str, texts: list[str]) -> list[float]:
            raise AssertionError("should not be called")

    assert rerank(FailingScorer(), "q", [], top_n=5) == []
