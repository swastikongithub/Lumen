"""Application settings, read from environment variables (and `.env` in development).

Every setting has a matching entry in `backend/.env.example`. Keep the two in sync.
"""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from limits import parse_many
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

    # Retrieval (SPEC §9 step 4): dense + BM25 candidates fused with RRF.
    retrieve_dense_limit: int = Field(default=30, gt=0)
    retrieve_sparse_limit: int = Field(default=30, gt=0)
    retrieve_fused_limit: int = Field(default=20, gt=0)
    # Document groups answers may come from (SPEC §3.2). Comma-separated in the environment.
    retrieval_origins: Annotated[list[str], NoDecode] = ["lpu.in", "ums"]

    # Re-ranking and abstention (SPEC §9 steps 5-6).
    rerank_model: str = "Xenova/ms-marco-MiniLM-L-12-v2"
    rerank_top_n: int = Field(default=5, gt=0)
    # τ, compared with the best cross-encoder score (a raw logit, so it can be negative).
    # Tuned on the golden set for MiniLM-L-12 (evals/reports/ablation.md); re-tune it with
    # the ablation when the re-ranker or the golden set changes.
    abstain_threshold: float = -3.5
    abstain_sources: int = Field(default=3, ge=0)

    # Generation (SPEC §9 step 7, §9.2). Model ids are LiteLLM's "<provider>/<model>".
    groq_api_key: SecretStr | None = None
    gemini_api_key: SecretStr | None = None
    llm_primary_model: str = "groq/openai/gpt-oss-120b"
    llm_secondary_model: str = "groq/openai/gpt-oss-20b"
    llm_fallback_model: str = "gemini/gemini-3.5-flash"
    llm_reasoning_effort: Literal["low", "medium", "high"] | None = "low"
    context_max_tokens: int = Field(default=2000, gt=0)
    answer_max_tokens: int = Field(default=400, gt=0)
    llm_temperature: float = Field(default=0.1, ge=0, le=2)
    llm_timeout_seconds: float = Field(default=30.0, gt=0)
    llm_cooldown_seconds: int = Field(default=60, gt=0)

    # Follow-up rewriting (SPEC §9 step 2). A turn is one earlier message, question or
    # answer, so the default 4 is the last two exchanges. 0 turns rewriting off.
    rewrite_history_turns: int = Field(default=4, ge=0)
    # Reasoning models think inside this budget too, so it is larger than a question needs.
    rewrite_max_tokens: int = Field(default=300, gt=0)

    # Semantic answer cache (SPEC §7.2, §9 step 3), a Qdrant collection.
    cache_enabled: bool = True
    cache_collection: str = "answer_cache"
    # Cosine similarity a new question needs to reuse a cached answer.
    cache_threshold: float = Field(default=0.95, gt=0, le=1)

    # Rate limits on POST /chat (SPEC §9 step 1, §13), in slowapi's "10/minute;100/day"
    # form. Counted in memory per instance. The IP limit is higher because students on
    # campus Wi-Fi share a few public addresses.
    rate_limit_session: str = "10/minute;100/day"
    rate_limit_ip: str = "60/minute;1000/day"
    # Proxies in front of the API that append the caller's address to X-Forwarded-For.
    # 0 = use the TCP peer address (local development).
    trusted_proxy_hops: int = Field(default=0, ge=0)

    # Conversations, messages, feedback and cached answers older than this are deleted
    # (SPEC §13, promised on /privacy). Checked at startup and then every few hours.
    retention_days: int = Field(default=30, gt=0)
    retention_check_hours: float = Field(default=6.0, gt=0)

    # Langfuse tracing (SPEC §9 step 9). Off unless both keys are set.
    langfuse_public_key: str | None = None
    langfuse_secret_key: SecretStr | None = None
    langfuse_base_url: str = "https://cloud.langfuse.com"

    # GET /admin/stats needs this in X-Admin-Key. Unset = the endpoint answers 404.
    admin_api_key: SecretStr | None = None

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

    @field_validator("cors_origins", "retrieval_origins", mode="before")
    @classmethod
    def split_comma_separated(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("rate_limit_session", "rate_limit_ip")
    @classmethod
    def check_rate_limit(cls, value: str) -> str:
        """Fail at startup, not on the first request, when a limit string is malformed."""
        parse_many(value)
        return value


@lru_cache
def get_settings() -> Settings:
    """Settings for the running process, loaded once."""
    return Settings()
