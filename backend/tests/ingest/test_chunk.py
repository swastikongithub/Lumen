"""Chunk metadata (SPEC §8 step 3): heading paths, page ranges, contextualized text."""

from types import SimpleNamespace

from docling_core.transforms.chunker.tokenizer.base import BaseTokenizer

from app.ingest.chunk import DocumentChunker, page_range
from tests.ingest.docling_fixtures import add_heading, add_paragraph, add_table, make_document


class WordTokenizer(BaseTokenizer):
    """One token per word: no model download needed."""

    max_tokens: int = 40

    def count_tokens(self, text: str) -> int:
        return len(text.split())

    def get_max_tokens(self) -> int:
        return self.max_tokens

    def get_tokenizer(self):  # semchunk accepts a token-counting function
        return self.count_tokens


def chunker(max_tokens: int = 40) -> DocumentChunker:
    return DocumentChunker(WordTokenizer(max_tokens=max_tokens))


def exam_rules():
    doc = make_document(pages=3)
    add_heading(doc, "Examination Rules", page=1)
    add_paragraph(doc, "Candidates must carry their university ID card.", page=1)
    add_heading(doc, "34.0 Unfair Means Case", page=2)
    add_paragraph(doc, "Possession of a mobile phone, even switched off, is a UMC.", page=2)
    add_table(doc, [["Act", "Result"], ["Copying", "Answer book cancelled"]], page=3)
    return doc


def test_chunks_keep_heading_paths_and_pages() -> None:
    chunks = chunker().chunk(exam_rules())

    umc = next(c for c in chunks if "mobile phone" in c.text)
    assert umc.headings[-1] == "34.0 Unfair Means Case"
    assert umc.page_start == 2
    assert umc.page_end in (2, 3)


def test_embed_text_adds_the_heading_path_to_the_raw_text() -> None:
    chunks = chunker().chunk(exam_rules())

    umc = next(c for c in chunks if "mobile phone" in c.text)
    assert "34.0 Unfair Means Case" in umc.embed_text
    assert umc.text in umc.embed_text
    assert umc.token_count == len(umc.embed_text.split())


def test_indexes_are_consecutive_and_no_chunk_exceeds_the_limit() -> None:
    doc = make_document(pages=2)
    add_heading(doc, "Hostel Rules", page=1)
    for n in range(30):
        add_paragraph(
            doc, f"Rule {n}: residents must follow the warden's instructions.", page=1 + n // 15
        )

    chunks = chunker(max_tokens=40).chunk(doc)

    assert [c.index for c in chunks] == list(range(len(chunks)))
    assert len(chunks) > 1
    assert all(c.token_count <= 40 for c in chunks)
    assert chunks[0].page_start == 1 and chunks[-1].page_end == 2


def test_documents_without_pages_have_no_page_range() -> None:
    doc = make_document(pages=0)
    add_heading(doc, "Mentorship Guidelines")
    add_paragraph(doc, "Every student is assigned a mentor.")

    (chunk,) = chunker().chunk(doc)

    assert (chunk.page_start, chunk.page_end) == (None, None)


def test_page_range_spans_all_items() -> None:
    items = [
        SimpleNamespace(prov=[SimpleNamespace(page_no=4)]),
        SimpleNamespace(prov=[SimpleNamespace(page_no=2), SimpleNamespace(page_no=3)]),
        SimpleNamespace(prov=[]),
    ]

    assert page_range(items) == (2, 4)
    assert page_range([]) == (None, None)
