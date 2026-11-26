from app.rag.citations import (
    citation,
    citations_for,
    cited_numbers,
    closest_sources,
    is_not_found,
)
from tests.rag.fakes import make_chunk


def test_cited_numbers_are_unique_sorted_and_within_the_context() -> None:
    answer = "Attendance must be 75% [2]. Medical leave counts [1][2]. Fines apply [7]."

    assert cited_numbers(answer, block_count=3) == [1, 2]


def test_zero_and_non_numeric_markers_are_ignored() -> None:
    assert cited_numbers("See [0] and [a] and [1a].", block_count=5) == []


def test_not_found_reply_is_recognised_with_small_variations() -> None:
    assert is_not_found("I couldn't find this in the indexed documents.")
    assert is_not_found('  "I couldn\u2019t find this in the indexed documents"  ')
    assert is_not_found("I COULDN'T FIND THIS IN THE INDEXED DOCUMENTS. Sorry!")
    assert not is_not_found("The minimum attendance is 75% [1].")


def test_citation_carries_what_source_cards_show() -> None:
    chunk = make_chunk(3, "Passage.", headings=("Fees", "Late fee"), page_start=2, page_end=3)

    assert citation(1, chunk) == {
        "n": 1,
        "chunk_id": "chunk-3",
        "document_id": "doc-academic-rules",
        "source_id": "academic-rules",
        "title": "Academic Rules",
        "url": "https://www.lpu.in/academic-rules.pdf",
        "category": "academics",
        "section": "Late fee",
        "page": 2,
        "page_end": 3,
        "text": "Passage.",
    }


def test_citations_keep_the_block_numbers_used_in_the_answer() -> None:
    blocks = [make_chunk(1), make_chunk(2), make_chunk(3)]

    result = citations_for([1, 3], blocks)

    assert [(c["n"], c["chunk_id"]) for c in result] == [(1, "chunk-1"), (3, "chunk-3")]


def test_closest_sources_are_numbered_from_one() -> None:
    chunks = [make_chunk(5), make_chunk(6), make_chunk(7), make_chunk(8)]

    result = closest_sources(chunks, limit=3)

    assert [(c["n"], c["chunk_id"]) for c in result] == [
        (1, "chunk-5"),
        (2, "chunk-6"),
        (3, "chunk-7"),
    ]
