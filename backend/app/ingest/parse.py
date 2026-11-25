"""Step 2 of ingestion (SPEC §8): Docling turns a raw file into a DoclingDocument.

Docling reads PDF (with OCR for scanned pages), DOCX, Markdown, HTML and images,
and keeps layout, tables, headings and page numbers. Web pages are cleaned first
(app/ingest/html_clean.py).

Guardrail: a paginated document is rejected when more than `max_empty_page_ratio`
of its pages yield no text even after OCR, so a bad scan is never half-indexed.
- A page has content if it holds text or a table with cells.
- A page where Docling found nothing at all (no text, picture or table) is a blank
  separator page, not a failed scan, and is left out of the ratio. A scanned page
  that OCR could not read still has layout elements (a picture, empty text), so it
  counts as empty.
"""

import logging
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path

from docling.datamodel.base_models import DocumentStream
from docling.document_converter import DocumentConverter
from docling_core.types.doc import ContentLayer, DoclingDocument, TableItem, TextItem

from app.ingest.html_clean import clean_html

logger = logging.getLogger(__name__)


class ParseError(Exception):
    """The file could not be parsed or failed the text-coverage guardrail."""


@dataclass(frozen=True)
class ParsedDocument:
    document: DoclingDocument
    page_count: int  # 0 for formats without pages (HTML, Markdown, DOCX)
    empty_pages: list[int] = field(default_factory=list)
    blank_pages: list[int] = field(default_factory=list)


def pages_with_elements(doc: DoclingDocument) -> set[int]:
    """Page numbers where Docling found anything: text, pictures, tables, headers."""
    layers = {ContentLayer.BODY, ContentLayer.FURNITURE}
    pages: set[int] = set()
    for item, _level in doc.iterate_items(traverse_pictures=True, included_content_layers=layers):
        pages.update(prov.page_no for prov in getattr(item, "prov", None) or [])
    return pages


def pages_with_content(doc: DoclingDocument) -> set[int]:
    """Page numbers that hold at least some text or a table with cells."""
    pages: set[int] = set()
    for item, _level in doc.iterate_items(traverse_pictures=True):
        has_content = (isinstance(item, TextItem) and item.text.strip()) or (
            isinstance(item, TableItem) and item.data.table_cells
        )
        if has_content:
            pages.update(prov.page_no for prov in item.prov)
    return pages


def has_text(doc: DoclingDocument) -> bool:
    return any(
        (isinstance(item, TextItem) and item.text.strip())
        or (isinstance(item, TableItem) and item.data.table_cells)
        for item, _level in doc.iterate_items(traverse_pictures=True)
    )


def check_text_coverage(doc: DoclingDocument, max_empty_ratio: float) -> ParsedDocument:
    """Apply the SPEC §8 guardrail and describe the document's pages."""
    page_numbers = sorted(doc.pages)
    if not has_text(doc):
        raise ParseError("no text found (scanned file without readable text?)")
    if not page_numbers:
        return ParsedDocument(doc, page_count=0)
    occupied = pages_with_elements(doc)
    blank = [page for page in page_numbers if page not in occupied]
    counted = [page for page in page_numbers if page in occupied]
    with_content = pages_with_content(doc)
    empty = [page for page in counted if page not in with_content]
    ratio = len(empty) / len(counted) if counted else 0.0
    if ratio > max_empty_ratio:
        raise ParseError(
            f"{len(empty)} of {len(counted)} non-blank pages have no text "
            f"({ratio:.0%} > {max_empty_ratio:.0%}): pages {empty}"
        )
    return ParsedDocument(doc, page_count=len(page_numbers), empty_pages=empty, blank_pages=blank)


class Parser:
    """Loads Docling's layout and OCR models on first use, then reuses them."""

    def __init__(self, max_empty_page_ratio: float) -> None:
        self.max_empty_page_ratio = max_empty_page_ratio
        self._converter: DocumentConverter | None = None

    def parse(self, path: Path) -> ParsedDocument:
        if self._converter is None:
            self._converter = DocumentConverter()
        try:
            if path.suffix == ".html":
                html = clean_html(path.read_text(encoding="utf-8", errors="replace"))
                source = DocumentStream(name=path.name, stream=BytesIO(html.encode("utf-8")))
                result = self._converter.convert(source)
            else:
                result = self._converter.convert(path)
        except Exception as error:  # Docling raises many types; report them all the same way
            raise ParseError(f"Docling could not parse {path.name}: {error}") from error
        parsed = check_text_coverage(result.document, self.max_empty_page_ratio)
        if parsed.empty_pages:
            logger.info("%s: pages without text: %s", path.name, parsed.empty_pages)
        if parsed.blank_pages:
            logger.info("%s: blank pages ignored: %s", path.name, parsed.blank_pages)
        return parsed
