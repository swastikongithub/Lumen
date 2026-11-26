"""Ablation study (SPEC §11.3): retrieval quality and latency for each configuration.

Writes evals/reports/ablation.md (the table for the README) and ablation.json. Run from
backend/ against the live index; no LLM is called:

    uv run python ../evals/ablations.py
    uv run python ../evals/ablations.py --chunk-sizes 256 384 512 --build

--chunk-sizes scores the best configuration on side collections built at those chunk
sizes (`kb_chunks_cs256`, ...); --build (re)creates them first, which needs the ingest
dependency group and the raw files in data/raw/. Parsed documents are cached, so only the
first build is slow. Latency is measured on this machine, one question at a time.
"""

import argparse
import asyncio
import json
import os
import platform
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from app.config import REPO_ROOT, Settings, get_settings
from app.evals.golden import GoldenCase, load_golden_set
from app.evals.metrics import percentile
from app.evals.report import (
    by_type_table,
    metrics_row,
    misses,
    ms,
    pct,
    runs_table,
    table,
    threshold_table,
)
from app.evals.retrieval import Mode, RetrievalConfig, RunResult, run_config
from app.evals.runtime import (
    async_client,
    make_searcher,
    scorer,
    setup_logging,
    short_model_name,
    sync_client,
)
from app.evals.threshold import choose, sweep

REPORTS = REPO_ROOT / "evals" / "reports"
MINILM_L6 = "Xenova/ms-marco-MiniLM-L-6-v2"
MINILM_L12 = "Xenova/ms-marco-MiniLM-L-12-v2"
BGE_BASE = "BAAI/bge-reranker-base"

CONFIGS = [
    RetrievalConfig("Dense only", Mode.DENSE),
    RetrievalConfig("BM25 only", Mode.BM25),
    RetrievalConfig("Hybrid (RRF)", Mode.HYBRID),
    RetrievalConfig("Hybrid + MiniLM-L-6 re-rank", Mode.HYBRID, MINILM_L6),
    RetrievalConfig("Hybrid + MiniLM-L-12 re-rank", Mode.HYBRID, MINILM_L12),
    RetrievalConfig("Hybrid + bge-reranker-base", Mode.HYBRID, BGE_BASE),
    RetrievalConfig("Hybrid (10 candidates) + MiniLM-L-6", Mode.HYBRID, MINILM_L6, candidates=10),
    RetrievalConfig("Hybrid (10 candidates) + MiniLM-L-12", Mode.HYBRID, MINILM_L12, candidates=10),
]


def best_run(runs: list[RunResult]) -> RunResult:
    """Highest Hit@5, then MRR@10, then Recall@5; on a full tie, the faster re-rank."""

    def key(run: RunResult) -> tuple[float, float, float, float]:
        s = run.summary
        speed = -percentile(run.rerank_seconds, 50) if run.rerank_seconds else 0.0
        return (round(s.hit_at_5, 3), round(s.mrr_at_10, 3), round(s.recall_at_5, 3), speed)

    return max(runs, key=key)


async def score_collection(
    settings: Settings, cases: list[GoldenCase], collection: str, configs: list[RetrievalConfig]
) -> list[RunResult]:
    client = async_client(settings)
    try:
        searcher = make_searcher(settings, client, collection)
        results = []
        for config in configs:
            print(f"  {config.name} on {collection} ...", flush=True)
            model = scorer(config.reranker) if config.reranker else None
            results.append(await run_config(cases, searcher, config, model))
        return results
    finally:
        await client.close()


