"""Small DoclingDocuments built in code, so tests need no files or Docling models."""

from docling_core.types.doc import (
    BoundingBox,
    DocItemLabel,
    DoclingDocument,
    ProvenanceItem,
    Size,
    TableCell,
    TableData,
)


def prov(page: int, text: str = "x") -> ProvenanceItem:
    return ProvenanceItem(
        page_no=page, bbox=BoundingBox(l=0, t=0, r=100, b=10), charspan=(0, len(text))
    )


def make_document(pages: int = 0) -> DoclingDocument:
    doc = DoclingDocument(name="test")
    for page in range(1, pages + 1):
        doc.add_page(page_no=page, size=Size(width=600, height=800))
    return doc


def add_heading(doc: DoclingDocument, text: str, page: int | None = None) -> None:
    doc.add_heading(text=text, level=1, prov=prov(page, text) if page else None)


def add_paragraph(doc: DoclingDocument, text: str, page: int | None = None) -> None:
    doc.add_text(label=DocItemLabel.TEXT, text=text, prov=prov(page, text) if page else None)


def add_table(doc: DoclingDocument, rows: list[list[str]], page: int | None = None) -> None:
    cells = [
        TableCell(
            text=value,
            start_row_offset_idx=r,
            end_row_offset_idx=r + 1,
            start_col_offset_idx=c,
            end_col_offset_idx=c + 1,
        )
        for r, row in enumerate(rows)
        for c, value in enumerate(row)
    ]
    data = TableData(num_rows=len(rows), num_cols=len(rows[0]), table_cells=cells)
    doc.add_table(data=data, prov=prov(page) if page else None)


def add_picture(doc: DoclingDocument, page: int) -> None:
    """A scanned image with no readable text, as when OCR fails."""
    doc.add_picture(prov=prov(page))
