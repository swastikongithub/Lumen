"""Guards for the CLAUDE.md hard rules that a file scan can check."""

import tomllib
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent

SKIPPED_DIRS = {".git", ".venv", "node_modules", ".svelte-kit", "build", ".gradle", ".pytest_cache"}
TYPESCRIPT_SUFFIXES = {".ts", ".tsx", ".mts", ".cts"}
SIGNING_KEY_SUFFIXES = {".jks", ".keystore"}


def repo_files() -> list[Path]:
    files = []
    for path in REPO_ROOT.rglob("*"):
        relative_parts = path.relative_to(REPO_ROOT).parts
        if path.is_file() and not SKIPPED_DIRS.intersection(relative_parts):
            files.append(path)
    return files


def api_dependencies() -> list[str]:
    pyproject = tomllib.loads((BACKEND_DIR / "pyproject.toml").read_text(encoding="utf-8"))
    return [dep.lower() for dep in pyproject["project"]["dependencies"]]


def test_no_typescript_anywhere() -> None:
    """Rule 1: plain JavaScript and Python only."""
    offenders = [
        path
        for path in repo_files()
        if path.suffix in TYPESCRIPT_SUFFIXES
        or path.name == "tsconfig.json"
        or (path.suffix == ".svelte" and 'lang="ts"' in path.read_text(encoding="utf-8"))
    ]
    assert offenders == []


def test_no_signing_keys_in_the_repo() -> None:
    """Rule 10: keystores and their passwords never live in the repo."""
    offenders = [
        path
        for path in repo_files()
        if path.suffix in SIGNING_KEY_SUFFIXES or path.name == "keystore.properties"
    ]
    assert offenders == []


def test_api_image_dependencies_exclude_docling_and_frameworks() -> None:
    """Rules 2 and 3: Docling only in the ingest group; no LangChain/LlamaIndex in the API."""
    banned = ("docling", "langchain", "llama-index", "llama_index")
    offenders = [dep for dep in api_dependencies() if dep.startswith(banned)]
    assert offenders == []
