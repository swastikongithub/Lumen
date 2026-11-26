"""Retrieval eval (SPEC §11.2) and the CI quality gate (SPEC §11.5). No LLM is called.

Scores the production retrieval config (hybrid RRF + the configured re-ranker) on the
golden set with Hit@5, Recall@5 and MRR@10. Run from backend/:

    uv run python ../evals/retrieval_eval.py                  # live kb_chunks collection
    uv run python ../evals/retrieval_eval.py --fixture ../evals/fixtures/chunks.jsonl --check
    uv run python ../evals/retrieval_eval.py --fixture ../evals/fixtures/chunks.jsonl \
        --write-baseline --note "why the baseline changed"

With --fixture, the frozen snapshot is loaded into a scratch collection first and only
questions whose evidence is in it are scored. --check exits 1 if Hit@5 or MRR@10 is more
than the tolerance below evals/baseline.json.
"""

import argparse
import asyncio
import sys
from pathlib import Path

from app.config import REPO_ROOT, get_settings
from app.evals import baseline as gate
from app.evals.fixtures import file_sha256, fixture_source_ids, load_fixture, read_fixture
from app.evals.golden import load_golden_set
from app.evals.report import by_type_table, misses, runs_table
from app.evals.retrieval import run_config
from app.evals.runtime import (
    async_client,
    covered_cases,
    make_searcher,
    production_config,
    scorer,
    setup_logging,
    sync_client,
)

EVALS = REPO_ROOT / "evals"
FIXTURE_COLLECTION = "kb_chunks_fixture"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--golden", type=Path, default=EVALS / "golden_set.jsonl")
    parser.add_argument("--fixture", type=Path, help="score the frozen snapshot, not kb_chunks")
    parser.add_argument("--baseline", type=Path, default=EVALS / "baseline.json")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--check", action="store_true", help="fail on a regression")
    action.add_argument("--write-baseline", action="store_true", help="record this run")
    parser.add_argument("--note", default="", help="why the baseline changed")
    parser.add_argument("--verbose", "-v", action="store_true")
    return parser.parse_args(argv)


async def run(args: argparse.Namespace) -> int:
    settings = get_settings()
    cases = load_golden_set(args.golden)
    config = production_config(settings)
    if (args.check or args.write_baseline) and not args.fixture:
        print("--check and --write-baseline need --fixture", file=sys.stderr)
        return 2

    if args.fixture:
        records = read_fixture(args.fixture)
        qdrant = sync_client(settings)
        try:
            load_fixture(qdrant, FIXTURE_COLLECTION, records)
        finally:
            qdrant.close()
        cases = covered_cases(cases, fixture_source_ids(records))
        collection, origins = FIXTURE_COLLECTION, ()
        print(f"Fixture: {len(records)} chunks; {len(cases)} questions have evidence in it")
    else:
        collection, origins = settings.qdrant_collection, None

    client = async_client(settings)
    try:
        searcher = make_searcher(settings, client, collection, origins)
        assert config.reranker is not None
        result = await run_config(cases, searcher, config, scorer(config.reranker))
    finally:
        await client.close()

    print()
    print(runs_table([result]))
    print()
    print(by_type_table(result.summary))
    missed = misses(result)
    print(f"\nNo relevant chunk in the top 5: {', '.join(missed) if missed else 'none'}")

    if not args.fixture:
        return 0
    fixture_sha, golden_sha = file_sha256(args.fixture), file_sha256(args.golden)
    if args.write_baseline:
        made = gate.make_baseline(
            config.name,
            result.summary,
            fixture_sha256=fixture_sha,
            golden_set_sha256=golden_sha,
            note=args.note,
        )
        gate.write_baseline(args.baseline, made)
        print(f"\nWrote {args.baseline}")
        return 0
    if args.check:
        baseline = gate.load_baseline(args.baseline)
        for warning in gate.staleness(
            baseline, config=config.name, fixture_sha256=fixture_sha, golden_set_sha256=golden_sha
        ):
            print(f"warning: {warning}")
        failures = gate.regressions(result.summary, baseline)
        for failure in failures:
            print(f"FAIL: {failure}")
        if failures:
            return 1
        print(f"\nQuality gate passed (tolerance {baseline.tolerance:.2f}).")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    setup_logging(args.verbose)
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
