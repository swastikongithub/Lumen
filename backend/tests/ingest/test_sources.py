import pytest

from app.config import REPO_ROOT
from app.enums import DocumentCategory
from app.ingest.sources import SourcesError, load_sources, parse_sources

VALID = """
- id: exam-policy
  title: "Examination Policy"
  url: "https://www.lpu.in/exam.pdf"
  category: exams
  academic_year: "2026-27"
  note: "Linked from the exams page"
- id: dress-code
  title: "Dress Code"
  url: "https://ums.lpu.in/dress.zip"
  category: other
  origin: ums
  fetch: manual
"""


def test_valid_manifest_parses() -> None:
    first, second = parse_sources(VALID)

    assert first.id == "exam-policy"
    assert first.category is DocumentCategory.EXAMS
    assert first.academic_year == "2026-27"
    assert (first.is_manual, first.origin_label) == (False, "lpu.in")
    assert (second.is_manual, second.origin_label) == (True, "ums")


def test_the_real_manifest_is_valid() -> None:
    """data/sources.yaml in the repo always loads: a broken manifest fails CI."""
    sources = load_sources(REPO_ROOT / "data" / "sources.yaml")

    assert len(sources) >= 15


@pytest.mark.parametrize(
    ("entry", "message"),
    [
        ("{id: a, title: A, category: exams}", "url"),
        ('{id: a, title: A, url: "http://x.in/a.pdf", category: exams}', "url"),
        ('{id: a, title: A, url: "https://x.in/a.pdf", category: sports}', "category"),
        ('{id: A_1, title: A, url: "https://x.in/a.pdf", category: exams}', "id"),
        ('{id: a, title: A, url: "https://x.in/a.pdf", category: exams, catgory: x}', "catgory"),
        ('{id: a, title: A, url: "https://x.in/a.pdf", category: exams, fetch: auto}', "fetch"),
        ('{id: a, title: A, url: "https://x.in/a.pdf", category: exams, origin: web}', "origin"),
    ],
)
def test_invalid_entries_are_rejected(entry: str, message: str) -> None:
    with pytest.raises(SourcesError, match=message):
        parse_sources(f"- {entry}\n")


def test_duplicate_ids_are_rejected() -> None:
    entry = '- {id: a, title: A, url: "https://x.in/a.pdf", category: exams}\n'

    with pytest.raises(SourcesError, match="duplicate ids: a"):
        parse_sources(entry * 2)


def test_manifest_must_be_a_list() -> None:
    with pytest.raises(SourcesError, match="list"):
        parse_sources("id: a\n")
