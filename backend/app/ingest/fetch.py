"""Step 1 of ingestion (SPEC §8): get each source's file into data/raw/ and hash it.

- `fetch: manual` entries are never downloaded: the file someone saved as
  data/raw/<id>.<ext> is used.
- Other entries are downloaded with Lumen's own User-Agent, only where robots.txt
  allows it, with a pause between requests to the same host. If a download fails
  but data/raw/ already has a copy, that copy is used and the reason is reported.
"""

import hashlib
import logging
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from app.ingest.robots import ALLOW_ALL, DISALLOW_ALL, Robots, parse_robots, product_token
from app.ingest.sources import Source

logger = logging.getLogger(__name__)

# Formats Docling can parse, in the order a local file is preferred when data/raw/
# holds several for one id (e.g. a hand-made .md next to the original .doc).
PARSEABLE_SUFFIXES = (".pdf", ".docx", ".md", ".html", ".png", ".jpg", ".jpeg")

CONTENT_TYPE_SUFFIXES = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "text/markdown": ".md",
    "text/html": ".html",
    "application/xhtml+xml": ".html",
    "image/png": ".png",
    "image/jpeg": ".jpg",
}
# URL endings that are web pages rather than files.
PAGE_SUFFIXES = {"", ".php", ".aspx", ".asp", ".htm", ".html"}
# First bytes each binary format must start with, to catch error pages saved as files.
MAGIC_BYTES = {
    ".pdf": (b"%PDF",),
    ".docx": (b"PK\x03\x04",),
    ".png": (b"\x89PNG",),
    ".jpg": (b"\xff\xd8\xff",),
}


class FetchError(Exception):
    """The source's file could not be downloaded and no local copy exists."""


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: bytes
    content_type: str  # media type only, lower-case, e.g. "application/pdf"


@dataclass(frozen=True)
class FetchedFile:
    path: Path
    sha256: str
    downloaded: bool  # False when an existing data/raw/ file was used
    note: str | None = None  # why a local copy was used instead of downloading


HttpGet = Callable[[str], HttpResponse]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def find_local_file(raw_dir: Path, source_id: str) -> Path | None:
    """The preferred parseable file saved for this id, if any."""
    for suffix in PARSEABLE_SUFFIXES:
        candidate = raw_dir / f"{source_id}{suffix}"
        if candidate.is_file():
            return candidate
    return None


def suffix_for(url: str, content_type: str) -> str:
    """File extension for a download, from its Content-Type, else its URL."""
    url_suffix = PurePosixPath(urlsplit(url).path).suffix.lower()
    from_type = CONTENT_TYPE_SUFFIXES.get(content_type)
    if from_type == ".html" and url_suffix not in PAGE_SUFFIXES:
        # e.g. a .pdf link that now answers with a web page: a dead or moved link.
        raise FetchError(f"expected a {url_suffix} file but the server sent a web page")
    if from_type:
        return from_type
    if url_suffix in PAGE_SUFFIXES:
        return ".html"
    if url_suffix == ".jpeg":
        return ".jpg"
    if url_suffix in PARSEABLE_SUFFIXES:
        return url_suffix
    raise FetchError(f"unsupported file type {content_type or url_suffix!r}")


def check_content(body: bytes, suffix: str) -> None:
    if not body.strip():
        raise FetchError("the download is empty")
    magic = MAGIC_BYTES.get(suffix)
    if magic and not body.startswith(magic):
        raise FetchError(f"the download is not a valid {suffix} file")


def urllib_get(user_agent: str, timeout: float) -> HttpGet:
    """An HttpGet that uses the standard library (no extra dependency)."""

    def get(url: str) -> HttpResponse:
        request = urllib.request.Request(url, headers={"User-Agent": user_agent})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return HttpResponse(
                    response.status, response.read(), response.headers.get_content_type()
                )
        except urllib.error.HTTPError as error:
            return HttpResponse(error.code, b"", error.headers.get_content_type())

    return get


class Fetcher:
    def __init__(
        self,
        raw_dir: Path,
        user_agent: str,
        http_get: HttpGet,
        *,
        delay_seconds: float = 1.0,
        offline: bool = False,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.raw_dir = raw_dir
        self.token = product_token(user_agent)
        self.offline = offline
        self._http_get = http_get
        self._delay = delay_seconds
        self._sleep = sleep
        self._robots: dict[str, Robots] = {}
        self._last_request: dict[str, float] = {}

    def get(self, source: Source) -> FetchedFile:
        local = find_local_file(self.raw_dir, source.id)
        if source.is_manual or self.offline:
            if local is None:
                raise FetchError(self._missing_message(source))
            return FetchedFile(local, sha256_file(local), downloaded=False)

        try:
            return self._download(source)
        except (FetchError, OSError) as error:
            if local is None:
                raise FetchError(f"download failed: {error}") from error
            note = f"download failed ({error}); used {local.name}"
            logger.warning("%s: %s", source.id, note)
            return FetchedFile(local, sha256_file(local), downloaded=False, note=note)

    def _download(self, source: Source) -> FetchedFile:
        if not self._robots_for(source.url).allows(self.token, source.url):
            raise FetchError("robots.txt disallows this URL; mark it `fetch: manual`")
        response = self._request(source.url)
        if response.status != 200:
            raise FetchError(f"HTTP {response.status}")
        suffix = suffix_for(source.url, response.content_type)
        check_content(response.body, suffix)

        self.raw_dir.mkdir(parents=True, exist_ok=True)
        path = self.raw_dir / f"{source.id}{suffix}"
        partial = path.with_name(path.name + ".part")
        partial.write_bytes(response.body)
        partial.replace(path)  # atomic: a crash never leaves half a file under the real name
        return FetchedFile(path, hashlib.sha256(response.body).hexdigest(), downloaded=True)

    def _robots_for(self, url: str) -> Robots:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            try:
                response = self._request(f"{origin}/robots.txt")
            except OSError:
                response = HttpResponse(599, b"", "")
            if response.status == 200:
                robots = parse_robots(response.body.decode("utf-8", errors="replace"))
            elif 400 <= response.status < 500:
                robots = ALLOW_ALL  # RFC 9309: an unavailable robots.txt allows everything
            else:
                robots = DISALLOW_ALL  # unreachable (5xx, network): assume full disallow
            self._robots[origin] = robots
        return self._robots[origin]

    def _request(self, url: str) -> HttpResponse:
        host = urlsplit(url).netloc
        last = self._last_request.get(host)
        if last is not None:
            wait = self._delay - (time.monotonic() - last)
            if wait > 0:
                self._sleep(wait)
        try:
            return self._http_get(url)
        finally:
            self._last_request[host] = time.monotonic()

    def _missing_message(self, source: Source) -> str:
        others = sorted(p.name for p in self.raw_dir.glob(f"{source.id}.*"))
        reason = "offline mode" if self.offline and not source.is_manual else "manual source"
        message = f"{reason}: save the file as {self.raw_dir.name}/{source.id}.<ext>"
        if others:
            message += f" ({', '.join(others)} cannot be parsed; convert it to PDF or Markdown)"
        return message
