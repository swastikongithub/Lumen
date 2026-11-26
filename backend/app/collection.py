"""Layout of the `kb_chunks` Qdrant collection (SPEC §7.2), shared by ingestion, the API
and the evals.

It lives outside `app/ingest/` because the API image has no Docling, and everything in
`app/ingest/` may import it. The evals build collections with the same layout (frozen CI
fixture, chunk-size ablation) without installing the ingest group.
"""

from qdrant_client import QdrantClient, models

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


def ensure_collection(client: QdrantClient, name: str, dim: int) -> None:
    """Create the collection with its named vectors and payload indexes if it is missing."""
    if client.collection_exists(name):
        return
    client.create_collection(
        collection_name=name,
        vectors_config={
            DENSE_VECTOR: models.VectorParams(size=dim, distance=models.Distance.COSINE)
        },
        sparse_vectors_config={
            SPARSE_VECTOR: models.SparseVectorParams(modifier=models.Modifier.IDF)
        },
    )
    for field_name, schema in PAYLOAD_INDEXES.items():
        client.create_payload_index(name, field_name=field_name, field_schema=schema)
