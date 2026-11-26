# CLAUDE.md — Lumen

Lumen is a cited Q&A assistant for LPU students, built as a production-grade RAG app: hybrid retrieval, re-ranking, abstention, evaluation with a CI quality gate, a SvelteKit web app, and an Android app on Google Play built from the same SvelteKit code with Capacitor.

## Sources of truth
- `docs/SPEC.md`: architecture, stack, data model, API, evals, build plan (§14) and per-phase prompts (§18).
- `docs/DESIGN.md` + `design/mockups/`: the approved UI. Match them for anything visual. DESIGN.md §7 covers the Android-only screens.
- `docs/PLAY_STORE.md`: Google Play requirements, release checklist and listing drafts.
- If the code and the spec disagree, stop and ask. Don't silently change the spec.

## Hard rules
1. **No TypeScript anywhere.** No `.ts`/`.tsx` files, no `tsconfig.json`, no `lang="ts"` in Svelte. Plain JavaScript only (JSDoc comments are fine). Python on the backend.
2. **No LangChain or LlamaIndex** in the retrieval/generation pipeline. Write it by hand. LiteLLM is only for provider calls; Docling only for parsing.
3. **Docling lives only in the `ingest` dependency group.** It must never end up in the API Docker image.
4. **Never invent numbers.** README, reports and CV text get measured metric values or clear `[placeholder]`s, nothing made up.
5. **Index only documents listed in `data/sources.yaml`**: lpu.in documents, plus general student policies that UMS links to (`origin: ums`, added at the owner's direction; SPEC §3.2). No personal data: never a student's own UMS pages, result lists or case records. Lumen itself never logs in anywhere.
6. Never commit `.env`, API keys or `data/raw/`. Keep `.env.example` up to date when adding a setting.
7. No Tailwind. Svelte scoped CSS + the CSS variables in `docs/DESIGN.md`.
8. **Android = Capacitor, configured with `capacitor.config.json`** (never `capacitor.config.ts`). The Java/Kotlin/Gradle files that Capacitor generates in `frontend/android/` are fine; write native code there only if a plugin can't do the job, and ask first.
9. **One codebase for web and app.** Components never import Capacitor directly: every device capability goes through `src/lib/platform.js`, with a web fallback, so the web app keeps working.
10. **Never create, commit or print signing keys.** No `*.jks`, `*.keystore`, `keystore.properties` or passwords in the repo.
11. Keep `CapacitorHttp` disabled (it breaks SSE streaming) and never ship `server.url` in the Capacitor config.
12. All public API routes live under `/api/v1`. Sessions use the `X-Session-Id` header, never cookies. Don't make breaking changes to v1 once the app is on Play.
13. The thumbs-down reason "Offensive or harmful" must always exist (Google Play AI-content policy).

## How to work
- Build **one phase at a time** (SPEC §14). Stop at the end of each phase and give me: what was built, how to run it, what's left, and anything I must do by hand (accounts, keys, documents).
- Write tests with the code. A phase is done only when lint and tests pass.
- Prefer small, readable modules over clever abstractions. This code will be explained in interviews.
- At the end of a phase, propose a commit message. Commit only when I say so.
- Keep scripts cross-platform (Windows and macOS/Linux): use Python scripts or `uv run` commands instead of bash-only scripts.
- Ask before adding a dependency the spec doesn't list.

## Conventions
**Backend (Python 3.12):** FastAPI, Pydantic v2, pydantic-settings (all config from env), SQLAlchemy 2.0 async + asyncpg, Alembic migrations, type hints everywhere, `logging` not `print`, Ruff for lint and format, pytest + pytest-asyncio + httpx.

**Frontend:** SvelteKit with Svelte 5 runes (`$state`, `$derived`, `$props`), plain JS, `adapter-static` in SPA mode, components in `src/lib/components/`, API and SSE parsing in `src/lib/api.js`, session headers in `src/lib/session.js`, device features in `src/lib/platform.js`, markdown via `marked` + `DOMPurify`.

**Android:** package ID `fun.swastik.lumen`, target SDK 36, release builds as signed `.aab`, official `@capacitor/*` plugins only unless I approve another.

## Commands (update this section as they become real)
```bash
# infrastructure (Qdrant + Postgres)
docker compose up -d

# backend
cd backend
uv sync --all-groups
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
uv run pytest
uv run ruff check . && uv run ruff format --check .

# ingestion and evals
uv run lumen ingest --all          # or --id <source-id>; --force re-chunks; --offline uses data/raw only
uv run lumen stats
uv run python ../evals/retrieval_eval.py                       # Hit@5, Recall@5, MRR@10
uv run python ../evals/retrieval_eval.py --fixture ../evals/fixtures/chunks.jsonl --check   # CI gate
uv run python ../evals/ablations.py --chunk-sizes 256 384 512 --build   # reports/ablation.md
uv run python ../evals/answer_eval.py             # needs LLM keys; --no-ragas skips the judge
uv run python ../evals/export_fixtures.py         # refresh the CI fixture after re-ingesting
uv run ruff check . ../evals && uv run ruff format --check . ../evals

# frontend
cd frontend
npm install
npm run dev

# android (from frontend/)
npm run build && npx cap sync android
npx cap run android        # device or emulator
npx cap open android       # Android Studio, for signed release bundles
```
