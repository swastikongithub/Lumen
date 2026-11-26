"""FastAPI application: app factory, lifespan (shared clients, models, tracing, the
retention job), CORS, rate limiting and routes.

Run locally from backend/:  uv run uvicorn app.main:app --reload
"""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from importlib.metadata import version

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from qdrant_client import AsyncQdrantClient
from slowapi.errors import RateLimitExceeded

from app.api import (
    admin,
    chat,
    clear_data,
    conversations,
    feedback,
    health,
    meta,
    rate_limit,
    sources,
)
from app.config import Settings, get_settings
from app.db.retention import run_retention
from app.db.session import create_engine, create_sessionmaker
from app.observability import Tracer, build_tracer
from app.rag.pipeline import RagPipeline, build_pipeline

API_V1_PREFIX = "/api/v1"

# Headers browsers may send cross-origin. Sessions travel in X-Session-Id, never cookies.
ALLOWED_HEADERS = ["Content-Type", "X-Session-Id", "X-Client", "X-App-Version"]
# Response headers browser code may read cross-origin: how long to wait after a 429.
EXPOSED_HEADERS = ["Retry-After"]

PipelineFactory = Callable[[Settings, AsyncQdrantClient, Tracer], RagPipeline]

logger = logging.getLogger(__name__)


async def prepare_answer_cache(pipeline: RagPipeline) -> None:
    """Create the answer-cache collection if needed. Without Qdrant the API still starts:
    answers are then simply not cached (and /ready reports Qdrant as down)."""
    if pipeline.cache is None:
        return
    try:
        await pipeline.cache.ensure_collection()
    except Exception:
        logger.warning("Answer cache unavailable: answers will not be cached", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create shared clients and load the models once at startup; close them at shutdown."""
    settings: Settings = app.state.settings
    engine = create_engine(settings.database_url)
    api_key = settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else None
    qdrant = AsyncQdrantClient(url=settings.qdrant_url, api_key=api_key)
    tracer = build_tracer(settings)

    app.state.engine = engine
    app.state.sessionmaker = create_sessionmaker(engine)
    app.state.qdrant = qdrant
    app.state.tracer = tracer
    # Loading the ONNX models is slow CPU work; a thread keeps the event loop responsive.
    pipeline = await asyncio.to_thread(app.state.pipeline_factory, settings, qdrant, tracer)
    app.state.pipeline = pipeline
    cache = pipeline.cache if isinstance(pipeline, RagPipeline) else None
    if isinstance(pipeline, RagPipeline):
        await prepare_answer_cache(pipeline)
    retention = asyncio.create_task(
        run_retention(
            app.state.sessionmaker,
            cache,
            settings.retention_days,
            settings.retention_check_hours,
        )
    )
    logger.info("Lumen API started")
    try:
        yield
    finally:
        retention.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await retention
        await asyncio.to_thread(tracer.shutdown)  # sends the spans still buffered
        await qdrant.close()
        await engine.dispose()
        logger.info("Lumen API stopped")


def build_api_v1_router() -> APIRouter:
    """Every public route lives under /api/v1 (CLAUDE.md rule 12)."""
    router = APIRouter(prefix=API_V1_PREFIX)
    for module in (chat, conversations, feedback, sources, meta, clear_data):
        router.include_router(module.router)
    return router


def create_app(
    settings: Settings | None = None, pipeline_factory: PipelineFactory = build_pipeline
) -> FastAPI:
    """`pipeline_factory` is replaceable so tests can start the app without loading models."""
    settings = settings or get_settings()
    logging.basicConfig(
        level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    # httpx (used by qdrant-client) logs every request at INFO; /ready probes would flood logs.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    for name in ("LiteLLM", "LiteLLM Router", "LiteLLM Proxy"):
        logging.getLogger(name).setLevel(logging.WARNING)

    app = FastAPI(title="Lumen API", version=version("lumen"), lifespan=lifespan)
    app.state.settings = settings
    app.state.pipeline_factory = pipeline_factory
    # A no-op until the lifespan builds the configured tracer.
    app.state.tracer = Tracer()

    # Rate limits on POST /chat (app/api/rate_limit.py); slowapi looks for app.state.limiter.
    rate_limit.configure(settings)
    app.state.limiter = rate_limit.limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit.rate_limited)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=ALLOWED_HEADERS,
        expose_headers=EXPOSED_HEADERS,
        allow_credentials=False,
    )
    app.include_router(health.router)
    app.include_router(admin.router)
    app.include_router(build_api_v1_router())
    return app


app = create_app()
