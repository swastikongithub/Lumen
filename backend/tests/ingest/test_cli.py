import pytest
import typer
from typer.testing import CliRunner

from app.enums import DocumentCategory
from app.ingest.cli import app, select_sources
from app.ingest.sources import Source

SOURCES = [
    Source(id=sid, title=sid, url=f"https://x.in/{sid}.pdf", category=DocumentCategory.EXAMS)
    for sid in ("exam-rules", "hostel-rules", "fee-schedule")
]


def test_all_selects_every_source() -> None:
    assert select_sources(SOURCES, all_sources=True, ids=[]) == SOURCES


def test_ids_select_in_manifest_order() -> None:
    selected = select_sources(SOURCES, all_sources=False, ids=["fee-schedule", "exam-rules"])

    assert [s.id for s in selected] == ["exam-rules", "fee-schedule"]


@pytest.mark.parametrize(
    ("all_sources", "ids", "message"),
    [
        (False, [], "either --all or"),
        (True, ["exam-rules"], "either --all or"),
        (False, ["exam-rule"], "not in sources.yaml: exam-rule"),
    ],
)
def test_bad_selections_are_rejected(all_sources: bool, ids: list[str], message: str) -> None:
    with pytest.raises(typer.BadParameter, match=message):
        select_sources(SOURCES, all_sources=all_sources, ids=ids)


def test_help_lists_the_commands() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "ingest" in result.output and "stats" in result.output
