"""The document manifest, data/sources.yaml (SPEC §3, §8).

Every entry is validated up front, so a typo in the manifest stops the run before
anything is downloaded or indexed.
"""

from collections import Counter
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from app.enums import DocumentCategory


class SourcesError(ValueError):
    """data/sources.yaml is missing, malformed or has an invalid entry."""


class Source(BaseModel):
    """One document in data/sources.yaml."""

    # extra="forbid": a misspelt key (e.g. `catgory`) is an error, not silently ignored.
    model_config = ConfigDict(extra="forbid", frozen=True)

    # Stable id: also the file name in data/raw/ and `documents.source_id` in Postgres.
    id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    title: str = Field(min_length=1)
    # Required: an entry without a url is never indexed (SPEC §8 guardrail).
    url: str = Field(pattern=r"^https://\S+$")
    category: DocumentCategory
    academic_year: str | None = None
    note: str | None = None
    # "manual": never downloaded; read from data/raw/<id>.<ext> (SPEC §8).
    fetch: Literal["manual"] | None = None
    # "ums": a UMS-linked policy (SPEC §3.2). Entries without it come from lpu.in.
    origin: Literal["ums"] | None = None

    @property
    def is_manual(self) -> bool:
        return self.fetch == "manual"

    @property
    def origin_label(self) -> str:
        """The value stored in each chunk's `origin` payload field."""
        return self.origin or "lpu.in"


_SOURCE_LIST = TypeAdapter(list[Source])


def parse_sources(text: str) -> list[Source]:
    """Validate the YAML text of a manifest."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise SourcesError(f"invalid YAML: {error}") from error
    if not isinstance(data, list):
        raise SourcesError("the manifest must be a YAML list of entries")
    try:
        sources = _SOURCE_LIST.validate_python(data)
    except ValidationError as error:
        raise SourcesError(str(error)) from error

    duplicates = sorted(sid for sid, count in Counter(s.id for s in sources).items() if count > 1)
    if duplicates:
        raise SourcesError(f"duplicate ids: {', '.join(duplicates)}")
    return sources


def load_sources(path: Path) -> list[Source]:
    """Read and validate data/sources.yaml."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise SourcesError(f"cannot read {path}: {error}") from error
    return parse_sources(text)
