"""Retrieval metrics (SPEC §11.2), deterministic and LLM-free.

A retrieved chunk is relevant to a piece of evidence when it comes from the same
document and (if the label gives them) its page range overlaps one of the labelled
pages and one of its headings contains the labelled section. For a ranked list:

- Hit@k: 1 if any of the top k chunks is relevant to any evidence, else 0;
- Recall@k: the share of the question's evidence found in the top k (a multi-part
  question with two pieces of evidence and one found scores 0.5);
- MRR@k: 1 / rank of the first relevant chunk in the top k, 0 if there is none.

Only answerable and multi questions are scored; unanswerable ones have no evidence.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from statistics import fmean
from typing import Protocol

from app.evals.golden import CaseType, Evidence, GoldenCase, Location


class ChunkLike(Protocol):
    """What relevance needs from a retrieved chunk (RetrievedChunk has all of it)."""

    @property
    def source_id(self) -> str: ...
    @property
    def page_start(self) -> int | None: ...
    @property
    def page_end(self) -> int | None: ...
    @property
    def headings(self) -> Sequence[str]: ...


def _normalise(text: str) -> str:
    return " ".join(text.split()).casefold()


def matches(location: Location, chunk: ChunkLike) -> bool:
    if chunk.source_id != location.source_id:
        return False
    if location.pages:
        if chunk.page_start is None:
            return False
        last = chunk.page_end if chunk.page_end is not None else chunk.page_start
        if not any(chunk.page_start <= page <= last for page in location.pages):
            return False
    if location.section:
        wanted = _normalise(location.section)
        if not any(wanted in _normalise(heading) for heading in chunk.headings):
            return False
    return True


def supports(evidence: Evidence, chunk: ChunkLike) -> bool:
    return any(matches(location, chunk) for location in evidence.locations)


def is_relevant(case: GoldenCase, chunk: ChunkLike) -> bool:
    return any(supports(evidence, chunk) for evidence in case.relevant)


def first_relevant_rank(case: GoldenCase, ranked: Sequence[ChunkLike]) -> int | None:
    """1-based rank of the first relevant chunk, or None."""
    for rank, chunk in enumerate(ranked, start=1):
        if is_relevant(case, chunk):
            return rank
    return None


def hit_at_k(case: GoldenCase, ranked: Sequence[ChunkLike], k: int) -> float:
    return 1.0 if any(is_relevant(case, chunk) for chunk in ranked[:k]) else 0.0


def recall_at_k(case: GoldenCase, ranked: Sequence[ChunkLike], k: int) -> float:
    if not case.relevant:
        return 0.0
    top = ranked[:k]
    found = sum(any(supports(evidence, chunk) for chunk in top) for evidence in case.relevant)
    return found / len(case.relevant)


def reciprocal_rank(case: GoldenCase, ranked: Sequence[ChunkLike], k: int) -> float:
    rank = first_relevant_rank(case, ranked[:k])
    return 1.0 / rank if rank else 0.0


@dataclass(frozen=True)
class CaseScore:
    case_id: str
    type: CaseType
    category: str
    hit_at_5: float
    recall_at_5: float
    rr_at_10: float
    first_rank: int | None  # within the ranked list that was scored
    seconds: float = 0.0  # retrieval (+ re-rank) time for this question


def score_case(case: GoldenCase, ranked: Sequence[ChunkLike], seconds: float = 0.0) -> CaseScore:
    return CaseScore(
        case_id=case.id,
        type=case.type,
        category=case.category.value,
        hit_at_5=hit_at_k(case, ranked, 5),
        recall_at_5=recall_at_k(case, ranked, 5),
        rr_at_10=reciprocal_rank(case, ranked, 10),
        first_rank=first_relevant_rank(case, ranked[:10]),
        seconds=seconds,
    )


@dataclass(frozen=True)
class Summary:
    questions: int
    hit_at_5: float
    recall_at_5: float
    mrr_at_10: float
    by_type: dict[str, "Summary"] = field(default_factory=dict)

    def as_dict(self) -> dict[str, float | int]:
        return {
            "questions": self.questions,
            "hit_at_5": round(self.hit_at_5, 4),
            "recall_at_5": round(self.recall_at_5, 4),
            "mrr_at_10": round(self.mrr_at_10, 4),
        }


def _mean(values: Sequence[float]) -> float:
    return fmean(values) if values else 0.0


def summarize(scores: Sequence[CaseScore], *, split: bool = True) -> Summary:
    by_type: dict[str, Summary] = {}
    if split:
        for case_type in CaseType:
            subset = [s for s in scores if s.type is case_type]
            if subset:
                by_type[case_type.value] = summarize(subset, split=False)
    return Summary(
        questions=len(scores),
        hit_at_5=_mean([s.hit_at_5 for s in scores]),
        recall_at_5=_mean([s.recall_at_5 for s in scores]),
        mrr_at_10=_mean([s.rr_at_10 for s in scores]),
        by_type=by_type,
    )


def percentile(values: Sequence[float], q: float) -> float:
    """Nearest-rank percentile (q in 0..100); 0.0 for no values."""
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(q / 100 * len(ordered)) - 1))
    return ordered[index]
