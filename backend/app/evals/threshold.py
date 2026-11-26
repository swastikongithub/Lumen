"""Tune the abstention threshold τ (SPEC §9 step 6, §11.4) without calling an LLM.

Lumen abstains before generation when the best re-rank score is below τ. For each
candidate τ, the sweep reports:
- the share of unanswerable questions that would abstain (higher is better);
- the share of answerable questions that would abstain by mistake (lower is better).

`choose` picks the τ that catches the most unanswerable questions while keeping false
abstains within the target (≤ 5%, SPEC §11.4). Unanswerable questions that get past τ
still reach the LLM, whose prompt tells it to answer "not found", so a cautious τ costs
some LLM calls but no wrong answers by itself.

The scores are the cross-encoder's raw logits, so τ is on that scale (0 is the
model's own relevant/not-relevant boundary).
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from app.evals.golden import GoldenCase

DEFAULT_GRID = tuple(x / 2 for x in range(-16, 17))  # -8.0 .. 8.0 in steps of 0.5


@dataclass(frozen=True)
class ThresholdRow:
    threshold: float
    unanswerable_abstained: float  # share of unanswerable questions abstained
    false_abstains: float  # share of answerable questions abstained


def abstains(best_score: float | None, threshold: float) -> bool:
    return best_score is None or best_score < threshold


def _share(flags: Sequence[bool]) -> float:
    return sum(flags) / len(flags) if flags else 0.0


def sweep(
    cases: Sequence[GoldenCase],
    best_scores: Mapping[str, float | None],
    thresholds: Iterable[float] = DEFAULT_GRID,
) -> list[ThresholdRow]:
    scored = [case for case in cases if case.id in best_scores]
    unanswerable = [best_scores[c.id] for c in scored if not c.answerable]
    answerable = [best_scores[c.id] for c in scored if c.answerable]
    return [
        ThresholdRow(
            threshold=t,
            unanswerable_abstained=_share([abstains(s, t) for s in unanswerable]),
            false_abstains=_share([abstains(s, t) for s in answerable]),
        )
        for t in sorted(set(thresholds))
    ]


def choose(rows: Sequence[ThresholdRow], max_false_abstains: float = 0.05) -> ThresholdRow | None:
    """Most unanswerable questions caught within the false-abstain budget; on a tie,
    fewer false abstains, then the lower threshold."""
    allowed = [row for row in rows if row.false_abstains <= max_false_abstains]
    if not allowed:
        return None
    return min(allowed, key=lambda r: (-r.unanswerable_abstained, r.false_abstains, r.threshold))
