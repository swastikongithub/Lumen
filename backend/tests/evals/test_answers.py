"""Answer eval bookkeeping: abstention, citation validity and RAGAS plumbing, no LLM."""

from collections.abc import AsyncIterator

from app.evals.answers import (
    AnswerRecord,
    abstention_stats,
    citation_stats,
    generate_answers,
    marker_numbers,
    ragas_means,
    record_from_answer,
    score_with_ragas,
)
from app.evals.golden import CaseType, Evidence, GoldenCase
from app.rag.citations import UNVERIFIED_NOTICE
from app.rag.generator import LlmBusyError, LlmUnavailableError
from app.rag.pipeline import Answer
from tests.rag.fakes import make_chunk


def case(id: str, answerable: bool = True) -> GoldenCase:
    return GoldenCase(
        id=id,
        type=CaseType.ANSWERABLE if answerable else CaseType.UNANSWERABLE,
        category="exams",
        question=f"question {id}?",
        reference_answer="the reference",
        relevant=(Evidence(source_id="academic-rules"),) if answerable else (),
    )


def answer(content: str, abstained: bool = False, blocks: int = 2) -> Answer:
    return Answer(
        content=content,
        citations=[],
        abstained=abstained,
        model="groq/test",
        tokens_out=12,
        best_score=3.0,
        context=[] if abstained else [make_chunk(n) for n in range(1, blocks + 1)],
    )


class ScriptedPipeline:
    """Plays back one outcome per call: an Answer, or an exception to raise."""

    def __init__(self, *outcomes) -> None:
        self.outcomes = list(outcomes)
        self.questions: list[str] = []

    async def run(self, question: str, category: str | None = None) -> AsyncIterator:
        self.questions.append(question)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        yield outcome.content
        yield outcome


def record(**overrides) -> AnswerRecord:
    fields = {
        "case_id": "q1",
        "answerable": True,
        "question": "q?",
        "answer": "See [1].",
        "abstained": False,
        "markers": [1],
        "context_blocks": 2,
        "contexts": ["9.0 Attendance\nStudents need 75%."],
        "best_score": 3.0,
        "model": "groq/test",
        "tokens_out": 12,
        "seconds": 1.0,
    }
    fields.update(overrides)
    return AnswerRecord(**fields)


def test_markers_and_record() -> None:
    assert marker_numbers("A [1] and [3], not [x] or [1234].") == [1, 3]
    rec = record_from_answer(case("q1"), answer("Yes [1]." + UNVERIFIED_NOTICE), 0.5)
    assert rec.answer == "Yes [1]."  # the notice is Lumen's, not the model's
    assert rec.markers == [1]
    assert rec.context_blocks == 2
    assert rec.contexts[0].startswith("9.0 Attendance\n")
    abstained = record_from_answer(case("q2"), answer("not found", abstained=True), 0.1)
    assert abstained.markers == [] and abstained.contexts == []


async def test_generate_answers_retries_when_busy() -> None:
    waits: list[float] = []

    async def sleep(seconds: float) -> None:
        waits.append(seconds)

    pipeline = ScriptedPipeline(
        answer("A [1]."),
        LlmBusyError(retry_after=7),
        answer("B [2]."),
        LlmUnavailableError("down"),
    )
    records = await generate_answers(
        pipeline, [case("q1"), case("q2"), case("q3")], pause_seconds=1.0, sleep=sleep
    )
    assert [r.answer for r in records] == ["A [1].", "B [2].", ""]
    assert records[2].error == "unavailable: down"
    assert waits == [1.0, 7, 1.0]  # pause, retry_after, pause
    assert pipeline.questions == ["question q1?", "question q2?", "question q2?", "question q3?"]


async def test_generate_answers_gives_up_after_retries() -> None:
    pipeline = ScriptedPipeline(*[LlmBusyError(retry_after=1)] * 3)

    async def sleep(seconds: float) -> None:
        return None

    [rec] = await generate_answers(pipeline, [case("q1")], max_busy_retries=2, sleep=sleep)
    assert rec.error == "rate_limited"


def test_abstention_stats() -> None:
    records = [
        record(case_id="a1", abstained=False),
        record(case_id="a2", abstained=True),  # false abstain
        record(case_id="u1", answerable=False, abstained=True),
        record(case_id="u2", answerable=False, abstained=False),
        record(case_id="e1", error="rate_limited"),  # not counted
    ]
    stats = abstention_stats(records)
    assert (stats.answerable, stats.unanswerable) == (2, 2)
    assert stats.abstain_rate_unanswerable == 0.5
    assert stats.false_abstain_rate == 0.5
    assert stats.precision == 0.5


def test_citation_stats() -> None:
    records = [
        record(markers=[1, 2]),
        record(markers=[3], context_blocks=2),  # [3] points past the last block
        record(markers=[]),
        record(abstained=True, markers=[]),  # abstentions are not answers
    ]
    stats = citation_stats(records)
    assert stats.answers == 3
    assert (stats.markers, stats.valid_markers) == (3, 2)
    assert stats.validity == 2 / 3
    assert stats.cited_share == 1 / 3


class FakeJudge:
    def __init__(self) -> None:
        self.seen: list[tuple[str, str]] = []

    async def score(self, rec: AnswerRecord, reference: str) -> dict[str, float]:
        self.seen.append((rec.case_id, reference))
        if rec.case_id == "boom":
            raise RuntimeError("judge failed")
        return {"faithfulness": 1.0, "context_recall": 0.5}


async def test_ragas_scores_only_answered_answerable_records() -> None:
    cases = {c.id: c for c in [case("q1"), case("boom"), case("u1", answerable=False)]}
    records = [
        record(case_id="q1"),
        record(case_id="boom"),
        record(case_id="u1", answerable=False),
        record(case_id="q1", abstained=True),
    ]
    judge = FakeJudge()
    scored = await score_with_ragas(records, cases, judge)
    assert judge.seen == [("q1", "the reference"), ("boom", "the reference")]
    assert scored[0].ragas == {"faithfulness": 1.0, "context_recall": 0.5}
    assert scored[1].ragas == {}  # the failure is logged, the run goes on
    assert ragas_means(scored) == {"faithfulness": 1.0, "context_recall": 0.5}
