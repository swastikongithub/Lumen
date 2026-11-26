"""The query pipeline (SPEC §9 steps 4-8) for one standalone question.

    retrieve (hybrid, RRF) -> re-rank -> abstain? -> prompt -> stream -> check citations

`RagPipeline.run` yields the answer text piece by piece (`str`) and finishes with one
`Answer` holding everything the API stores. Abstaining happens before the LLM is
called: if even the best re-ranked chunk scores below τ, the student gets the
"not found" message and the closest sources, and no LLM quota is spent.

Validation and persistence are the API's job (app/api/chat.py). Query rewriting and
the answer cache (steps 2-3) arrive in Phase 5.
"""

import asyncio
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.rag.citations import (
    UNVERIFIED_NOTICE,
    citations_for,
    cited_numbers,
    closest_sources,
    is_not_found,
)
from app.rag.generator import GenerationInfo, Generator, LlmUnavailableError
from app.rag.prompts import NOT_FOUND_ANSWER, build_messages, select_context
from app.rag.reranker import Scorer, rerank
from app.rag.retriever import RetrievedChunk


class Retriever(Protocol):
    async def search(self, question: str, category: str | None = None) -> list[RetrievedChunk]: ...


@dataclass(frozen=True)
class PipelineConfig:
    rerank_top_n: int = 5
    abstain_threshold: float = 0.0
    abstain_sources: int = 3
    context_max_tokens: int = 2000


@dataclass(frozen=True)
class Answer:
    content: str  # exactly the text that was streamed
    citations: list[dict[str, Any]]
    abstained: bool
    model: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    best_score: float | None = None  # top re-rank score, for tuning τ (Phase 3)
    context: list[RetrievedChunk] = field(default_factory=list)


class RagPipeline:
    def __init__(
        self,
        retriever: Retriever,
        scorer: Scorer,
        generator: Generator,
        config: PipelineConfig,
    ) -> None:
        self.retriever = retriever
        self.scorer = scorer
        self.generator = generator
        self.config = config

    async def run(self, question: str, category: str | None = None) -> AsyncIterator[str | Answer]:
        candidates = await self.retriever.search(question, category)
        # Cross-encoder scoring is CPU work (about a second for 20 chunks on one core).
        ranked = await asyncio.to_thread(
            rerank, self.scorer, question, candidates, self.config.rerank_top_n
        )
        best_score = ranked[0].score if ranked else None

        if best_score is None or best_score < self.config.abstain_threshold:
            yield NOT_FOUND_ANSWER
            yield self._abstain(NOT_FOUND_ANSWER, ranked, best_score)
            return

        blocks = select_context(ranked, self.config.context_max_tokens)
        info = GenerationInfo()
        parts: list[str] = []
        async for text in self.generator.stream(build_messages(question, blocks), info):
            parts.append(text)
            yield text
        content = "".join(parts)
        if not content.strip():
            raise LlmUnavailableError("the model returned an empty answer")

        numbers = cited_numbers(content, len(blocks))
        if not numbers and is_not_found(content):
            yield self._abstain(content, ranked, best_score, info)
            return
        if not numbers:
            yield UNVERIFIED_NOTICE
            content += UNVERIFIED_NOTICE
        yield Answer(
            content=content,
            citations=citations_for(numbers, blocks),
            abstained=False,
            model=info.model,
            tokens_in=info.tokens_in,
            tokens_out=info.tokens_out,
            best_score=best_score,
            context=blocks,
        )

    def _abstain(
        self,
        content: str,
        ranked: Sequence[RetrievedChunk],
        best_score: float | None,
        info: GenerationInfo | None = None,
    ) -> Answer:
        info = info or GenerationInfo()
        return Answer(
            content=content,
            citations=closest_sources(ranked, self.config.abstain_sources),
            abstained=True,
            model=info.model,
            tokens_in=info.tokens_in,
            tokens_out=info.tokens_out,
            best_score=best_score,
        )
