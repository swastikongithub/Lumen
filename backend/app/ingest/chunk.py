"""Step 3 of ingestion (SPEC §8): split a DoclingDocument into chunks.

Docling's HybridChunker cuts along the document's structure (sections, paragraphs,
tables) and then by token count, using the embedding model's own tokenizer so no
chunk is silently truncated by the embedder. Each chunk keeps:

- `text`: the raw chunk, shown to users in the sources panel;
- `embed_text`: heading path + text (`contextualize`), which is what gets embedded
  and BM25-indexed, so "Section 34.0 Unfair Means Case" is searchable by its heading;
- `headings` and the page range it came from, for citations.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from docling_core.transforms.chunker.hybrid_chunker import HybridChunker
from docling_core.transforms.chunker.tokenizer.base import BaseTokenizer
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
from docling_core.types.doc import DoclingDocument


@dataclass(frozen=True)
class Chunk:
    index: int  # position within its document, from 0
    text: str
    embed_text: str
    headings: tuple[str, ...]
    page_start: int | None  # None for formats without pages (HTML, Markdown, DOCX)
    page_end: int | None
    token_count: int  # tokens in embed_text


def page_range(doc_items: Iterable[Any]) -> tuple[int | None, int | None]:
    """First and last page of the document items a chunk was built from."""
    pages = {prov.page_no for item in doc_items for prov in getattr(item, "prov", None) or []}
    return (min(pages), max(pages)) if pages else (None, None)


def huggingface_tokenizer(model_name: str, max_tokens: int) -> BaseTokenizer:
    """The embedding model's tokenizer (downloaded from Hugging Face on first use)."""
    return HuggingFaceTokenizer.from_pretrained(model_name=model_name, max_tokens=max_tokens)


class DocumentChunker:
    def __init__(self, tokenizer: BaseTokenizer) -> None:
        self._tokenizer = tokenizer
        # merge_peers: join small neighbouring chunks under the same headings.
        self._chunker = HybridChunker(tokenizer=tokenizer, merge_peers=True)

    def chunk(self, doc: DoclingDocument) -> list[Chunk]:
        chunks: list[Chunk] = []
        for raw in self._chunker.chunk(dl_doc=doc):
            text = raw.text.strip()
            if not text:
                continue
            embed_text = self._chunker.contextualize(chunk=raw)
            page_start, page_end = page_range(raw.meta.doc_items)
            chunks.append(
                Chunk(
                    index=len(chunks),
                    text=text,
                    embed_text=embed_text,
                    headings=tuple(raw.meta.headings or ()),
                    page_start=page_start,
                    page_end=page_end,
                    token_count=self._tokenizer.count_tokens(embed_text),
                )
            )
        return chunks
