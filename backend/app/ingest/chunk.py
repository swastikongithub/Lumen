"""Step 3 of ingestion (SPEC §8): split a DoclingDocument into chunks.

Docling's HybridChunker cuts along the document's structure (sections, paragraphs,
tables) and then by token count, using the embedding model's own tokenizer so no
chunk is silently truncated by the embedder. Each chunk keeps:

- `text`: the raw chunk, shown to users in the sources panel;
- `embed_text`: heading path + text (`contextualize`), which is what gets embedded
  and BM25-indexed, so "Section 34.0 Unfair Means Case" is searchable by its heading;
- `headings` and the page range it came from, for citations.

HybridChunker skips text inside pictures. When Docling reads a whole image (or an
image in a PDF, like a scanned table) as a picture, its OCR text sits inside that
picture, so pictures holding at least `MIN_PICTURE_WORDS` words of text get chunks
of their own. Logos and small labels stay out.
"""

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Any

from docling_core.transforms.chunker.hybrid_chunker import HybridChunker
from docling_core.transforms.chunker.tokenizer.base import BaseTokenizer
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
from docling_core.types.doc import DoclingDocument, PictureItem, TextItem

MIN_PICTURE_WORDS = 20


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


def picture_texts(doc: DoclingDocument) -> Iterator[tuple[PictureItem, list[str]]]:
    """Pictures with enough OCR text to index, with their text lines in reading order."""
    for picture in doc.pictures:
        lines = []
        for ref in picture.children:
            child = ref.resolve(doc)
            if isinstance(child, TextItem) and child.text.strip():
                lines.append(child.text.strip())
        if sum(len(line.split()) for line in lines) >= MIN_PICTURE_WORDS:
            yield picture, lines


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
            if text:
                embed_text = self._chunker.contextualize(chunk=raw)
                pages = page_range(raw.meta.doc_items)
                self._add(chunks, text, embed_text, raw.meta.headings or [], pages)
        for picture, lines in picture_texts(doc):
            caption = picture.caption_text(doc).strip()
            headings = [caption] if caption else []
            pages = page_range([picture])
            for text in self._pack(lines, headings):
                self._add(chunks, text, "\n".join([*headings, text]), headings, pages)
        return chunks

    def _add(
        self,
        chunks: list[Chunk],
        text: str,
        embed_text: str,
        headings: list[str],
        pages: tuple[int | None, int | None],
    ) -> None:
        chunks.append(
            Chunk(
                index=len(chunks),
                text=text,
                embed_text=embed_text,
                headings=tuple(headings),
                page_start=pages[0],
                page_end=pages[1],
                token_count=self._tokenizer.count_tokens(embed_text),
            )
        )

    def _pack(self, lines: list[str], headings: list[str]) -> Iterator[str]:
        """Join lines into texts that fit the token limit together with the headings."""
        limit = self._tokenizer.get_max_tokens()
        current: list[str] = []
        for line in lines:
            candidate = "\n".join([*headings, *current, line])
            if current and self._tokenizer.count_tokens(candidate) > limit:
                yield "\n".join(current)
                current = []
            current.append(line)
        if current:
            yield "\n".join(current)
