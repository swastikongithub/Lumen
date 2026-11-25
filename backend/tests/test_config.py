import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import REPO_ROOT, Settings

ENV_EXAMPLE = Path(__file__).resolve().parents[1] / ".env.example"


def test_env_example_lists_every_setting() -> None:
    """CLAUDE.md rule 6: .env.example documents every setting in app/config.py."""
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    documented = set(re.findall(r"^([A-Z][A-Z0-9_]*)=", text, flags=re.MULTILINE))

    missing = {name.upper() for name in Settings.model_fields} - documented

    assert missing == set()


def test_ingestion_paths_default_to_the_repo_data_folder() -> None:
    settings = Settings(_env_file=None)

    assert settings.sources_path == REPO_ROOT / "data" / "sources.yaml"
    assert settings.raw_dir == REPO_ROOT / "data" / "raw"


def test_defaults_match_local_docker_compose() -> None:
    settings = Settings(_env_file=None)

    assert settings.database_url == "postgresql+asyncpg://lumen:lumen@localhost:5433/lumen"
    assert settings.qdrant_url == "http://localhost:6333"
    assert settings.cors_origins == ["http://localhost:5173", "https://localhost"]
    assert settings.qdrant_api_key is None


def test_cors_origins_are_read_comma_separated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "https://lumen.pages.dev, http://localhost:5173,")

    settings = Settings(_env_file=None)

    assert settings.cors_origins == ["https://lumen.pages.dev", "http://localhost:5173"]


def test_empty_values_count_as_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QDRANT_API_KEY", "")
    monkeypatch.setenv("APP_NOTICE", "")

    settings = Settings(_env_file=None)

    assert settings.qdrant_api_key is None
    assert settings.app_notice is None


def test_secrets_are_not_printed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QDRANT_API_KEY", "super-secret")

    settings = Settings(_env_file=None)

    assert "super-secret" not in repr(settings)
    assert settings.qdrant_api_key.get_secret_value() == "super-secret"


def test_ready_timeout_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, ready_timeout_seconds=0)
