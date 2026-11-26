"""Layout of the `kb_chunks` Qdrant collection (SPEC §7.2), shared by ingestion and the API.

It lives outside `app/ingest/` because the API image has no Docling, and everything in
`app/ingest/` may import it.
"""

from qdrant_client import models

DENSE_VECTOR = "dense"
SPARSE_VECTOR = "bm25"
BM25_MODEL = "Qdrant/bm25"

PAYLOAD_INDEXES = {
    "category": models.PayloadSchemaType.KEYWORD,
    "document_id": models.PayloadSchemaType.KEYWORD,
    "source_id": models.PayloadSchemaType.KEYWORD,
    "academic_year": models.PayloadSchemaType.KEYWORD,
    "origin": models.PayloadSchemaType.KEYWORD,
    "corpus_version": models.PayloadSchemaType.INTEGER,
}


def bm25_document(text: str) -> models.Document:
    """Raw text for Qdrant's server-side BM25. Chunks and queries both go through this."""
    return models.Document(text=text, model=BM25_MODEL)
