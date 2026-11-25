"""Application settings, read from environment variables (and `.env` in development).

Every setting has a matching entry in `backend/.env.example`. Keep the two in sync.
"""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# backend/app/config.py -> the repository root, which holds data/.
REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    # env_ignore_empty: `QDRANT_API_KEY=` in .env means "not set", not an empty string.
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", env_ignore_empty=True
    )

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # Postgres. Local default matches docker-compose.yml (host port 5433).
    database_url: str = "postgresql+asyncpg://lumen:lumen@localhost:5433/lumen"

    # Qdrant. The API key is only needed for Qdrant Cloud.
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: SecretStr | None = None
    qdrant_collection: str = "kb_chunks"

    # Embeddings (SPEC §7.2, §8). The API embeds queries with the same model.
    embed_model: str = "BAAI/bge-small-en-v1.5"
    embed_dim: int = Field(default=384, gt=0)
    embed_batch_size: int = Field(default=64, gt=0)

    # Ingestion (SPEC §8). Used by the `lumen` CLI only, never by the API.
    sources_path: Path = REPO_ROOT / "data" / "sources.yaml"
    raw_dir: Path = REPO_ROOT / "data" / "raw"
    chunk_max_tokens: int = Field(default=384, gt=0)
    # Reject a document when more than this share of its pages has no text.
    max_empty_page_ratio: float = Field(default=0.2, ge=0, le=1)
    # The product token before "/" is what robots.txt rules are matched against.
    fetch_user_agent: str = "LumenBot/0.1"
    fetch_timeout_seconds: float = Field(default=60.0, gt=0)
    # Pause between two downloads from the same host.
    fetch_delay_seconds: float = Field(default=1.0, ge=0)

    # Browser origins allowed to call the API (SPEC §10). Comma-separated in the environment.
    # http://localhost:5173 = Vite dev server, https://localhost = Capacitor Android WebView.
    cors_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:5173",
        "https://localhost",
    ]

    # Returned by GET /api/v1/meta. The Android app blocks itself below min_app_version.
    min_app_version: str = "1.0.0"
    latest_app_version: str = "1.0.0"
    app_notice: str | None = None

    # Per-dependency timeout for GET /ready.
    ready_timeout_seconds: float = Field(default=2.0, gt=0)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_comma_separated(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    """Settings for the running process, loaded once."""
    return Settings()
