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

What happens to a question (`app/api/chat.py`, `app/rag/`):

1. **Rate limit** (`app/api/rate_limit.py`).
   - Each session (`X-Session-Id`) may ask `RATE_LIMIT_SESSION` (10/minute;100/day), and each network `RATE_LIMIT_IP` (60/minute;1000/day).
   - Over a limit the answer is 429 with `{"code": "too_many_requests", "retry_after": N}` and `Retry-After`, and nothing is saved.
   - The IP key is an HMAC of the address with a random salt made at startup, so raw IPs are never stored. IPv6 addresses count per /64 network.
2. **Rewrite** (`rewrite.py`). A follow-up in an existing conversation goes to the LLM with the last `REWRITE_HISTORY_TURNS` messages and becomes a standalone question. Every later step (cache, retrieval, the answer prompt) uses the rewrite, because the answer prompt carries no history. A new conversation skips this step, and so does a failed rewrite.
3. **Cache** (`cache.py`).
   - The question is looked up in the `answer_cache` Qdrant collection.
   - A hit has cosine similarity ≥ `CACHE_THRESHOLD`, with the same category filter and the current `corpus_version`, so re-ingesting invalidates every cached answer.
   - A hit is streamed back without calling the LLM.
4. **Retrieve** (`retriever.py`). One Qdrant query runs a dense search (bge-small) and a BM25 search. RRF fuses them into the top 20, with an optional `category` filter.
5. **Re-rank** (`reranker.py`). A cross-encoder scores those 20 against the question, and the top 5 are kept.
6. **Abstain.** If the best score is below `ABSTAIN_THRESHOLD`, the answer is "I couldn't find this in the indexed documents.", with the 3 closest sources. No LLM is called.
7. **Generate** (`prompts.py`, `generator.py`). Numbered context blocks (at most `CONTEXT_MAX_TOKENS`) go to the LiteLLM chain `primary` → `secondary` → `fallback`, and the answer streams back.
8. **Check citations** (`citations.py`).
   - `[n]` markers that point at a real block become citations.
   - An answer with none gets a "couldn't match" notice.
9. **Store.** An answer with citations goes into the cache. Abstentions and unverified answers never do.
10. **Save.** Both turns are saved to `messages`, with the rewrite, `cache_hit` and the Langfuse trace ID.

Without an LLM key the API still starts. Questions it would abstain on are answered normally, and the rest get an SSE `error` event with code `unavailable`.

The embedding and re-ranking models load once at startup (`/ready` reports `models`). The first start downloads them, about 260 MB.

## Tracing, stats and retention (SPEC §9, §10, §13)

**Langfuse tracing** (`app/observability.py`) is optional. Set `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` (and `LANGFUSE_BASE_URL` for the US region or a self-hosted instance).

- Each question is one trace named `chat`, with the spans `rewrite`, `cache-lookup`, `retrieve`, `rerank`, `generate` and `cache-store`.
- LiteLLM's `langfuse_otel` callback adds the model call (model, tokens, cost) under `generate`.
- Traces are grouped by conversation ID. The session ID and IP are never sent.
- Without the keys nothing is sent and the API runs as before.

**Usage numbers.** Set `ADMIN_API_KEY` (any long random string) and ask:

```bash
uv run python -c "import secrets; print(secrets.token_urlsafe(32))"   # a key for .env
curl -H "X-Admin-Key: $ADMIN_API_KEY" "http://localhost:8000/admin/stats?days=7"
```

- The answer covers the last 1–30 days: questions per day, abstain and cache-hit rates, thumbs up/down and the thumbs-down rate, and p50/p95 latency and time to first token.
- The key is compared in constant time.
- Without `ADMIN_API_KEY` the endpoint answers 404, and it isn't in the OpenAPI document.

**Retention** (`app/db/retention.py`). The API deletes messages (with their feedback), emptied conversations and cache entries older than `RETENTION_DAYS` (30). It runs a minute after startup and then every `RETENTION_CHECK_HOURS`. This is what the `/privacy` page promises.
