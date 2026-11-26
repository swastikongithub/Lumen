"""The golden set (SPEC §11.1): `evals/golden_set.jsonl`, one question per line.

    {"id": "q001", "type": "answerable", "category": "exams",
     "question": "...", "reference_answer": "...",
     "relevant": [{"source_id": "exam-policy", "pages": [12]}]}

`type` is `answerable` (one document), `multi` (needs two or more pieces of evidence)
or `unanswerable` (the documents don't cover it, so Lumen should abstain).

Each entry in `relevant` is one piece of evidence the answer needs. It is labelled by
document and page, not by chunk ID, so the same labels work for every chunk size:
- `pages`: the evidence is on one of these pages;
- `section`: for documents without pages (web pages), or to tell two pieces of
  evidence on the same page apart: a heading the chunk sits under must contain it;
- `alternatives`: other places that hold the same text (the corpus has a few
  near-identical documents, e.g. the end-term and reappear exam instructions).
Without `pages` or `section`, any chunk of the document counts.
"""

from collections.abc import Collection, Iterable
from enum import StrEnum
from pathlib import Path
from typing import Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PositiveInt,
    ValidationError,
    field_validator,
    model_validator,
)

from app.enums import DocumentCategory


class GoldenSetError(ValueError):
    """The golden set file is malformed; the message names the line."""


class CaseType(StrEnum):
    ANSWERABLE = "answerable"
    MULTI = "multi"
    UNANSWERABLE = "unanswerable"


class Location(BaseModel):
    """Where a piece of evidence is: a document, optionally narrowed by page or heading."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str = Field(min_length=1)
    pages: tuple[PositiveInt, ...] = ()
    section: str | None = Field(default=None, min_length=1)


class Evidence(Location):
    """One piece of evidence an answer needs, and other places holding the same text."""

    alternatives: tuple[Location, ...] = ()

    @property
    def locations(self) -> tuple[Location, ...]:
        primary = Location(source_id=self.source_id, pages=self.pages, section=self.section)
        return (primary, *self.alternatives)


class GoldenCase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    type: CaseType
    category: DocumentCategory
    question: str = Field(min_length=1)
    reference_answer: str = Field(min_length=1)
    relevant: tuple[Evidence, ...] = ()

    @field_validator("question", "reference_answer")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    @model_validator(mode="after")
    def evidence_matches_type(self) -> Self:
        if self.type is CaseType.UNANSWERABLE and self.relevant:
            raise ValueError("unanswerable questions have no relevant evidence")
        if self.type is CaseType.ANSWERABLE and not self.relevant:
            raise ValueError("answerable questions need at least one relevant entry")
        if self.type is CaseType.MULTI and len(self.relevant) < 2:
            raise ValueError("multi questions need two or more relevant entries")
        return self

    @property
    def answerable(self) -> bool:
        return self.type is not CaseType.UNANSWERABLE

    @property
    def source_ids(self) -> set[str]:
        """Every document this case's evidence points to, alternatives included."""
        return {loc.source_id for evidence in self.relevant for loc in evidence.locations}


def parse_golden_set(lines: Iterable[str]) -> list[GoldenCase]:
    """Parse JSONL text. Blank lines are skipped; errors name the line number."""
    cases: list[GoldenCase] = []
    seen: set[str] = set()
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            case = GoldenCase.model_validate_json(line)
        except ValidationError as error:
            raise GoldenSetError(f"line {number}: {error}") from error
        if case.id in seen:
            raise GoldenSetError(f"line {number}: duplicate id {case.id!r}")
        seen.add(case.id)
        cases.append(case)
    return cases


def load_golden_set(path: Path) -> list[GoldenCase]:
    with path.open(encoding="utf-8") as file:
        return parse_golden_set(file)


def unknown_sources(cases: Iterable[GoldenCase], known: Collection[str]) -> dict[str, set[str]]:
    """Case id -> source ids it references that are not in `known` (sources.yaml)."""
    missing = {case.id: case.source_ids - set(known) for case in cases}
    return {case_id: ids for case_id, ids in missing.items() if ids}
