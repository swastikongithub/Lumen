"""The query pipeline (SPEC §9 steps 2-8) for one question.

    rewrite follow-up -> cache? -> retrieve (hybrid, RRF) -> re-rank -> abstain?
    -> prompt -> stream -> check citations -> cache the answer

`RagPipeline.run` yields the answer text piece by piece (`str`) and finishes with one
`Answer` holding everything the API stores. Abstaining happens before the LLM is
called: if even the best re-ranked chunk scores below τ, the student gets the
"not found" message and the closest sources, and no LLM quota is spent. A cache hit
skips everything after step 3.

The rewrite needs the conversation's earlier messages (`history`) and the cache needs the
current `corpus_version`; without them (the evals) those steps are skipped, so the evals
always measure retrieval and generation. Each step is a tracing span (app/observability.py).

Validation and persistence are the API's job (app/api/chat.py).
"""

import asyncio
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from qdrant_client import AsyncQdrantClient

from app.config import Settings
from app.observability import Tracer
from app.rag.cache import AnswerCache
from app.rag.citations import (
    UNVERIFIED_NOTICE,
    citations_for,
    cited_numbers,
    closest_sources,
    is_not_found,
)
from app.rag.generator import (
    GenerationInfo,
    Generator,
    LiteLLMGenerator,
    LlmUnavailableError,
)
from app.rag.prompts import NOT_FOUND_ANSWER, build_messages, select_context
from app.rag.reranker import CrossEncoderScorer, Scorer, rerank
from app.rag.retriever import HybridRetriever, QueryEmbedder, RetrievedChunk
from app.rag.rewrite import QueryRewriter, Turn


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
    rewritten_query: str | None = None  # the standalone question, when a follow-up was rewritten
    cache_hit: bool = False


def chunk_scores(chunks: Sequence[RetrievedChunk]) -> list[dict[str, Any]]:
    """What a tracing span records about chunks: IDs and scores, not their text."""
    return [
        {"chunk_id": c.chunk_id, "source_id": c.source_id, "score": round(c.score, 4)}
        for c in chunks
    ]


class RagPipeline:
    def __init__(
        self,
        retriever: Retriever,
        scorer: Scorer,
        generator: Generator,
        config: PipelineConfig,
        *,
        rewriter: QueryRewriter | None = None,
        cache: AnswerCache | None = None,
        tracer: Tracer | None = None,
    ) -> None:
        self.retriever = retriever
        self.scorer = scorer
        self.generator = generator
        self.config = config
        self.rewriter = rewriter
        self.cache = cache
        self.tracer = tracer or Tracer()

    async def run(
        self,
        question: str,
        category: str | None = None,
        *,
        history: Sequence[Turn] = (),
        corpus_version: int | None = None,
    ) -> AsyncIterator[str | Answer]:
        tracer = self.tracer
        rewritten = None
        if self.rewriter and history:
            with tracer.span("rewrite", input={"question": question}) as span:
                rewritten = await self.rewriter.rewrite(question, history)
                span.update(output=rewritten)
        query = rewritten or question

        use_cache = self.cache is not None and corpus_version is not None
        if use_cache:
            assert self.cache is not None and corpus_version is not None
            with tracer.span("cache-lookup", input={"query": query}) as span:
                hit = await self.cache.lookup(query, category, corpus_version)
                span.update(output={"hit": hit is not None, "score": hit.score if hit else None})
            if hit:
                yield hit.content
                yield Answer(
                    content=hit.content,
                    citations=hit.citations,
                    abstained=False,
                    rewritten_query=rewritten,
                    cache_hit=True,
                )
                return

        with tracer.span(
            "retrieve", as_type="retriever", input={"query": query, "category": category}
        ) as span:
            candidates = await self.retriever.search(query, category)
            span.update(output=chunk_scores(candidates))
        with tracer.span("rerank", input={"candidates": len(candidates)}) as span:
            # Cross-encoder scoring is CPU work (about a second for 20 chunks on one core).
            ranked = await asyncio.to_thread(
                rerank, self.scorer, query, candidates, self.config.rerank_top_n
            )
            best_score = ranked[0].score if ranked else None
            span.update(
                output=chunk_scores(ranked),
                metadata={"best_score": best_score, "threshold": self.config.abstain_threshold},
            )

        if best_score is None or best_score < self.config.abstain_threshold:
            yield NOT_FOUND_ANSWER
            yield self._abstain(NOT_FOUND_ANSWER, ranked, best_score, rewritten=rewritten)
            return

        blocks = select_context(ranked, self.config.context_max_tokens)
        info = GenerationInfo()
        parts: list[str] = []
        with tracer.span(
            "generate", input={"query": query, "blocks": [b.chunk_id for b in blocks]}
        ) as span:
            async for text in self.generator.stream(build_messages(query, blocks), info):
                parts.append(text)
                yield text
            content = "".join(parts)
            span.update(output=content, metadata={"model": info.model})
        if not content.strip():
            raise LlmUnavailableError("the model returned an empty answer")

        numbers = cited_numbers(content, len(blocks))
        if not numbers and is_not_found(content):
            yield self._abstain(content, ranked, best_score, info, rewritten=rewritten)
            return
        if not numbers:
            yield UNVERIFIED_NOTICE
            content += UNVERIFIED_NOTICE
        citations = citations_for(numbers, blocks)
        if use_cache and citations:
            assert self.cache is not None and corpus_version is not None
            with tracer.span("cache-store"):
                await self.cache.store(query, category, corpus_version, content, citations)
        yield Answer(
            content=content,
            citations=citations,
            abstained=False,
            model=info.model,
            tokens_in=info.tokens_in,
            tokens_out=info.tokens_out,
            best_score=best_score,
            context=blocks,
            rewritten_query=rewritten,
        )

    def _abstain(
        self,
        content: str,
        ranked: Sequence[RetrievedChunk],
        best_score: float | None,
        info: GenerationInfo | None = None,
        *,
        rewritten: str | None = None,
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
            rewritten_query=rewritten,
        )


def build_pipeline(
    settings: Settings, qdrant: AsyncQdrantClient, tracer: Tracer | None = None
) -> RagPipeline:
    """The production pipeline. Loads the embedding and re-ranking ONNX models, which
    takes a few seconds (and downloads them on first run), so call it once at startup."""
    embedder = QueryEmbedder(settings.embed_model)
    retriever = HybridRetriever(
        qdrant,
        settings.qdrant_collection,
        embedder.embed,
        dense_limit=settings.retrieve_dense_limit,
        sparse_limit=settings.retrieve_sparse_limit,
        fused_limit=settings.retrieve_fused_limit,
        origins=settings.retrieval_origins,
    )
    config = PipelineConfig(
        rerank_top_n=settings.rerank_top_n,
        abstain_threshold=settings.abstain_threshold,
        abstain_sources=settings.abstain_sources,
        context_max_tokens=settings.context_max_tokens,
    )
    generator = LiteLLMGenerator.from_settings(settings)
    cache = (
        AnswerCache(
            qdrant,
            settings.cache_collection,
            embedder.embed,
            dim=settings.embed_dim,
            threshold=settings.cache_threshold,
        )
        if settings.cache_enabled
        else None
    )
    return RagPipeline(
        retriever,
        CrossEncoderScorer(settings.rerank_model),
        generator,
        config,
        rewriter=QueryRewriter(
            generator,
            max_tokens=settings.rewrite_max_tokens,
            history_turns=settings.rewrite_history_turns,
        ),
        cache=cache,
        tracer=tracer,
    )
