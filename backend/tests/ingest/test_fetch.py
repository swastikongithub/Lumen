import hashlib
from pathlib import Path

import pytest

from app.enums import DocumentCategory
from app.ingest.fetch import (
    Fetcher,
    FetchError,
    HttpResponse,
    find_local_file,
    suffix_for,
)
from app.ingest.sources import Source

PDF = b"%PDF-1.7 test document"


def source(url: str = "https://www.lpu.in/docs/policy.pdf", **extra: str) -> Source:
    return Source(id="policy", title="Policy", url=url, category=DocumentCategory.EXAMS, **extra)


class FakeWeb:
    """Serves fixed responses and records every URL requested."""

    def __init__(self, pages: dict[str, HttpResponse]) -> None:
        self.pages = pages
        self.requested: list[str] = []

    def __call__(self, url: str) -> HttpResponse:
        self.requested.append(url)
        if url not in self.pages:
            raise OSError("connection refused")
        return self.pages[url]


def fetcher(tmp_path: Path, web: FakeWeb, **options: object) -> Fetcher:
    return Fetcher(tmp_path, "LumenBot/0.1", web, sleep=lambda _: None, **options)


ROBOTS_OK = HttpResponse(404, b"", "text/html")  # no robots.txt: everything allowed


def test_downloads_saves_by_id_and_hashes(tmp_path: Path) -> None:
    web = FakeWeb(
        {
            "https://www.lpu.in/robots.txt": ROBOTS_OK,
            "https://www.lpu.in/docs/policy.pdf": HttpResponse(200, PDF, "application/pdf"),
        }
    )

    fetched = fetcher(tmp_path, web).get(source())

    assert fetched.path == tmp_path / "policy.pdf"
    assert fetched.path.read_bytes() == PDF
    assert fetched.sha256 == hashlib.sha256(PDF).hexdigest()
    assert fetched.downloaded


def test_web_pages_are_saved_as_html(tmp_path: Path) -> None:
    url = "https://www.lpu.in/academics/calendar.php"
    web = FakeWeb(
        {
            "https://www.lpu.in/robots.txt": ROBOTS_OK,
            url: HttpResponse(200, b"<html>calendar</html>", "text/html"),
        }
    )

    fetched = fetcher(tmp_path, web).get(source(url))

    assert fetched.path.name == "policy.html"


def test_manual_sources_are_never_downloaded(tmp_path: Path) -> None:
    (tmp_path / "policy.pdf").write_bytes(PDF)
    web = FakeWeb({})

    fetched = fetcher(tmp_path, web).get(source(fetch="manual"))

    assert web.requested == []
    assert fetched.path == tmp_path / "policy.pdf"
    assert not fetched.downloaded


def test_missing_manual_file_explains_what_to_do(tmp_path: Path) -> None:
    (tmp_path / "policy.doc").write_bytes(b"legacy")

    with pytest.raises(FetchError, match=r"policy\.doc cannot be parsed"):
        fetcher(tmp_path, FakeWeb({})).get(source(fetch="manual"))


def test_robots_disallow_blocks_the_download(tmp_path: Path) -> None:
    robots = HttpResponse(200, b"User-agent: *\nDisallow: /docs\n", "text/plain")
    web = FakeWeb({"https://www.lpu.in/robots.txt": robots})

    with pytest.raises(FetchError, match=r"robots.txt disallows"):
        fetcher(tmp_path, web).get(source())

    assert web.requested == ["https://www.lpu.in/robots.txt"]


def test_failed_download_falls_back_to_the_local_copy(tmp_path: Path) -> None:
    (tmp_path / "policy.pdf").write_bytes(PDF)
    web = FakeWeb(
        {
            "https://www.lpu.in/robots.txt": ROBOTS_OK,
            "https://www.lpu.in/docs/policy.pdf": HttpResponse(403, b"", "text/html"),
        }
    )

    fetched = fetcher(tmp_path, web).get(source())

    assert not fetched.downloaded
    assert fetched.note is not None and "HTTP 403" in fetched.note
    assert fetched.sha256 == hashlib.sha256(PDF).hexdigest()


def test_unreachable_robots_txt_means_disallow(tmp_path: Path) -> None:
    web = FakeWeb({"https://www.lpu.in/robots.txt": HttpResponse(503, b"", "text/html")})

    with pytest.raises(FetchError, match=r"robots.txt disallows"):
        fetcher(tmp_path, web).get(source())


def test_robots_txt_is_fetched_once_per_host(tmp_path: Path) -> None:
    web = FakeWeb(
        {
            "https://www.lpu.in/robots.txt": ROBOTS_OK,
            "https://www.lpu.in/docs/policy.pdf": HttpResponse(200, PDF, "application/pdf"),
        }
    )
    f = fetcher(tmp_path, web)

    f.get(source())
    f.get(source())

    assert web.requested.count("https://www.lpu.in/robots.txt") == 1


def test_offline_mode_uses_local_files_only(tmp_path: Path) -> None:
    (tmp_path / "policy.pdf").write_bytes(PDF)
    web = FakeWeb({})

    fetched = fetcher(tmp_path, web, offline=True).get(source())

    assert web.requested == []
    assert not fetched.downloaded


def test_error_page_saved_as_pdf_is_rejected(tmp_path: Path) -> None:
    not_found = HttpResponse(200, b"Not found", "application/pdf")
    web = FakeWeb(
        {
            "https://www.lpu.in/robots.txt": ROBOTS_OK,
            "https://www.lpu.in/docs/policy.pdf": not_found,
        }
    )

    with pytest.raises(FetchError, match=r"not a valid .pdf"):
        fetcher(tmp_path, web).get(source())


def test_waits_between_requests_to_the_same_host(tmp_path: Path) -> None:
    waits: list[float] = []
    web = FakeWeb(
        {
            "https://www.lpu.in/robots.txt": ROBOTS_OK,
            "https://www.lpu.in/docs/policy.pdf": HttpResponse(200, PDF, "application/pdf"),
        }
    )
    f = Fetcher(tmp_path, "LumenBot/0.1", web, delay_seconds=5, sleep=waits.append)

    f.get(source())

    assert len(waits) == 1 and 0 < waits[0] <= 5


@pytest.mark.parametrize(
    ("url", "content_type", "suffix"),
    [
        ("https://x.in/a.pdf", "application/pdf", ".pdf"),
        ("https://x.in/a.php", "text/html", ".html"),
        ("https://x.in/a.docx", "application/octet-stream", ".docx"),
        ("https://x.in/a.jpeg", "", ".jpg"),
        ("https://x.in/page", "", ".html"),
    ],
)
def test_suffix_for(url: str, content_type: str, suffix: str) -> None:
    assert suffix_for(url, content_type) == suffix


def test_pdf_link_answering_with_a_web_page_is_a_dead_link() -> None:
    with pytest.raises(FetchError, match="sent a web page"):
        suffix_for("https://x.in/a.pdf", "text/html")


def test_local_file_preference_order(tmp_path: Path) -> None:
    for name in ("policy.doc", "policy.md", "policy.html"):
        (tmp_path / name).write_text("x", encoding="utf-8")

    assert find_local_file(tmp_path, "policy") == tmp_path / "policy.md"
    assert find_local_file(tmp_path, "other") is None
