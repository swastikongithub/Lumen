# Lumen backend

FastAPI API, ingestion CLI and evals. See `docs/SPEC.md` and the commands in `CLAUDE.md`.

## Ingestion (SPEC §8)

```bash
docker compose up -d               # Qdrant + Postgres (from the repo root)
uv sync --all-groups               # the ingest group brings Docling
uv run alembic upgrade head
uv run lumen ingest --all          # every source in data/sources.yaml
uv run lumen stats                 # documents, chunks, avg chunk tokens, corpus_version
```

Other options:

- `--id <source-id>` (repeatable) ingests only some sources.
- `--force` re-chunks files that haven't changed, for example after changing `CHUNK_MAX_TOKENS`.
- `--offline` uses `data/raw/` only and downloads nothing.

How the pipeline works:

- **Fetch.** Sources are downloaded to `data/raw/<id>.<ext>` with the `LumenBot` User-Agent, only where robots.txt allows.
  - `fetch: manual` entries are never downloaded. Save them by hand as `data/raw/<id>.<ext>`.
  - If a download fails, an existing local copy is used and the summary says so.
- **Change detection.** A file whose sha256 matches the active version is skipped.
  - A changed file becomes a new version.
  - The old version's chunks are deleted and its row is marked `superseded`.
  - With `--all`, sources removed from `sources.yaml` are pruned the same way.
- **Empty-page check.** A PDF is rejected when more than 20% of its pages have no text, even after OCR (`MAX_EMPTY_PAGE_RATIO`).
- **Exit code.** The command exits with code 1 if any source failed. The summary lists why.

The first run downloads Docling's layout and OCR models, the bge-small tokenizer and the FastEmbed model. Expect a few minutes before the first document is processed.