def build_chunk_sizes(settings: Settings, sizes: list[int]) -> dict[int, int]:
    # Docling is only needed here, so it is imported only here.
    from app.evals.chunk_size import (
        PARSED_DIR_NAME,
        build_size_collection,
        parse_sources,
        size_collection,
    )
    from app.ingest.fetch import Fetcher, urllib_get
    from app.ingest.index import Embedder
    from app.ingest.parse import Parser
    from app.ingest.sources import load_sources

    sources = load_sources(settings.sources_path)
    fetcher = Fetcher(
        settings.raw_dir,
        settings.fetch_user_agent,
        urllib_get(settings.fetch_user_agent, settings.fetch_timeout_seconds),
        offline=True,
    )
    parsed = parse_sources(
        sources, fetcher, Parser(settings.max_empty_page_ratio), settings.raw_dir / PARSED_DIR_NAME
    )
    embedder = Embedder(settings.embed_model, settings.embed_batch_size)
    client = sync_client(settings)
    try:
        return {
            size: build_size_collection(
                client,
                size_collection(settings.qdrant_collection, size),
                parsed,
                chunk_tokens=size,
                embedder=embedder,
                embed_dim=settings.embed_dim,
            )
            for size in sizes
        }
    finally:
        client.close()


def collection_stats(settings: Settings, collection: str) -> tuple[int, int]:
    """(chunks, documents) in a collection."""
    client = sync_client(settings)
    try:
        chunks = client.count(collection, exact=True).count
        seen: set[str] = set()
        offset = None
        while True:
            batch, offset = client.scroll(
                collection, limit=512, offset=offset, with_payload=["source_id"]
            )
            seen.update((p.payload or {}).get("source_id", "") for p in batch)
            if offset is None:
                return chunks, len(seen)
    finally:
        client.close()


def machine() -> str:
    cpu = platform.processor() or "CPU"
    return f"{platform.system()} {platform.release()}, {cpu}, {os.cpu_count()} logical cores"


