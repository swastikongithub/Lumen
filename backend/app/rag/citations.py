"""Step 8 of the query pipeline (SPEC §9): check the answer's citations.

The model cites context blocks as [n]. After generation:
- markers that point at a real block become citations, in block order;
- markers that point nowhere ([7] with 5 blocks) are dropped from the citation list.
  The streamed text keeps them; clients draw a chip only for markers with a citation;
- an answer with no valid citation gets UNVERIFIED_NOTICE appended;
- an answer that is the "not found" reply (prompt rule 2) counts as an abstention.

One citation shape is streamed in the SSE `citations` event and stored in
`messages.citations` (SPEC §7.1, §10), so a reloaded conversation shows the same cards.
"""

import re
from collections.abc import Sequence
from typing import Any

from app.rag.prompts import NOT_FOUND_ANSWER
from app.rag.retriever import RetrievedChunk

MARKER = re.compile(r"\[(\d{1,3})\]")

UNVERIFIED_NOTICE = (
    "\n\n_Lumen couldn't match this answer to the indexed documents. "
    "Check the official source before relying on it._"
)


def cited_numbers(answer: str, block_count: int) -> list[int]:
    """Valid block numbers cited in the answer, ascending, without repeats."""
    numbers = {int(match) for match in MARKER.findall(answer)}
    return sorted(n for n in numbers if 1 <= n <= block_count)


def _normalise(text: str) -> str:
    # Models sometimes wrap the reply in quotes or use a curly apostrophe (U+2019).
    text = text.strip().strip("\"'\u201c\u201d").replace("\u2019", "'").lower()
    return text.rstrip(".").strip()


def is_not_found(answer: str) -> bool:
    """True when the model gave the prompt's "not found" reply (rule 2)."""
    return _normalise(answer).startswith(_normalise(NOT_FOUND_ANSWER))


def citation(n: int, chunk: RetrievedChunk) -> dict[str, Any]:
    return {
        "n": n,
        "chunk_id": chunk.chunk_id,
        "document_id": chunk.document_id,
        "source_id": chunk.source_id,
        "title": chunk.title,
        "url": chunk.source_url,
        "category": chunk.category,
        "section": chunk.section,
        "page": chunk.page_start,
        "page_end": chunk.page_end,
        # The passage itself, for the excerpt box on the source card.
        "text": chunk.text,
    }


def citations_for(numbers: Sequence[int], blocks: Sequence[RetrievedChunk]) -> list[dict]:
    return [citation(n, blocks[n - 1]) for n in numbers]


def closest_sources(chunks: Sequence[RetrievedChunk], limit: int) -> list[dict]:
    """Shown with an abstained answer: the best matches, numbered from 1."""
    return [citation(n, chunk) for n, chunk in enumerate(chunks[:limit], start=1)]
