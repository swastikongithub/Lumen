"""Stand-ins for the pipeline's parts, so tests need no models, Qdrant or LLM."""

from collections.abc import AsyncIterator, Sequence

from app.rag.generator import GenerationInfo, LlmBusyError
from app.rag.retriever import RetrievedChunk


def make_chunk(
    n: int = 1,
    text: str = "Students need 75% attendance to sit the end-term exam.",
    *,
    title: str = "Academic Rules",
    source_id: str = "academic-rules",
    category: str = "academics",
    academic_year: str | None = "2025-26",
    page_start: int | None = 4,
    page_end: int | None = 4,
    headings: tuple[str, ...] = ("9.0 Attendance",),
    token_count: int = 50,
    score: float = 0.0,
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=f"chunk-{n}",
        document_id=f"doc-{source_id}",
        source_id=source_id,
        title=title,
        source_url=f"https://www.lpu.in/{source_id}.pdf",
        category=category,
        academic_year=academic_year,
        page_start=page_start,
        page_end=page_end,
        headings=headings,
        text=text,
        token_count=token_count,
        score=score,
    )


class FakeRetriever:
    def __init__(self, chunks: Sequence[RetrievedChunk]) -> None:
        self.chunks = list(chunks)
        self.calls: list[tuple[str, str | None]] = []

    async def search(self, question: str, category: str | None = None) -> list[RetrievedChunk]:
        self.calls.append((question, category))
        return self.chunks


class FakeScorer:
    """Scores chunks by a fixed table keyed on chunk text; unknown text scores -10."""

    def __init__(self, scores: dict[str, float]) -> None:
        self.scores = scores

    def score(self, query: str, texts: Sequence[str]) -> list[float]:
        return [
            next((s for text_part, s in self.scores.items() if text_part in text), -10.0)
            for text in texts
        ]


class FakeGenerator:
    """A mocked LLM: streams the given reply in small pieces, or raises an error."""

    def __init__(
        self,
        reply: str = "",
        *,
        model: str = "fake-model",
        error: Exception | None = None,
    ) -> None:
        self.reply = reply
        self.model = model
        self.error = error
        self.calls: list[list[dict[str, str]]] = []

    async def stream(
        self, messages: Sequence[dict[str, str]], info: GenerationInfo
    ) -> AsyncIterator[str]:
        self.calls.append(list(messages))
        if self.error:
            raise self.error
        info.model = self.model
        for start in range(0, len(self.reply), 8):
            yield self.reply[start : start + 8]
        info.tokens_in, info.tokens_out = 900, len(self.reply.split())


def busy_generator(retry_after: int = 30) -> FakeGenerator:
    return FakeGenerator(error=LlmBusyError(retry_after))
