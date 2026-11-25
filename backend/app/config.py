"""Application settings, read from environment variables (and `.env` in development).

Every setting has a matching entry in `backend/.env.example`. Keep the two in sync.
"""

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


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