def write_report(
    settings: Settings,
    cases: list[GoldenCase],
    runs: list[RunResult],
    size_runs: dict[int, RunResult],
    size_chunks: dict[int, int],
) -> None:
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    chunks, documents = collection_stats(settings, settings.qdrant_collection)
    counts = Counter(case.type.value for case in cases)
    best = best_run(runs)
    reranked = [run for run in runs if run.config.reranker and run.config.candidates == 20]

    lines = [
        "# Retrieval ablation",
        "",
        f"Measured {now} with `evals/ablations.py` on {machine()}.",
        f"Corpus: `{settings.qdrant_collection}`, {chunks} chunks from {documents} documents "
        f"(chunk size {settings.chunk_max_tokens} tokens, origins: "
        f"{', '.join(settings.retrieval_origins) or 'all'}).",
        f"Golden set: {len(cases)} questions ({counts['answerable']} answerable, "
        f"{counts['multi']} multi-part, {counts['unanswerable']} unanswerable); "
        "the retrieval metrics use the answerable and multi-part ones.",
        "Hybrid search fetches 30 dense + 30 BM25 candidates and fuses them with RRF; "
        "re-rankers score the fused top 20 (or 10) and the top 10 are scored. "
        "Latency is per question on CPU, one question at a time.",
        "",
        "## Configurations",
        "",
        runs_table(runs),
        "",
        f"Best: **{best.config.name}** (highest Hit@5, then MRR@10, then Recall@5).",
        "",
        "### Best configuration by question type",
        "",
        by_type_table(best.summary),
        "",
        f"No relevant chunk in its top 5: {', '.join(misses(best)) or 'none'}.",
    ]

    if size_runs:
        rows = [
            [f"{size} tokens", size_chunks.get(size, "?"), *metrics_row("", run.summary)[1:]]
            for size, run in sorted(size_runs.items())
        ]
        lines += [
            "",
            f"## Chunk size ({best.config.name})",
            "",
            "Each size is a side collection built from the same parsed documents "
            "(`app/evals/chunk_size.py`); relevance is by page and heading, so the same "
            "labels apply to every size.",
            "",
            table(["Chunk size", "Chunks", "Hit@5", "Recall@5", "MRR@10"], rows),
        ]

    lines += ["", "## Abstention threshold τ", ""]
    summary_rows = []
    for run in reranked:
        rows = sweep(cases, run.best_scores)
        chosen = choose(rows)
        summary_rows.append(
            [
                run.config.name,
                f"{chosen.threshold:+.1f}" if chosen else "none fits",
                pct(chosen.unanswerable_abstained) if chosen else "-",
                pct(chosen.false_abstains) if chosen else "-",
            ]
        )
    lines += [
        "τ is applied to the best re-rank score (raw cross-encoder logits). The chosen τ "
        "abstains on the most unanswerable questions while keeping false abstains on "
        "answerable ones at 5% or less (SPEC §11.4). Unanswerable questions that pass τ "
        'still reach the LLM, which is told to answer "not found".',
        "",
        table(["Re-ranker", "Chosen τ", "Unanswerable abstained", "False abstains"], summary_rows),
    ]
    production = next(
        (run for run in reranked if run.config.reranker == settings.rerank_model), None
    )
    if production is not None:
        rows = sweep(cases, production.best_scores)
        lines += [
            "",
            f"Sweep for the configured re-ranker ({short_model_name(settings.rerank_model)}):",
            "",
            threshold_table([r for r in rows if -6.0 <= r.threshold <= 6.0], choose(rows)),
        ]

    lines += [
        "",
        "## Reproduce",
        "",
        "```bash",
        "cd backend",
        "uv run python ../evals/ablations.py --chunk-sizes 256 384 512 --build",
        "```",
        "",
    ]
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "ablation.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")

    data = {
        "measured_at": now,
        "machine": machine(),
        "collection": settings.qdrant_collection,
        "chunks": chunks,
        "documents": documents,
        "questions": dict(counts),
        "configs": [
            {
                "name": run.config.name,
                "mode": run.config.mode.value,
                "reranker": run.config.reranker,
                "candidates": run.config.candidates,
                **run.summary.as_dict(),
                "retrieve_p50_ms": float(ms(percentile(run.retrieve_seconds, 50))),
                "rerank_p50_ms": float(ms(percentile(run.rerank_seconds, 50)))
                if run.rerank_seconds
                else None,
                "rerank_p95_ms": float(ms(percentile(run.rerank_seconds, 95)))
                if run.rerank_seconds
                else None,
                "best_scores": run.best_scores,
            }
            for run in runs
        ],
        "chunk_sizes": {
            str(size): {"chunks": size_chunks.get(size), **run.summary.as_dict()}
            for size, run in size_runs.items()
        },
        "best": best.config.name,
    }
    (REPORTS / "ablation.json").write_text(
        json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n"
    )


async def run(args: argparse.Namespace) -> int:
    settings = get_settings()
    cases = load_golden_set(args.golden)
    configs = [c for c in CONFIGS if not args.only or c.name in args.only]
    print(f"Scoring {len(configs)} configurations on {len(cases)} questions")
    runs = await score_collection(settings, cases, settings.qdrant_collection, configs)

    size_runs: dict[int, RunResult] = {}
    size_chunks: dict[int, int] = {}
    if args.chunk_sizes:
        if args.build:
            size_chunks = build_chunk_sizes(settings, args.chunk_sizes)
        from app.evals.chunk_size import size_collection

        best = best_run(runs).config
        for size in args.chunk_sizes:
            name = size_collection(settings.qdrant_collection, size)
            [size_runs[size]] = await score_collection(settings, cases, name, [best])
            size_chunks.setdefault(size, collection_stats(settings, name)[0])

    write_report(settings, cases, runs, size_runs, size_chunks)
    print(f"\n{runs_table(runs)}\n\nWrote {REPORTS / 'ablation.md'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--golden", type=Path, default=REPO_ROOT / "evals/golden_set.jsonl")
    parser.add_argument("--chunk-sizes", type=int, nargs="*", default=[])
    parser.add_argument("--build", action="store_true", help="(re)build the chunk-size collections")
    parser.add_argument("--only", nargs="*", help="run only these config names")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    setup_logging(args.verbose)
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
