"""Answer eval (SPEC §11.2): the full pipeline on the golden set, judged by RAGAS.

Calls the real LLM chain for every question, so it uses free-tier quota: run it by hand
or weekly, not on every pull request. Needs GROQ_API_KEY and/or GEMINI_API_KEY (the judge
needs GEMINI_API_KEY) in backend/.env and the eval dependency group. From backend/:

    uv run python ../evals/answer_eval.py                     # all questions + RAGAS
    uv run python ../evals/answer_eval.py --no-ragas          # abstention + citations only
    uv run python ../evals/answer_eval.py --only q001 q051 --judge-rpm 5

Writes evals/reports/answer_eval.md and answer_eval.json (answers included, for review).
"""

import argparse
import asyncio
import json
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from app.config import REPO_ROOT, Settings, get_settings
from app.evals.answers import (
    RAGAS_METRICS,
    AnswerRecord,
    abstention_stats,
    citation_stats,
    generate_answers,
    ragas_means,
    score_with_ragas,
)
from app.evals.golden import GoldenCase, load_golden_set
from app.evals.metrics import percentile
from app.evals.report import num, pct, table
from app.evals.runtime import async_client, setup_logging
from app.rag.generator import model_list
from app.rag.pipeline import build_pipeline

REPORTS = REPO_ROOT / "evals" / "reports"


def write_report(
    settings: Settings,
    cases: list[GoldenCase],
    records: list[AnswerRecord],
    judge: str | None,
) -> Path:
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    abstain = abstention_stats(records)
    cites = citation_stats(records)
    means = ragas_means(records)
    models = sorted({r.model for r in records if r.model})
    errors = [r for r in records if r.error]
    answered = [r for r in records if r.answered]
    lines = [
        "# Answer evaluation",
        "",
        f"Measured {now} with `evals/answer_eval.py` on {len(records)} golden-set questions.",
        f"Answered by: {', '.join(models) or 'no model (every question abstained or failed)'}. "
        f"Judge: {judge or 'not run (--no-ragas)'}. τ = {settings.abstain_threshold:+.1f}.",
        "",
        "## Abstention (targets: ≥ 90% on unanswerable, ≤ 5% false abstains)",
        "",
        table(
            ["Measure", "Value"],
            [
                ["Unanswerable questions that abstained", pct(abstain.abstain_rate_unanswerable)],
                ["Answerable questions that abstained (false)", pct(abstain.false_abstain_rate)],
                ["Abstentions that were right (precision)", pct(abstain.precision)],
                ["Questions scored", abstain.answerable + abstain.unanswerable],
            ],
        ),
        "",
        "## Citations",
        "",
        table(
            ["Measure", "Value"],
            [
                ["[n] markers pointing to a real context block", pct(cites.validity)],
                ["Answers with at least one valid citation", pct(cites.cited_share)],
                ["Answers checked", cites.answers],
            ],
        ),
        "",
        "## RAGAS (answerable questions Lumen answered; target faithfulness ≥ 0.85)",
        "",
        table(
            ["Metric", "Mean", "Scored"],
            [
                [name, num(means[name]), sum(name in r.ragas for r in records)]
                for name in RAGAS_METRICS
                if name in means
            ],
        )
        if means
        else "Not run.",
        "",
        "## Performance (this run)",
        "",
        table(
            ["Measure", "Value"],
            [
                [
                    "Seconds per question, p50",
                    f"{percentile([r.seconds for r in answered], 50):.1f}",
                ],
                [
                    "Seconds per question, p95",
                    f"{percentile([r.seconds for r in answered], 95):.1f}",
                ],
                [
                    "Output tokens per answer, p50",
                    percentile([float(r.tokens_out or 0) for r in answered], 50),
                ],
            ],
        ),
    ]
    if errors:
        lines += ["", f"Failed: {', '.join(f'{r.case_id} ({r.error})' for r in errors)}."]
    lines.append("")
    REPORTS.mkdir(parents=True, exist_ok=True)
    path = REPORTS / "answer_eval.md"
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    (REPORTS / "answer_eval.json").write_text(
        json.dumps(
            {
                "measured_at": now,
                "judge": judge,
                "abstain_threshold": settings.abstain_threshold,
                "records": [asdict(r) for r in records],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


async def run(args: argparse.Namespace) -> int:
    settings = get_settings()
    if not model_list(settings):
        print("No LLM key: set GROQ_API_KEY and/or GEMINI_API_KEY in backend/.env", file=sys.stderr)
        return 2
    use_ragas = not args.no_ragas
    if use_ragas and settings.gemini_api_key is None:
        print("The judge needs GEMINI_API_KEY (or pass --no-ragas)", file=sys.stderr)
        return 2

    cases = load_golden_set(args.golden)
    if args.only:
        cases = [case for case in cases if case.id in set(args.only)]
    client = async_client(settings)
    try:
        pipeline = build_pipeline(settings, client)
        records = await generate_answers(pipeline, cases, pause_seconds=args.pause)
    finally:
        await client.close()

    judge = None
    if use_ragas:
        from app.evals.ragas_judge import FastEmbedEmbeddings, RagasJudge, judge_completion

        judge = args.judge_model or settings.llm_fallback_model
        assert settings.gemini_api_key is not None
        completion = judge_completion(settings.gemini_api_key.get_secret_value(), args.judge_rpm)
        scorer = RagasJudge(judge, completion, FastEmbedEmbeddings(settings.embed_model))
        records = await score_with_ragas(records, {c.id: c for c in cases}, scorer)

    path = write_report(settings, cases, records, judge)
    print(path.read_text(encoding="utf-8"))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--golden", type=Path, default=REPO_ROOT / "evals/golden_set.jsonl")
    parser.add_argument("--only", nargs="*", help="question ids to run")
    parser.add_argument("--no-ragas", action="store_true", help="skip the LLM judge")
    parser.add_argument("--judge-model", help="LiteLLM model id; default LLM_FALLBACK_MODEL")
    parser.add_argument("--judge-rpm", type=float, default=8.0, help="judge calls per minute")
    parser.add_argument("--pause", type=float, default=2.0, help="seconds between questions")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    setup_logging(args.verbose)
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
