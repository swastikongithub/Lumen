"""The CI gate: fail on a drop of more than 3 points in Hit@5 or MRR@10 (SPEC §11.5)."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.evals.baseline import (
    Baseline,
    Metrics,
    load_baseline,
    make_baseline,
    regressions,
    staleness,
    write_baseline,
)
from app.evals.metrics import Summary

BASELINE = Baseline(
    config="hybrid+rerank",
    questions=24,
    metrics=Metrics(hit_at_5=0.90, recall_at_5=0.80, mrr_at_10=0.70),
    fixture_sha256="f" * 64,
    golden_set_sha256="g" * 64,
)


def summary(hit: float, mrr: float, recall: float = 0.0) -> Summary:
    return Summary(questions=24, hit_at_5=hit, recall_at_5=recall, mrr_at_10=mrr)


def test_passes_within_the_tolerance() -> None:
    assert regressions(summary(0.87, 0.67), BASELINE) == []  # exactly 3 points lower
    assert regressions(summary(0.95, 0.75), BASELINE) == []


def test_recall_is_reported_but_not_gated() -> None:
    assert regressions(summary(0.90, 0.70, recall=0.10), BASELINE) == []


def test_fails_on_a_bigger_drop() -> None:
    failures = regressions(summary(0.86, 0.60), BASELINE)
    assert len(failures) == 2
    assert failures[0].startswith("hit_at_5 0.860 is below the baseline 0.900")
    assert "mrr_at_10 0.600" in failures[1]


def test_staleness_warnings() -> None:
    assert (
        staleness(
            BASELINE, config="hybrid+rerank", fixture_sha256="f" * 64, golden_set_sha256="g" * 64
        )
        == []
    )
    warnings = staleness(BASELINE, config="other", fixture_sha256="x", golden_set_sha256="y")
    assert len(warnings) == 3


def test_round_trip(tmp_path: Path) -> None:
    made = make_baseline(
        "hybrid+rerank",
        summary(0.912345, 0.7, recall=0.8),
        fixture_sha256="f" * 64,
        golden_set_sha256="g" * 64,
        note="first baseline",
    )
    assert made.metrics.hit_at_5 == 0.9123  # rounded to 4 places
    path = tmp_path / "baseline.json"
    write_baseline(path, made)
    assert load_baseline(path) == made


def test_rejects_unknown_fields(tmp_path: Path) -> None:
    path = tmp_path / "baseline.json"
    path.write_text(BASELINE.model_dump_json()[:-1] + ', "surprise": 1}', encoding="utf-8")
    with pytest.raises(ValidationError):
        load_baseline(path)
