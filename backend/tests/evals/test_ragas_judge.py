"""The RAGAS judge's wiring, without calling Gemini or loading an embedding model."""

import time

import numpy as np
import pytest
from ragas.metrics.result import MetricResult

from app.evals import ragas_judge
from app.evals.answers import AnswerRecord
from app.evals.ragas_judge import FastEmbedEmbeddings, RagasJudge, Throttle, judge_completion


async def test_throttle_spaces_calls() -> None:
    throttle = Throttle(per_minute=600)  # one call every 0.1 s
    started = time.monotonic()
    for _ in range(3):
        await throttle.wait()
    assert time.monotonic() - started >= 0.19


async def test_unlimited_throttle_does_not_wait() -> None:
    throttle = Throttle(per_minute=0)
    started = time.monotonic()
    for _ in range(5):
        await throttle.wait()
    assert time.monotonic() - started < 0.1


async def test_judge_completion_adds_key_and_retries() -> None:
    calls = []

    async def fake_completion(**kwargs):
        calls.append(kwargs)
        return "response"

    complete = judge_completion("secret", per_minute=0, completion=fake_completion)
    assert await complete(model="gemini/x", messages=[], mode="json") == "response"
    assert calls == [{"model": "gemini/x", "messages": [], "api_key": "secret", "num_retries": 3}]


class FakeTextEmbedding:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name

    def embed(self, texts):
        for text in texts:
            yield np.array([float(len(text)), 1.0])


async def test_fastembed_embeddings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ragas_judge, "TextEmbedding", FakeTextEmbedding)
    embeddings = FastEmbedEmbeddings("BAAI/bge-small-en-v1.5")
    assert embeddings.embed_text("abc") == [3.0, 1.0]
    assert await embeddings.aembed_text("ab") == [2.0, 1.0]
    assert await embeddings.aembed_texts(["a", "abcd"]) == [[1.0, 1.0], [4.0, 1.0]]


class FakeMetric:
    def __init__(self, value: float) -> None:
        self.value = value
        self.kwargs: dict = {}

    async def ascore(self, **kwargs) -> MetricResult:
        self.kwargs = kwargs
        return MetricResult(value=self.value)


async def test_judge_scores_all_four_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ragas_judge, "TextEmbedding", FakeTextEmbedding)

    async def never_called(**kwargs):
        raise AssertionError("no LLM call expected")

    judge = RagasJudge("gemini/gemini-test", never_called, FastEmbedEmbeddings("fake"))
    metrics = {
        "_faithfulness": FakeMetric(0.9),
        "_relevancy": FakeMetric(0.8),
        "_precision": FakeMetric(0.7),
        "_recall": FakeMetric(0.6),
    }
    for attribute, metric in metrics.items():
        setattr(judge, attribute, metric)
    record = AnswerRecord(
        case_id="q1",
        answerable=True,
        question="Can I bring a phone?",
        answer="No [1].",
        abstained=False,
        markers=[1],
        context_blocks=1,
        contexts=["Mobile phones are prohibited."],
        best_score=4.0,
        model="groq/x",
        tokens_out=5,
        seconds=1.0,
    )
    scores = await judge.score(record, reference="No, phones are prohibited.")
    assert scores == {
        "faithfulness": 0.9,
        "response_relevancy": 0.8,
        "context_precision": 0.7,
        "context_recall": 0.6,
    }
    assert metrics["_recall"].kwargs == {
        "user_input": "Can I bring a phone?",
        "retrieved_contexts": ["Mobile phones are prohibited."],
        "reference": "No, phones are prohibited.",
    }
    assert metrics["_relevancy"].kwargs == {
        "user_input": "Can I bring a phone?",
        "response": "No [1].",
    }
