"""The CI quality gate (SPEC §11.5): compare a retrieval run with `evals/baseline.json`.

The build fails if Hit@5 or MRR@10 drops more than `tolerance` (3 points) below the
baseline. The baseline also records which fixture and golden set it was measured on:
if either file changed, the gate still runs but warns that the baseline may be stale.
Update the baseline only in a pull request that explains why (`--write-baseline`).
"""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from app.evals.metrics import Summary

GATED_METRICS = ("hit_at_5", "mrr_at_10")
DEFAULT_TOLERANCE = 0.03


class Metrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hit_at_5: float = Field(ge=0, le=1)
    recall_at_5: float = Field(ge=0, le=1)
    mrr_at_10: float = Field(ge=0, le=1)


class Baseline(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config: str  # the retrieval configuration the numbers belong to
    questions: int = Field(ge=1)
    metrics: Metrics
    tolerance: float = Field(default=DEFAULT_TOLERANCE, ge=0, le=1)
    fixture_sha256: str
    golden_set_sha256: str
    note: str = ""


def load_baseline(path: Path) -> Baseline:
    return Baseline.model_validate_json(path.read_text(encoding="utf-8"))


def write_baseline(path: Path, baseline: Baseline) -> None:
    path.write_text(baseline.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n")


def make_baseline(
    config: str,
    summary: Summary,
    *,
    fixture_sha256: str,
    golden_set_sha256: str,
    tolerance: float = DEFAULT_TOLERANCE,
    note: str = "",
) -> Baseline:
    values = summary.as_dict()
    return Baseline(
        config=config,
        questions=summary.questions,
        metrics=Metrics(
            hit_at_5=values["hit_at_5"],
            recall_at_5=values["recall_at_5"],
            mrr_at_10=values["mrr_at_10"],
        ),
        tolerance=tolerance,
        fixture_sha256=fixture_sha256,
        golden_set_sha256=golden_set_sha256,
        note=note,
    )


def regressions(summary: Summary, baseline: Baseline) -> list[str]:
    """One message per gated metric that fell more than the tolerance; empty = pass."""
    current = summary.as_dict()
    failures = []
    for name in GATED_METRICS:
        floor = getattr(baseline.metrics, name) - baseline.tolerance
        value = float(current[name])
        if value < floor - 1e-9:
            failures.append(
                f"{name} {value:.3f} is below the baseline {getattr(baseline.metrics, name):.3f}"
                f" minus {baseline.tolerance:.2f} (floor {floor:.3f})"
            )
    return failures


def staleness(
    baseline: Baseline, *, config: str, fixture_sha256: str, golden_set_sha256: str
) -> list[str]:
    """Warnings when the baseline was measured on something else than this run."""
    warnings = []
    if baseline.config != config:
        warnings.append(f"baseline config is {baseline.config!r}, this run is {config!r}")
    if baseline.fixture_sha256 != fixture_sha256:
        warnings.append("evals/fixtures/chunks.jsonl changed since the baseline was written")
    if baseline.golden_set_sha256 != golden_set_sha256:
        warnings.append("evals/golden_set.jsonl changed since the baseline was written")
    return warnings
