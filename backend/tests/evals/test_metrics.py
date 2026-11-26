"""Page-overlap relevance and Hit@5 / Recall@5 / MRR@10 (SPEC §11.1-11.2)."""

from dataclasses import dataclass

import pytest

from app.evals.golden import CaseType, Evidence, GoldenCase, Location
from app.evals.metrics import (
    hit_at_k,
    matches,
    percentile,
    recall_at_k,
    reciprocal_rank,
    score_case,
    summarize,
)


@dataclass(frozen=True)
class Chunk:
    source_id: str
    page_start: int | None = None
    page_end: int | None = None
    headings: tuple[str, ...] = ()


def case(*evidence: Evidence, type: CaseType = CaseType.ANSWERABLE, id: str = "q1") -> GoldenCase:
    return GoldenCase(
        id=id,
        type=type,
        category="exams",
        question="q?",
        reference_answer="a",
        relevant=evidence,
    )


OTHER = Chunk("other-doc", 1, 1)


@pytest.mark.parametrize(
    ("location", "chunk", "expected"),
    [
        (Location(source_id="a"), Chunk("a"), True),
        (Location(source_id="a"), Chunk("b"), False),
        (Location(source_id="a", pages=(12,)), Chunk("a", 12, 12), True),
        (Location(source_id="a", pages=(12,)), Chunk("a", 11, 13), True),  # range overlaps
        (Location(source_id="a", pages=(12,)), Chunk("a", 13, 14), False),
        (Location(source_id="a", pages=(3, 12)), Chunk("a", 3, None), True),
        (Location(source_id="a", pages=(12,)), Chunk("a"), False),  # chunk has no pages
        (Location(source_id="a", section="refund"), Chunk("a", headings=("Fees", "Refunds")), True),
        (
            Location(source_id="a", section="Assessment and Evaluation"),
            Chunk("a", headings=("Assessment and\nEvaluation",)),  # Docling keeps line breaks
            True,
        ),
        (Location(source_id="a", section="Refund"), Chunk("a", headings=("Fees",)), False),
        (
            Location(source_id="a", pages=(2,), section="Mess"),
            Chunk("a", 2, 2, ("Attendance",)),
            False,  # both conditions must hold
        ),
    ],
)
def test_matches(location: Location, chunk: Chunk, expected: bool) -> None:
    assert matches(location, chunk) is expected


def test_alternatives_count_as_the_same_evidence() -> None:
    evidence = Evidence(source_id="a", pages=(1,), alternatives=(Location(source_id="b"),))
    c = case(evidence)
    assert hit_at_k(c, [Chunk("b", 9, 9)], 5) == 1.0
    assert recall_at_k(c, [Chunk("b", 9, 9)], 5) == 1.0


def test_rank_metrics() -> None:
    c = case(Evidence(source_id="a", pages=(4,)))
    ranked = [OTHER, OTHER, Chunk("a", 4, 4), *[OTHER] * 7]
    assert hit_at_k(c, ranked, 5) == 1.0
    assert reciprocal_rank(c, ranked, 10) == pytest.approx(1 / 3)
    late = [*[OTHER] * 6, Chunk("a", 4, 4)]
    assert hit_at_k(c, late, 5) == 0.0
    assert reciprocal_rank(c, late, 10) == pytest.approx(1 / 7)
    assert reciprocal_rank(c, [*[OTHER] * 10, Chunk("a", 4, 4)], 10) == 0.0


def test_recall_counts_each_piece_of_evidence_once() -> None:
    c = case(
        Evidence(source_id="a", pages=(1,)),
        Evidence(source_id="b", pages=(2,)),
        type=CaseType.MULTI,
    )
    assert recall_at_k(c, [Chunk("a", 1, 1), Chunk("a", 1, 1)], 5) == 0.5
    assert recall_at_k(c, [Chunk("b", 2, 2), Chunk("a", 1, 1)], 5) == 1.0
    assert recall_at_k(c, [*[OTHER] * 5, Chunk("b", 2, 2)], 5) == 0.0


def test_summarize_by_type() -> None:
    single = case(Evidence(source_id="a"), id="q1")
    multi = case(Evidence(source_id="a"), Evidence(source_id="b"), type=CaseType.MULTI, id="q2")
    scores = [
        score_case(single, [Chunk("a")]),  # hit, recall 1, rr 1
        score_case(multi, [OTHER, Chunk("a")]),  # hit, recall 0.5, rr 0.5
    ]
    summary = summarize(scores)
    assert summary.questions == 2
    assert summary.hit_at_5 == 1.0
    assert summary.recall_at_5 == 0.75
    assert summary.mrr_at_10 == 0.75
    assert summary.by_type["multi"].recall_at_5 == 0.5
    assert summary.as_dict() == {
        "questions": 2,
        "hit_at_5": 1.0,
        "recall_at_5": 0.75,
        "mrr_at_10": 0.75,
    }


def test_summary_of_nothing_is_zero() -> None:
    assert summarize([]).hit_at_5 == 0.0


def test_percentile_nearest_rank() -> None:
    values = [float(v) for v in range(1, 21)]  # 1..20
    assert percentile(values, 50) == 10.0
    assert percentile(values, 95) == 19.0
    assert percentile(values, 100) == 20.0
    assert percentile([], 95) == 0.0
