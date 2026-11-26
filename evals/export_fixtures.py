"""Export the frozen CI fixture (SPEC §11.5) from the live `kb_chunks` collection.

    uv run python ../evals/export_fixtures.py              # lpu.in documents only
    uv run python ../evals/export_fixtures.py --origins lpu.in ums --out <path>

Only public lpu.in documents go into the committed fixture by default (see
app/evals/fixtures.py). After re-exporting, re-run the gate with --write-baseline in the
same pull request and say why the corpus changed.
"""

import argparse
import sys
from pathlib import Path

from app.config import REPO_ROOT, get_settings
from app.evals.fixtures import PUBLIC_ORIGINS, export_fixture
from app.evals.runtime import setup_logging, sync_client


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "evals/fixtures/chunks.jsonl")
    parser.add_argument("--collection", help="default: QDRANT_COLLECTION")
    parser.add_argument("--origins", nargs="+", default=list(PUBLIC_ORIGINS))
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    setup_logging()
    settings = get_settings()
    client = sync_client(settings)
    try:
        count = export_fixture(
            client, args.collection or settings.qdrant_collection, args.out, args.origins
        )
    finally:
        client.close()
    print(f"Wrote {count} chunks ({', '.join(args.origins)}) to {args.out}")
    return 0 if count else 1


if __name__ == "__main__":
    sys.exit(main())
