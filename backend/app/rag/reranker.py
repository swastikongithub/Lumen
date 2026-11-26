"""Step 5 of the query pipeline (SPEC §9): re-rank the fused candidates.

A cross-encoder reads the question and one chunk together and scores how well the chunk
answers it. That is far more precise than comparing two separately made vectors, but
it costs one model run per chunk, so only the ~20 retrieved candidates are scored.

FastEmbed's `TextCrossEncoder` returns raw logits: higher is better, and below 0 means
the model leans towards "not relevant". The abstention threshold τ is on that scale.
"""

from collections.abc import Sequence
from dataclasses import replace
from typing import Protocol

from app.rag.retriever import RetrievedChunk


class Scorer(Protocol):
    def score(self, query: str, texts: Sequence[str]) -> list[float]: ...


class CrossEncoderScorer:
    """FastEmbed cross-encoder. Load it once (FastAPI lifespan): it takes a few seconds."""

    def __init__(self, model_name: str) -> None:
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        self._model = TextCrossEncoder(model_name=model_name)

    def score(self, query: str, texts: Sequence[str]) -> list[float]:
        return [float(score) for score in self._model.rerank(query, list(texts))]


def rerank(
    scorer: Scorer, question: str, chunks: Sequence[RetrievedChunk], top_n: int
) -> list[RetrievedChunk]:
    """The `top_n` chunks by cross-encoder score, best first, carrying that score."""
    if not chunks:
        return []
    scores = scorer.score(question, [chunk.text_with_headings for chunk in chunks])
    rescored = [replace(chunk, score=score) for chunk, score in zip(chunks, scores, strict=True)]
    # sorted() is stable: equal scores keep their retrieval order.
    return sorted(rescored, key=lambda chunk: chunk.score, reverse=True)[:top_n]
