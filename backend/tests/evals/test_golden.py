"""The golden-set schema and loader (SPEC §11.1), and the committed golden set itself."""

import json
from collections import Counter
from pathlib import Path

import pytest

from app.evals.golden import (
    CaseType,
    GoldenSetError,
    Location,
    load_golden_set,
    parse_golden_set,
    unknown_sources,
)
from app.ingest.sources import load_sources
from app.rag.prompts import NOT_FOUND_ANSWER

REPO = Path(__file__).resolve().parents[3]
GOLDEN_SET = REPO / "evals" / "golden_set.jsonl"
SOURCES = REPO / "data" / "sources.yaml"


def line(**overrides) -> str:
    case = {
        "id": "q001",
        "type": "answerable",
        "category": "exams",
        "question": "Can I bring a phone?",
        "reference_answer": "No.",
        "relevant": [{"source_id": "exam-rules", "pages": [2]}],
    }
    case.update(overrides)
    return json.dumps(case)


def test_parses_the_spec_example() -> None:
    [case] = parse_golden_set([line()])
    assert case.type is CaseType.ANSWERABLE
    assert case.answerable
    assert case.relevant[0].pages == (2,)
    assert case.source_ids == {"exam-rules"}


def test_section_and_alternatives() -> None:
    evidence = {
        "source_id": "a",
        "section": "Refunds",
        "alternatives": [{"source_id": "b", "pages": [3]}],
    }
    [case] = parse_golden_set([line(relevant=[evidence])])
    primary, other = case.relevant[0].locations
    assert primary == Location(source_id="a", section="Refunds")
    assert other == Location(source_id="b", pages=(3,))
    assert case.source_ids == {"a", "b"}


def test_blank_lines_are_skipped() -> None:
    assert len(parse_golden_set(["", line(), "  \n"])) == 1


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"type": "unanswerable"}, "no relevant evidence"),
        ({"relevant": []}, "at least one relevant"),
        ({"type": "multi"}, "two or more"),
        ({"question": "   "}, "blank"),
        ({"category": "sports"}, "category"),
        ({"relevant": [{"source_id": "a", "pages": [0]}]}, "pages"),
        ({"extra": 1}, "extra"),
    ],
)
def test_invalid_cases_name_the_line(overrides: dict, message: str) -> None:
    with pytest.raises(GoldenSetError, match=rf"line 2:(.|\n)*{message}"):
        parse_golden_set([line(id="q000"), line(**overrides)])


def test_duplicate_ids_are_rejected() -> None:
    with pytest.raises(GoldenSetError, match="line 2: duplicate id 'q001'"):
        parse_golden_set([line(), line()])


def test_unknown_sources() -> None:
    cases = parse_golden_set([line(), line(id="q002", relevant=[{"source_id": "gone"}])])
    assert unknown_sources(cases, {"exam-rules"}) == {"q002": {"gone"}}


# --- the committed golden set ------------------------------------------------------


@pytest.fixture(scope="module")
def golden():
    return load_golden_set(GOLDEN_SET)


def test_golden_set_has_the_spec_mix(golden) -> None:
    """SPEC §11.1: 40 answerable, 10 multi-part, 10 unanswerable to start."""
    counts = Counter(case.type for case in golden)
    assert counts[CaseType.ANSWERABLE] >= 40
    assert counts[CaseType.MULTI] >= 10
    assert counts[CaseType.UNANSWERABLE] >= 10


def test_golden_set_points_only_at_listed_documents(golden) -> None:
    known = {source.id for source in load_sources(SOURCES)}
    assert unknown_sources(golden, known) == {}


def test_unanswerable_references_are_the_not_found_answer(golden) -> None:
    for case in golden:
        if case.type is CaseType.UNANSWERABLE:
            assert case.reference_answer == NOT_FOUND_ANSWER, case.id
