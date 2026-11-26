"""Report tables and shared script setup."""

from app.config import Settings
from app.evals.golden import CaseType, Evidence, GoldenCase, Location
from app.evals.metrics import CaseScore
from app.evals.report import misses, runs_table, table, threshold_table
from app.evals.retrieval import Mode, RetrievalConfig, RunResult
from app.evals.runtime import covered_cases, production_config, short_model_name
from app.evals.threshold import ThresholdRow


def test_table_escapes_pipes() -> None:
    assert table(["A", "B"], [["x|y", 1]]) == "| A | B |\n|---|---|\n| x\\|y | 1 |"


def score(case_id: str, hit: float) -> CaseScore:
    return CaseScore(case_id, CaseType.ANSWERABLE, "exams", hit, hit, hit, 1 if hit else None)


def test_runs_table_and_misses() -> None:
    run = RunResult(
        RetrievalConfig("Hybrid + L-12", Mode.HYBRID, reranker="m"),
        scores=[score("q1", 1.0), score("q2", 0.0)],
        retrieve_seconds=[0.08, 0.1],
        rerank_seconds=[1.0, 3.0],
    )
    plain = RunResult(RetrievalConfig("BM25 only", Mode.BM25), [score("q1", 1.0)], {}, [0.01])
    text = runs_table([run, plain])
    assert "| Hybrid + L-12 | 0.500 | 0.500 | 0.500 | 80 | 1000 | 3000 |" in text
    assert "| BM25 only | 1.000 | 1.000 | 1.000 | 10 | - | - |" in text
    assert misses(run) == ["q2"]


def test_threshold_table_marks_the_choice() -> None:
    rows = [ThresholdRow(-1.0, 0.2, 0.0), ThresholdRow(0.5, 0.6, 0.02)]
    text = threshold_table(rows, rows[1])
    assert "| +0.5 ← | 60% | 2% |" in text
    assert "| -1.0 | 20% | 0% |" in text


def test_production_config_follows_settings() -> None:
    settings = Settings(rerank_model="Xenova/ms-marco-MiniLM-L-6-v2", retrieve_fused_limit=10)
    config = production_config(settings)
    assert config.name == "Hybrid + ms-marco-MiniLM-L-6-v2"
    assert (config.mode, config.reranker, config.candidates) == (
        Mode.HYBRID,
        "Xenova/ms-marco-MiniLM-L-6-v2",
        10,
    )
    assert short_model_name("plain") == "plain"


def test_covered_cases_need_every_piece_of_evidence() -> None:
    def case(id: str, *evidence: Evidence) -> GoldenCase:
        return GoldenCase(
            id=id,
            type=CaseType.MULTI if len(evidence) > 1 else CaseType.ANSWERABLE,
            category="exams",
            question="q?",
            reference_answer="a",
            relevant=evidence,
        )

    public = Evidence(source_id="public")
    private = Evidence(source_id="ums-doc")
    either = Evidence(source_id="ums-doc", alternatives=(Location(source_id="public"),))
    cases = [case("q1", public), case("q2", public, private), case("q3", either)]
    assert [c.id for c in covered_cases(cases, {"public"})] == ["q1", "q3"]
