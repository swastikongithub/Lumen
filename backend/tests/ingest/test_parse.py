import pytest

from app.ingest.parse import ParseError, check_text_coverage
from tests.ingest.docling_fixtures import (
    add_paragraph,
    add_picture,
    add_table,
    make_document,
)


def test_pages_with_text_or_tables_count_as_content() -> None:
    doc = make_document(pages=3)
    add_paragraph(doc, "Attendance must be at least 75%.", page=1)
    add_table(doc, [["Days late", "Fine"], ["1-10", "Rs 500"]], page=2)  # table-only page
    add_paragraph(doc, "Contact the registrar.", page=3)

    parsed = check_text_coverage(doc, max_empty_ratio=0.2)

    assert parsed.page_count == 3
    assert parsed.empty_pages == []


def test_a_few_pages_without_text_are_tolerated() -> None:
    doc = make_document(pages=5)
    for page in (1, 2, 3, 4):
        add_paragraph(doc, f"Rule {page}.", page=page)
    add_picture(doc, 5)  # a photo page with no text

    parsed = check_text_coverage(doc, max_empty_ratio=0.2)

    assert parsed.empty_pages == [5]


def test_mostly_unreadable_scans_are_rejected() -> None:
    doc = make_document(pages=4)
    add_paragraph(doc, "Cover page", page=1)
    for page in (2, 3, 4):
        add_picture(doc, page)  # scanned pages OCR could not read

    with pytest.raises(ParseError, match="3 of 4 non-blank pages have no text"):
        check_text_coverage(doc, max_empty_ratio=0.2)


def test_blank_separator_pages_are_ignored() -> None:
    doc = make_document(pages=2)  # e.g. instructions followed by an empty back page
    add_paragraph(doc, "No mobile phones in the exam hall.", page=1)

    parsed = check_text_coverage(doc, max_empty_ratio=0.2)

    assert (parsed.page_count, parsed.empty_pages, parsed.blank_pages) == (2, [], [2])


def test_documents_without_any_text_are_rejected() -> None:
    with pytest.raises(ParseError, match="no text found"):
        check_text_coverage(make_document(pages=2), max_empty_ratio=0.2)


def test_formats_without_pages_need_only_some_text() -> None:
    doc = make_document(pages=0)  # HTML, Markdown and DOCX have no page numbers
    add_paragraph(doc, "Mentorship guidelines.")

    parsed = check_text_coverage(doc, max_empty_ratio=0.2)

    assert parsed.page_count == 0
