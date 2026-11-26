"""Chunk-size ablation (SPEC §11.3): rebuild the corpus at other chunk sizes.

Each size gets its own side collection (`<collection>_cs256`, ...), built from the same
parsed documents with the same chunker, embedder and payload as `lumen ingest`. The
live `kb_chunks` collection and Postgres are never touched.

Parsing with Docling (OCR included) is by far the slowest step, so each parsed document
is cached as Docling JSON under `data/raw/_parsed/`, keyed by the file's sha256. The
cache is gitignored with the rest of `data/raw/`.

Needs the `ingest` dependency group (Docling). Raw files must already be in `data/raw/`
(run `lumen ingest` first); nothing is downloaded.
"""

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from docling_core.transforms.chunker.tokenizer.base import BaseTokenizer
from docling_core.types.doc import DoclingDocument, ImageRefMode
from qdrant_client import QdrantClient

from app.collection import bm25_document, ensure_collection
from app.ingest import index
from app.ingest.chunk import DocumentChunker, huggingface_tokenizer
from app.ingest.fetch import Fetcher, FetchError
from app.ingest.parse import ParseError, Parser
from app.ingest.sources import Source

logger = logging.getLogger(__name__)

PARSED_DIR_NAME = "_parsed"


@dataclass(frozen=True)
class ParsedSource:
    source: Source
    sha256: str
    document: DoclingDocument


def size_collection(base: str, chunk_tokens: int) -> str:
    return f"{base}_cs{chunk_tokens}"


def cache_path(cache_dir: Path, source_id: str, sha256: str) -> Path:
    return cache_dir / f"{source_id}-{sha256[:16]}.json"


def parse_sources(
    sources: Sequence[Source], fetcher: Fetcher, parser: Parser, cache_dir: Path
) -> list[ParsedSource]:
    """Parse every source from data/raw/, reusing cached Docling JSON when it exists.
    Sources that fail to fetch or parse are skipped, as `lumen ingest` would."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    parsed = []
    for source in sources:
        try:
            fetched = fetcher.get(source)
            path = cache_path(cache_dir, source.id, fetched.sha256)
            if path.exists():
                document = DoclingDocument.load_from_json(path)
            else:
                document = parser.parse(fetched.path).document
                document.save_as_json(path, image_mode=ImageRefMode.PLACEHOLDER, indent=0)
                logger.info("%s: parsed and cached", source.id)
        except (FetchError, ParseError) as error:
            logger.warning("%s: skipped (%s)", source.id, error)
            continue
        parsed.append(ParsedSource(source, fetched.sha256, document))
    return parsed


def build_size_collection(
    client: QdrantClient,
    collection: str,
    parsed: Sequence[ParsedSource],
    *,
    chunk_tokens: int,
    embedder: index.Embedder,
    embed_dim: int,
    tokenizer: Callable[[str, int], BaseTokenizer] = huggingface_tokenizer,
    sparse: index.SparseFactory = bm25_document,
) -> int:
    """(Re)create `collection` with every document chunked at `chunk_tokens`.
    Returns the number of chunks."""
    if client.collection_exists(collection):
        client.delete_collection(collection)
    ensure_collection(client, collection, embed_dim)
    chunker = DocumentChunker(tokenizer(embedder.model_name, chunk_tokens))
    total = 0
    for item in parsed:
        chunks = chunker.chunk(item.document)
        if not chunks:
            continue
        vectors = embedder.embed([chunk.embed_text for chunk in chunks])
        meta = index.DocumentMeta(
            document_id=index.document_id(item.source.id, 1),
            source_id=item.source.id,
            title=item.source.title,
            source_url=item.source.url,
            category=item.source.category.value,
            academic_year=item.source.academic_year,
            origin=item.source.origin_label,
            content_hash=item.sha256,
            corpus_version=0,  # side collections are not corpus versions
            embed_model=embedder.model_name,
        )
        index.upsert_points(client, collection, index.build_points(meta, chunks, vectors, sparse))
        total += len(chunks)
    logger.info("%s: %d chunks at %d tokens", collection, total, chunk_tokens)
    return total
