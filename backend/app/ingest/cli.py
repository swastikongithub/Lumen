"""The `lumen` command (SPEC §8).

    uv run lumen ingest --all          every source; prunes ones removed from sources.yaml
    uv run lumen ingest --id exam-policy [--id ...]
    uv run lumen ingest --all --force  re-chunk unchanged files (e.g. new chunk size)
    uv run lumen ingest --all --offline  use data/raw/ only, no downloads
    uv run lumen stats                 documents, chunks, avg chunk tokens, corpus_version

Needs the `ingest` dependency group (uv sync --all-groups) and docker compose services.
"""

import asyncio
import logging
import sys
from collections import Counter
from typing import Annotated

import typer
from qdrant_client import QdrantClient

from app.config import Settings, get_settings
from app.db.session import create_engine, create_sessionmaker
from app.ingest.pipeline import Outcome, SourceResult
from app.ingest.sources import Source, SourcesError, load_sources
from app.ingest.stats import CorpusStats, collect_stats

app = typer.Typer(help="Lumen ingestion tools.", no_args_is_help=True, add_completion=False)
logger = logging.getLogger("lumen")

# Third-party loggers that are chatty at INFO.
QUIET_LOGGERS = ("docling", "docling_core", "RapidOCR", "httpx", "fastembed", "transformers")


def qdrant_client(settings: Settings) -> QdrantClient:
    api_key = settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else None
    return QdrantClient(url=settings.qdrant_url, api_key=api_key)


@app.callback()
def main(
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Show debug logs.")] = False,
) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")  # titles may not fit a legacy console
    level = logging.DEBUG if verbose else get_settings().log_level
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not verbose:
        for name in QUIET_LOGGERS:
            logging.getLogger(name).setLevel(logging.WARNING)


def select_sources(sources: list[Source], all_sources: bool, ids: list[str]) -> list[Source]:
    if all_sources == bool(ids):
        raise typer.BadParameter("use either --all or one or more --id")
    if all_sources:
        return sources
    known = {s.id for s in sources}
    unknown = [sid for sid in ids if sid not in known]
    if unknown:
        raise typer.BadParameter(f"not in sources.yaml: {', '.join(unknown)}")
    return [s for s in sources if s.id in set(ids)]


@app.command()
def ingest(
    all_sources: Annotated[
        bool, typer.Option("--all", help="Every source; prune ones no longer listed.")
    ] = False,
    ids: Annotated[list[str] | None, typer.Option("--id", help="A source id (repeatable).")] = None,
    force: Annotated[bool, typer.Option(help="Re-index files even if unchanged.")] = False,
    offline: Annotated[bool, typer.Option(help="Use data/raw/ only; download nothing.")] = False,
) -> None:
    """Fetch, parse, chunk, embed and index sources from data/sources.yaml."""
    settings = get_settings()
    try:
        sources = load_sources(settings.sources_path)
    except SourcesError as error:
        typer.echo(f"sources.yaml is invalid: {error}", err=True)
        raise typer.Exit(2) from error
    selected = select_sources(sources, all_sources, ids or [])

    results = asyncio.run(
        run_ingest(settings, selected, force=force, offline=offline, prune=all_sources)
    )
    print_results(results)
    if any(r.outcome is Outcome.FAILED for r in results):
        raise typer.Exit(1)


async def run_ingest(
    settings: Settings, sources: list[Source], *, force: bool, offline: bool, prune: bool
) -> list[SourceResult]:
    # Imported here so `lumen stats` does not pay for loading Docling.
    from app.ingest.chunk import DocumentChunker, huggingface_tokenizer
    from app.ingest.fetch import Fetcher, urllib_get
    from app.ingest.index import Embedder, ensure_collection
    from app.ingest.parse import ParsedDocument, Parser
    from app.ingest.pipeline import Ingestor

    chunker: DocumentChunker | None = None

    def chunk(parsed: ParsedDocument):
        nonlocal chunker
        if chunker is None:  # downloads the tokenizer only when something needs chunking
            tokenizer = huggingface_tokenizer(settings.embed_model, settings.chunk_max_tokens)
            chunker = DocumentChunker(tokenizer)
        return chunker.chunk(parsed.document)

    qdrant = qdrant_client(settings)
    ensure_collection(qdrant, settings.qdrant_collection, settings.embed_dim)
    engine = create_engine(settings.database_url)
    try:
        ingestor = Ingestor(
            qdrant=qdrant,
            collection=settings.qdrant_collection,
            session_factory=create_sessionmaker(engine),
            fetcher=Fetcher(
                settings.raw_dir,
                settings.fetch_user_agent,
                urllib_get(settings.fetch_user_agent, settings.fetch_timeout_seconds),
                delay_seconds=settings.fetch_delay_seconds,
                offline=offline,
            ),
            parser=Parser(settings.max_empty_page_ratio),
            chunk=chunk,
            embedder=Embedder(settings.embed_model, settings.embed_batch_size),
            embed_model=settings.embed_model,
        )
        return await ingestor.run(sources, force=force, prune_missing=prune)
    finally:
        await engine.dispose()
        qdrant.close()


def print_results(results: list[SourceResult]) -> None:
    for r in results:
        typer.echo(f"{r.outcome.value:<10} {r.source_id:<40} {r.detail}")
    counts = Counter(r.outcome.value for r in results)
    typer.echo("\n" + ", ".join(f"{n} {outcome}" for outcome, n in sorted(counts.items())))


@app.command()
def stats() -> None:
    """Show what is indexed: documents, chunks, average chunk tokens, corpus version."""
    print_stats(asyncio.run(run_stats(get_settings())))


async def run_stats(settings: Settings) -> CorpusStats:
    qdrant = qdrant_client(settings)
    engine = create_engine(settings.database_url)
    try:
        async with create_sessionmaker(engine)() as session:
            return await collect_stats(session, qdrant, settings.qdrant_collection)
    finally:
        await engine.dispose()
        qdrant.close()


def print_stats(s: CorpusStats) -> None:
    rows = [
        ("corpus_version", str(s.corpus_version)),
        ("documents", f"{s.active_documents} active, {s.superseded_documents} superseded"),
        ("chunks", str(s.chunks)),
        ("chunk tokens", f"avg {s.avg_chunk_tokens:.0f}, max {s.max_chunk_tokens}"),
        ("by category", ", ".join(f"{k} {v}" for k, v in s.documents_by_category.items())),
        ("chunks by origin", ", ".join(f"{k} {v}" for k, v in s.chunks_by_origin.items())),
    ]
    for label, value in rows:
        typer.echo(f"{label:<17} {value}")
