"""Answer evaluation (SPEC §11.2): run the real pipeline over the golden set and score it.

Three groups of numbers:
- abstention: how many unanswerable questions abstained, and how many answerable ones
  abstained by mistake (targets in SPEC §11.4);
- citation validity: the share of `[n]` markers that point to a real context block,
  and the share of answers with at least one valid citation;
- RAGAS (faithfulness, response relevancy, context precision, context recall), judged
  by Gemini Flash, on the answerable questions Lumen did answer.

Generation uses the production LLM chain (Groq first), and the judge is a different
provider, which reduces self-grading bias (SPEC §4). If Groq has no key, Gemini both
answers and judges; the report says so. Free tiers are slow, so calls are throttled.

This module needs no RAGAS; the judge itself is in app/evals/ragas_judge.py, which needs
the `eval` dependency group.
"""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from statistics import fmean
from typing import Any, Protocol

from app.evals.golden import GoldenCase
from app.rag.citations import MARKER, UNVERIFIED_NOTICE
from app.rag.generator import LlmBusyError, LlmUnavailableError
from app.rag.pipeline import Answer

logger = logging.getLogger(__name__)

RAGAS_METRICS = ("faithfulness", "response_relevancy", "context_precision", "context_recall")


class PipelineLike(Protocol):
    def run(self, question: str, category: str | None = None) -> Any: ...


@dataclass(frozen=True)
class AnswerRecord:
    case_id: str
    answerable: bool
    question: str
    answer: str  # as streamed, without the "couldn't verify" notice
    abstained: bool
    markers: list[int]  # every [n] in the answer, valid or not
    context_blocks: int
    contexts: list[str]  # the numbered blocks the LLM saw
    best_score: float | None
    model: str | None
    tokens_out: int | None
    seconds: float
    error: str | None = None
    ragas: dict[str, float] = field(default_factory=dict)

    @property
    def answered(self) -> bool:
        return self.error is None and not self.abstained


def marker_numbers(answer: str) -> list[int]:
    return [int(n) for n in MARKER.findall(answer)]


def record_from_answer(case: GoldenCase, answer: Answer, seconds: float) -> AnswerRecord:
    text = answer.content.removesuffix(UNVERIFIED_NOTICE)
    return AnswerRecord(
        case_id=case.id,
        answerable=case.answerable,
        question=case.question,
        answer=text,
        abstained=answer.abstained,
        markers=[] if answer.abstained else marker_numbers(text),
        context_blocks=len(answer.context),
        contexts=[chunk.text_with_headings for chunk in answer.context],
        best_score=answer.best_score,
        model=answer.model,
        tokens_out=answer.tokens_out,
        seconds=seconds,
    )


async def answer_case(pipeline: PipelineLike, case: GoldenCase) -> Answer:
    final: Answer | None = None
    async for item in pipeline.run(case.question):
        if isinstance(item, Answer):
            final = item
    if final is None:
        raise LlmUnavailableError("the pipeline finished without an answer")
    return final


async def generate_answers(
    pipeline: PipelineLike,
    cases: Sequence[GoldenCase],
    *,
    pause_seconds: float = 0.0,
    max_busy_retries: int = 3,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> list[AnswerRecord]:
    """Answer every case in order. A rate-limited call waits `retry_after` and retries."""
    records = []
    for index, case in enumerate(cases):
        if index and pause_seconds:
            await sleep(pause_seconds)
        started = time.perf_counter()
        error: str | None = None
        answer: Answer | None = None
        for attempt in range(max_busy_retries + 1):
            try:
                answer = await answer_case(pipeline, case)
                break
            except LlmBusyError as busy:
                if attempt == max_busy_retries:
                    error = "rate_limited"
                else:
                    logger.info("%s: rate limited, waiting %ss", case.id, busy.retry_after)
                    await sleep(busy.retry_after)
            except LlmUnavailableError as unavailable:
                error = f"unavailable: {unavailable}"
                break
        seconds = time.perf_counter() - started
        if answer is None:
            records.append(
                AnswerRecord(
                    case_id=case.id,
                    answerable=case.answerable,
                    question=case.question,
                    answer="",
                    abstained=False,
                    markers=[],
                    context_blocks=0,
                    contexts=[],
                    best_score=None,
                    model=None,
                    tokens_out=None,
                    seconds=seconds,
                    error=error or "no answer",
                )
            )
        else:
            records.append(record_from_answer(case, answer, seconds))
        logger.info("%s: %s", case.id, "abstained" if records[-1].abstained else "answered")
    return records


@dataclass(frozen=True)
class AbstentionStats:
    unanswerable: int
    answerable: int
    correct_abstains: int  # unanswerable and abstained
    false_abstains: int  # answerable but abstained
    abstained: int

    @property
    def abstain_rate_unanswerable(self) -> float:
        return self.correct_abstains / self.unanswerable if self.unanswerable else 0.0

    @property
    def false_abstain_rate(self) -> float:
        return self.false_abstains / self.answerable if self.answerable else 0.0

    @property
    def precision(self) -> float:
        """Of all abstentions, the share that were right to abstain."""
        return self.correct_abstains / self.abstained if self.abstained else 0.0


def abstention_stats(records: Sequence[AnswerRecord]) -> AbstentionStats:
    scored = [r for r in records if r.error is None]
    return AbstentionStats(
        unanswerable=sum(not r.answerable for r in scored),
        answerable=sum(r.answerable for r in scored),
        correct_abstains=sum(r.abstained and not r.answerable for r in scored),
        false_abstains=sum(r.abstained and r.answerable for r in scored),
        abstained=sum(r.abstained for r in scored),
    )


@dataclass(frozen=True)
class CitationStats:
    answers: int  # answered (not abstained, no error)
    markers: int
    valid_markers: int
    answers_with_valid_citation: int

    @property
    def validity(self) -> float:
        return self.valid_markers / self.markers if self.markers else 0.0

    @property
    def cited_share(self) -> float:
        return self.answers_with_valid_citation / self.answers if self.answers else 0.0


def citation_stats(records: Sequence[AnswerRecord]) -> CitationStats:
    answered = [r for r in records if r.answered]
    valid = [[n for n in r.markers if 1 <= n <= r.context_blocks] for r in answered]
    return CitationStats(
        answers=len(answered),
        markers=sum(len(r.markers) for r in answered),
        valid_markers=sum(len(v) for v in valid),
        answers_with_valid_citation=sum(bool(v) for v in valid),
    )


# --- RAGAS -------------------------------------------------------------------------


class RagasScorer(Protocol):
    async def score(self, record: AnswerRecord, reference: str) -> dict[str, float]: ...


def ragas_means(records: Sequence[AnswerRecord]) -> dict[str, float]:
    means = {}
    for name in RAGAS_METRICS:
        values = [r.ragas[name] for r in records if name in r.ragas]
        if values:
            means[name] = fmean(values)
    return means


async def score_with_ragas(
    records: Sequence[AnswerRecord],
    cases: Mapping[str, GoldenCase],
    scorer: RagasScorer,
) -> list[AnswerRecord]:
    """Fill `ragas` for answered, answerable records; the rest are returned unchanged."""
    out = []
    for record in records:
        if record.answered and record.answerable and record.contexts:
            try:
                scores = await scorer.score(record, cases[record.case_id].reference_answer)
            except Exception as error:  # a judge failure must not lose the other results
                logger.warning("%s: RAGAS scoring failed: %s", record.case_id, error)
                scores = {}
            record = replace(record, ragas=scores)
        out.append(record)
    return out
