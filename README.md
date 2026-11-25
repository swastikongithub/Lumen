# lumen

Cited answers to LPU student questions, from public university documents only. Production RAG project: hybrid search, re-ranking, abstention, evaluation suite with a CI quality gate, a SvelteKit web app, and an Android app on Google Play (Capacitor).

> Unofficial student project, not affiliated with Lovely Professional University.

**Status:** starter. The code is built phase by phase with Claude Code from `docs/SPEC.md`.

## What's in this starter
| Path | What it is |
|---|---|
| `CLAUDE.md` | Standing rules Claude Code reads automatically |
| `docs/SPEC.md` | Full project spec, build plan and per-phase prompts |
| `docs/DESIGN.md` | Design tokens, components, states, responsive rules, Android screens |
| `docs/PLAY_STORE.md` | Google Play requirements, release checklist, listing drafts |
| `store/` | Where the final Play listing text and graphics go |
| `design/mockups/` | Approved UI mockups (reference only) |
| `design/brand/` | Logo mark SVGs |
| `data/sources.example.yaml` | Template for the document list. Copy it to `sources.yaml` and add real public links |

## Before you start
- Git, Python 3.12, [uv](https://docs.astral.sh/uv/), Node.js 20+ (LTS), Docker Desktop
- Accounts, needed only from Phase 2 onwards: Groq, Google AI Studio (Gemini), Langfuse. For deployment (Phase 6): Qdrant Cloud, Neon, Google Cloud (Cloud Run), Cloudflare Pages.
- For the Android app (Phases 7–8): Android Studio (its bundled JDK is enough), an Android phone with USB debugging, and a Google Play Console personal account (one-time fee and identity verification, so create it early). Google Play needs 12+ testers for a 14-day closed test before production, so line up classmates in advance.

## Getting started
```bash
cd lumen
git init
claude          # start Claude Code in this folder, then paste the starting prompt
```

This README gets replaced by the full project README in Phase 6 (SPEC §16).
