# Evals

How Lumen is measured (SPEC §11). Everything runs from `backend/` with `uv run`, so the
scripts use the backend's settings (`backend/.env`) and models.

| File | What it is |
|---|---|
| `golden_set.jsonl` | The questions, with where in the documents the answer is |
| `retrieval_eval.py` | Hit@5, Recall@5, MRR@10 for the production retrieval setup; the CI gate |
| `ablations.py` | The same metrics for every config in SPEC §11.3, chunk sizes, and the τ sweep → `reports/ablation.md` |
| `answer_eval.py` | The full pipeline with the real LLMs: abstention, citation validity, RAGAS → `reports/answer_eval.md` |
| `export_fixtures.py` | Writes `fixtures/chunks.jsonl`, the frozen corpus the CI gate runs on |
| `baseline.json` | The numbers the CI gate compares against |

The logic lives in `backend/app/evals/`; these scripts only parse arguments and print.

## Commands

```bash
cd backend

# Retrieval (no LLM, a minute or two)
uv run python ../evals/retrieval_eval.py
uv run python ../evals/ablations.py
uv run python ../evals/ablations.py --chunk-sizes 256 384 512 --build   # slow the first time

# The CI gate, locally
uv run python ../evals/retrieval_eval.py --fixture ../evals/fixtures/chunks.jsonl --check

# Answers (uses Groq and Gemini free-tier quota; needs keys in backend/.env)
uv run python ../evals/answer_eval.py --no-ragas    # abstention + citations only
uv run python ../evals/answer_eval.py               # + RAGAS with the Gemini judge
```

## The golden set

One JSON object per line:

```json
{"id": "q023", "type": "answerable", "category": "exams",
 "question": "I'm going to be 40 minutes late for my exam, will they still let me in?",
 "reference_answer": "...written from the document...",
 "relevant": [{"source_id": "end-term-exam-instructions", "pages": [4],
               "alternatives": [{"source_id": "reappear-exam-instructions", "pages": [4]}]}]}
```

- `type`: `answerable` (one piece of evidence), `multi` (two or more), `unanswerable`
  (the documents don't cover it; `relevant` is empty and `reference_answer` is Lumen's
  "not found" sentence).
- Each `relevant` entry is one piece of evidence. `source_id` is the id from
  `data/sources.yaml`. A retrieved chunk supports it when it is from that document and:
  - its page range overlaps one of `pages` (if given), and
  - one of its headings contains `section` (if given; used for web pages, which have no
    pages, and to tell two pieces of evidence on one page apart).
- `alternatives` lists other places with the same text (the corpus repeats some
  documents, such as the end-term, reappear and summer-term exam instructions).

Labels use pages and headings, not chunk ids, so the same set works for every chunk size.

**Status:** the first 60 questions were drafted by the assistant from the indexed
documents, and each label was checked against the chunk text. Because they were written
while reading the chunks, they share more words with the documents than real student
questions do, so the retrieval numbers are optimistic. Replace or extend them with real
questions (and every thumbs-down with reason `wrong` or `not_found` from production,
SPEC §11.1), then update the baseline.

Adding a question: append a line with the next id, run
`uv run pytest tests/evals/test_golden.py` (it checks the schema and that every
`source_id` exists), then re-run the evals.

## The CI gate

The `retrieval-eval` job in `.github/workflows/ci.yml` starts Qdrant, loads
`fixtures/chunks.jsonl` (chunk text, payload and both vectors, so no Docling and no chunk
embedding in CI), runs `retrieval_eval.py --check`, and fails if Hit@5 or MRR@10 is more
than 3 points below `baseline.json`.

- The fixture holds the public `lpu.in` documents only, because it is committed to a
  public repository and UMS-linked documents are not public pages. Questions whose
  evidence is not in the fixture are skipped by the gate (the script prints how many
  were scored).
- The gate scores the production setup: hybrid RRF + the configured re-ranker.
- Update the baseline only in a pull request that says why:

```bash
uv run python ../evals/export_fixtures.py          # if the corpus changed
uv run python ../evals/retrieval_eval.py --fixture ../evals/fixtures/chunks.jsonl \
    --write-baseline --note "why"
```

## Answer eval notes

- The judge is Gemini Flash through LiteLLM (`--judge-model`, default
  `LLM_FALLBACK_MODEL`). The answers come from the production chain, Groq first, so a
  different provider judges them. Without a Groq key, Gemini both answers and judges;
  the report names the models used.
- RAGAS metrics: faithfulness (claims supported by the context), response relevancy,
  context precision and context recall (both against `reference_answer`). Response
  relevancy embeds with the app's own FastEmbed model, so it uses no embedding quota.
- Calls are throttled (`--judge-rpm`, default 8 a minute) for the free tier. A full run
  makes roughly 10 judge calls per answered question.
