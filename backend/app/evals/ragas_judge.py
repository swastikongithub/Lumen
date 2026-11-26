"""The RAGAS judge for app/evals/answers.py: four metrics scored by Gemini Flash.

- faithfulness: are the answer's claims supported by the context the LLM saw?
- response relevancy: does the answer address the question? (needs embeddings)
- context precision: are the relevant context blocks ranked first? (uses the reference)
- context recall: does the context cover the reference answer?

The judge is called through LiteLLM (the app's provider layer) wrapped by `instructor`
for structured output, throttled for the free tier. Response relevancy embeds with the
app's own FastEmbed model, so it uses no embedding quota.

Needs the `eval` dependency group (RAGAS, instructor).
"""

import asyncio
import os
import time
from collections.abc import Awaitable, Callable
from typing import Any

# As in app/rag/generator.py: use LiteLLM's bundled model cost map, no download.
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

import instructor
import litellm
from fastembed import TextEmbedding
from ragas.embeddings.base import BaseRagasEmbedding
from ragas.llms import llm_factory
from ragas.metrics.collections import (
    AnswerRelevancy,
    ContextPrecisionWithReference,
    ContextRecall,
    Faithfulness,
)

from app.evals.answers import AnswerRecord

Completion = Callable[..., Awaitable[Any]]


class Throttle:
    """At most `per_minute` calls a minute, spaced evenly."""

    def __init__(self, per_minute: float) -> None:
        self._interval = 60.0 / per_minute if per_minute > 0 else 0.0
        self._next = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            now = time.monotonic()
            if now < self._next:
                await asyncio.sleep(self._next - now)
            self._next = max(now, self._next) + self._interval


def judge_completion(
    api_key: str | None,
    per_minute: float,
    *,
    num_retries: int = 3,
    completion: Completion = litellm.acompletion,
) -> Completion:
    """`litellm.acompletion` with the judge's key, a rate limit and retries on 429."""
    throttle = Throttle(per_minute)

    async def complete(**kwargs: Any) -> Any:
        kwargs.pop("mode", None)  # instructor's own setting, not a provider parameter
        await throttle.wait()
        return await completion(**kwargs, api_key=api_key, num_retries=num_retries)

    return complete


class FastEmbedEmbeddings(BaseRagasEmbedding):
    def __init__(self, model_name: str) -> None:
        super().__init__()
        self._model = TextEmbedding(model_name=model_name)

    def embed_text(self, text: str, **kwargs: Any) -> list[float]:
        return next(iter(self._model.embed([text]))).tolist()

    async def aembed_text(self, text: str, **kwargs: Any) -> list[float]:
        return await asyncio.to_thread(self.embed_text, text)


class RagasJudge:
    """Implements app.evals.answers.RagasScorer."""

    def __init__(
        self, judge_model: str, completion: Completion, embeddings: BaseRagasEmbedding
    ) -> None:
        client = instructor.from_litellm(completion, mode=instructor.Mode.JSON)
        llm = llm_factory(
            judge_model, provider="google", client=client, adapter="litellm", temperature=0
        )
        self._faithfulness = Faithfulness(llm=llm)
        self._relevancy = AnswerRelevancy(llm=llm, embeddings=embeddings, strictness=3)
        self._precision = ContextPrecisionWithReference(llm=llm)
        self._recall = ContextRecall(llm=llm)

    async def score(self, record: AnswerRecord, reference: str) -> dict[str, float]:
        question, answer, contexts = record.question, record.answer, record.contexts
        results = {
            "faithfulness": await self._faithfulness.ascore(
                user_input=question, response=answer, retrieved_contexts=contexts
            ),
            "response_relevancy": await self._relevancy.ascore(
                user_input=question, response=answer
            ),
            "context_precision": await self._precision.ascore(
                user_input=question, reference=reference, retrieved_contexts=contexts
            ),
            "context_recall": await self._recall.ascore(
                user_input=question, retrieved_contexts=contexts, reference=reference
            ),
        }
        return {name: float(result.value) for name, result in results.items()}
