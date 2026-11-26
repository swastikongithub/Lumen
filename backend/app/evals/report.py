"""Markdown for the eval reports (`evals/reports/*.md`) and the terminal."""

from collections.abc import Sequence

from app.evals.metrics import Summary, percentile
from app.evals.retrieval import RunResult
from app.evals.threshold import ThresholdRow


def table(headers: Sequence[str], rows: Sequence[Sequence[object]]) -> str:
    def cell(value: object) -> str:
        return str(value).replace("|", "\\|")

    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
        *("| " + " | ".join(cell(v) for v in row) + " |" for row in rows),
    ]
    return "\n".join(lines)


def num(value: float) -> str:
    return f"{value:.3f}"


def ms(seconds: float) -> str:
    return f"{seconds * 1000:.0f}"


def pct(value: float) -> str:
    return f"{value:.0%}"


def metrics_row(name: str, summary: Summary) -> list[str]:
    return [name, num(summary.hit_at_5), num(summary.recall_at_5), num(summary.mrr_at_10)]


def runs_table(runs: Sequence[RunResult]) -> str:
    """One row per configuration: quality, then retrieval and re-rank latency."""
    rows = []
    for run in runs:
        rerank = run.rerank_seconds
        rows.append(
            [
                *metrics_row(run.config.name, run.summary),
                ms(percentile(run.retrieve_seconds, 50)),
                ms(percentile(rerank, 50)) if rerank else "-",
                ms(percentile(rerank, 95)) if rerank else "-",
            ]
        )
    headers = [
        "Config",
        "Hit@5",
        "Recall@5",
        "MRR@10",
        "Retrieve p50 (ms)",
        "Re-rank p50 (ms)",
        "Re-rank p95 (ms)",
    ]
    return table(headers, rows)


def by_type_table(summary: Summary) -> str:
    rows = [
        [name, sub.questions, num(sub.hit_at_5), num(sub.recall_at_5), num(sub.mrr_at_10)]
        for name, sub in summary.by_type.items()
    ]
    return table(["Question type", "Questions", "Hit@5", "Recall@5", "MRR@10"], rows)


def threshold_table(rows: Sequence[ThresholdRow], chosen: ThresholdRow | None) -> str:
    body = [
        [
            f"{row.threshold:+.1f}" + (" ←" if chosen is not None and row == chosen else ""),
            pct(row.unanswerable_abstained),
            pct(row.false_abstains),
        ]
        for row in rows
    ]
    return table(["τ", "Unanswerable that abstain", "Answerable that abstain (false)"], body)


def misses(run: RunResult) -> list[str]:
    """Question ids with no relevant chunk in the top 5."""
    return [score.case_id for score in run.scores if score.hit_at_5 == 0.0]
