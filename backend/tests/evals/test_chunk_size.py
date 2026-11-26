"""Chunk-size side collections: parse cache and rebuild, with no Docling models or HF."""

import hashlib
from pathlib import Path

from qdrant_client import QdrantClient, models

from app.evals.chunk_size import (
    ParsedSource,
    build_size_collection,
    cache_path,
    parse_sources,
    size_collection,
)
from app.ingest.fetch import FetchedFile, FetchError
from app.ingest.parse import ParsedDocument, ParseError
from app.ingest.sources import Source
from tests.ingest.docling_fixtures import add_heading, add_paragraph, make_document
from tests.ingest.test_chunk import WordTokenizer


def source(id: str) -> Source:
    return Source.model_validate(
        {
            "id": id,
            "title": f"Title {id}",
            "url": f"https://www.lpu.in/{id}.pdf",
            "category": "exams",
        }
    )


def document(words: int = 30):
    doc = make_document(pages=2)
    add_heading(doc, "Examination Rules", page=1)
    add_paragraph(doc, " ".join(["rule"] * words), page=1)
    add_heading(doc, "Unfair Means", page=2)
    add_paragraph(doc, " ".join(["phone"] * words), page=2)
    return doc


class FakeFetcher:
    def __init__(self, tmp_path: Path, missing: set[str] = frozenset()) -> None:
        self.tmp_path = tmp_path
        self.missing = missing

    def get(self, src: Source) -> FetchedFile:
        if src.id in self.missing:
            raise FetchError(f"{src.id}: not in data/raw")
        path = self.tmp_path / f"{src.id}.pdf"
        path.write_bytes(src.id.encode())
        return FetchedFile(path, hashlib.sha256(src.id.encode()).hexdigest(), downloaded=False)


class FakeParser:
    def __init__(self, broken: set[str] = frozenset()) -> None:
        self.parsed: list[str] = []
        self.broken = broken

    def parse(self, path: Path) -> ParsedDocument:
        self.parsed.append(path.stem)
        if path.stem in self.broken:
            raise ParseError("bad scan")
        return ParsedDocument(document(), page_count=2)


def test_parse_sources_caches_docling_json(tmp_path: Path) -> None:
    cache = tmp_path / "_parsed"
    sources = [source("a"), source("b"), source("gone"), source("bad")]
    fetcher = FakeFetcher(tmp_path, missing={"gone"})
    parser = FakeParser(broken={"bad"})
    first = parse_sources(sources, fetcher, parser, cache)
    assert [p.source.id for p in first] == ["a", "b"]  # failures are skipped
    assert cache_path(cache, "a", first[0].sha256).exists()

    again = FakeParser()
    second = parse_sources(sources[:2], fetcher, again, cache)
    assert again.parsed == []  # both came from the cache
    assert second[0].document.export_to_markdown() == first[0].document.export_to_markdown()


class FakeEmbedder:
    model_name = "fake-model"

    def embed(self, texts):
        return [[1.0, float(len(text) % 7), 0.5] for text in texts]


def fake_sparse(text: str) -> models.SparseVector:
    return models.SparseVector(indices=[len(text) % 50], values=[1.0])


def test_build_size_collection(tmp_path: Path) -> None:
    client = QdrantClient(":memory:")
    parsed = [ParsedSource(source(id), id * 64, document(words=30)) for id in ("a", "b")]
    name = size_collection("kb_chunks", 20)
    assert name == "kb_chunks_cs20"

    def build(tokens: int) -> int:
        return build_size_collection(
            client,
            name,
            parsed,
            chunk_tokens=tokens,
            embedder=FakeEmbedder(),
            embed_dim=3,
            tokenizer=lambda model, max_tokens: WordTokenizer(max_tokens=max_tokens),
            sparse=fake_sparse,
        )

    small = build(20)
    assert client.count(name).count == small
    large = build(200)  # rebuilt from scratch, fewer and larger chunks
    assert large < small
    assert client.count(name).count == large
    point = client.scroll(name, limit=1, with_payload=True)[0][0]
    assert point.payload["source_id"] in {"a", "b"}
    assert point.payload["corpus_version"] == 0
    assert point.payload["embed_model"] == "fake-model"
