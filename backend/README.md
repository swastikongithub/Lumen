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

## Chat API (SPEC §9, §10)

```bash
cp .env.example .env               # then set GROQ_API_KEY and/or GEMINI_API_KEY
uv run uvicorn app.main:app --reload
```

Try it once documents are ingested (any UUID works as the session ID):

```bash
curl -N -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-Session-Id: 3f2b8c1e-6a4d-4e2f-9b7a-1c5d8e9f0a2b" \
  -d '{"message": "Can I carry a mobile phone into the exam hall?"}'
```

What happens to a question (`app/rag/`):

1. **Retrieve** (`retriever.py`). One Qdrant query runs a dense search (bge-small) and a BM25 search. RRF fuses them into the top 20, with an optional `category` filter.
2. **Re-rank** (`reranker.py`). A cross-encoder scores those 20 against the question, and the top 5 are kept.
3. **Abstain.** If the best score is below `ABSTAIN_THRESHOLD`, the answer is "I couldn't find this in the indexed documents.", with the 3 closest sources. No LLM is called.
4. **Generate** (`prompts.py`, `generator.py`). Numbered context blocks (at most `CONTEXT_MAX_TOKENS`) go to the LiteLLM chain `primary` → `secondary` → `fallback`, and the answer streams back.
5. **Check citations** (`citations.py`).
   - `[n]` markers that point at a real block become citations.
   - An answer with none gets a "couldn't match" notice.
6. **Save.** Both turns are saved to `messages`.

Without an LLM key the API still starts. Questions it would abstain on are answered normally, and the rest get an SSE `error` event with code `unavailable`.

The embedding and re-ranking models load once at startup (`/ready` reports `models`). The first start downloads them, about 260 MB.
