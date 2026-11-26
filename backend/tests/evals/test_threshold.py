"""Sweeping the abstention threshold τ over best re-rank scores."""

from app.evals.golden import CaseType, Evidence, GoldenCase
from app.evals.threshold import ThresholdRow, abstains, choose, sweep


def case(id: str, answerable: bool) -> GoldenCase:
    return GoldenCase(
        id=id,
        type=CaseType.ANSWERABLE if answerable else CaseType.UNANSWERABLE,
        category="other",
        question="q?",
        reference_answer="a",
        relevant=(Evidence(source_id="doc"),) if answerable else (),
    )


CASES = [case("a1", True), case("a2", True), case("u1", False), case("u2", False)]
SCORES = {"a1": 4.0, "a2": 0.5, "u1": -6.0, "u2": 1.0}


def test_abstains_below_threshold_or_without_candidates() -> None:
    assert abstains(-1.0, 0.0)
    assert not abstains(0.0, 0.0)
    assert abstains(None, -100.0)


def test_sweep() -> None:
    rows = sweep(CASES, SCORES, thresholds=[0.0, 2.0, -7.0])
    assert [r.threshold for r in rows] == [-7.0, 0.0, 2.0]
    assert rows[0] == ThresholdRow(-7.0, unanswerable_abstained=0.0, false_abstains=0.0)
    assert rows[1] == ThresholdRow(0.0, unanswerable_abstained=0.5, false_abstains=0.0)
    assert rows[2] == ThresholdRow(2.0, unanswerable_abstained=1.0, false_abstains=0.5)


def test_sweep_ignores_unscored_cases() -> None:
    rows = sweep([*CASES, case("a3", True)], SCORES, thresholds=[0.0])
    assert rows[0].false_abstains == 0.0


def test_choose_stays_within_the_false_abstain_budget() -> None:
    rows = sweep(CASES, SCORES, thresholds=[-7.0, 0.0, 0.5, 2.0])
    best = choose(rows, max_false_abstains=0.05)
    # 0.0 and 0.5 both catch u1 without false abstains; 2.0 would drop a2.
    assert best is not None and best.threshold == 0.0
    assert choose(rows, max_false_abstains=0.5).threshold == 2.0


def test_choose_returns_none_when_nothing_fits() -> None:
    assert choose([ThresholdRow(1.0, 1.0, 0.5)], max_false_abstains=0.05) is None
