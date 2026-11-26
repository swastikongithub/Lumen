"""The command-line scripts in evals/: argument handling and report writing."""

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

from app.evals.answers import AnswerRecord
from app.evals.golden import CaseType, load_golden_set
from app.evals.metrics import CaseScore
from app.evals.retrieval import Mode, RetrievalConfig, RunResult

EVALS = Path(__file__).resolve().parents[3] / "evals"


def load_script(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"evals_{name}", EVALS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def test_gate_needs_the_fixture(capsys: pytest.CaptureFixture[str]) -> None:
    script = load_script("retrieval_eval")
    assert await script.run(script.parse_args(["--check"])) == 2
    assert "need --fixture" in capsys.readouterr().err


def test_check_and_write_baseline_are_exclusive() -> None:
    script = load_script("retrieval_eval")
    with pytest.raises(SystemExit):
        script.parse_args(["--check", "--write-baseline"])


def record(case_id: str, answerable: bool, abstained: bool, ragas=None) -> AnswerRecord:
    return AnswerRecord(
        case_id=case_id,
        answerable=answerable,
        question="q?",
        answer="" if abstained else "Yes [1].",
        abstained=abstained,
        markers=[] if abstained else [1],
        context_blocks=0 if abstained else 2,
        contexts=[] if abstained else ["text"],
        best_score=1.0,
        model=None if abstained else "groq/openai/gpt-oss-120b",
        tokens_out=None if abstained else 40,
        seconds=2.0,
        ragas=ragas or {},
    )


def test_answer_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    script = load_script("answer_eval")
    monkeypatch.setattr(script, "REPORTS", tmp_path)
    records = [
        record("q001", True, False, {"faithfulness": 0.9}),
        record("q051", False, True),
    ]
    settings = script.get_settings()
    path = script.write_report(settings, [], records, "gemini/gemini-3.5-flash")
    text = path.read_text(encoding="utf-8")
    assert "| Unanswerable questions that abstained | 100% |" in text
    assert "| [n] markers pointing to a real context block | 100% |" in text
    assert "| faithfulness | 0.900 | 1 |" in text
    saved = json.loads((tmp_path / "answer_eval.json").read_text(encoding="utf-8"))
    assert [r["case_id"] for r in saved["records"]] == ["q001", "q051"]


def run(name: str, hit: float, mrr: float, rerank: list[float] | None = None) -> RunResult:
    scores = [CaseScore("q001", CaseType.ANSWERABLE, "exams", hit, hit, mrr, 1)]
    config = RetrievalConfig(name, Mode.HYBRID, reranker="m" if rerank else None)
    return RunResult(config, scores, {"q001": 2.0, "q051": -5.0}, [0.05], rerank or [])


def test_best_run_prefers_quality_then_speed() -> None:
    script = load_script("ablations")
    slow = run("slow", 1.0, 0.9, rerank=[3.0])
    fast = run("fast", 1.0, 0.9, rerank=[1.0])
    weaker = run("weaker", 0.9, 1.0)
    assert script.best_run([slow, weaker, fast]).config.name == "fast"


def test_ablation_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    script = load_script("ablations")
    monkeypatch.setattr(script, "REPORTS", tmp_path)
    monkeypatch.setattr(script, "collection_stats", lambda settings, collection: (100, 5))
    cases = load_golden_set(EVALS / "golden_set.jsonl")
    settings = script.get_settings()
    runs = [run("Hybrid (RRF)", 0.8, 0.6), run("Hybrid + L-12", 1.0, 0.9, rerank=[2.0])]
    script.write_report(settings, cases, runs, {256: runs[1]}, {256: 120})
    text = (tmp_path / "ablation.md").read_text(encoding="utf-8")
    assert "Best: **Hybrid + L-12**" in text
    assert "| 256 tokens | 120 | 1.000 | 1.000 | 0.900 |" in text
    assert "## Abstention threshold τ" in text
    data = json.loads((tmp_path / "ablation.json").read_text(encoding="utf-8"))
    assert data["best"] == "Hybrid + L-12"
    assert data["configs"][1]["rerank_p50_ms"] == 2000.0
