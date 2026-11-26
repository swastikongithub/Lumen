"""FastAPI application: app factory, lifespan (shared clients and models), CORS and routes.

Run locally from backend/:  uv run uvicorn app.main:app --reload
"""

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from importlib.metadata import version

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from qdrant_client import AsyncQdrantClient

from app.api import chat, clear_data, conversations, feedback, health, meta, sources
from app.config import Settings, get_settings
from app.db.session import create_engine, create_sessionmaker
from app.rag.pipeline import RagPipeline, build_pipeline

API_V1_PREFIX = "/api/v1"

# Headers browsers may send cross-origin. Sessions travel in X-Session-Id, never cookies.
ALLOWED_HEADERS = ["Content-Type", "X-Session-Id", "X-Client", "X-App-Version"]

PipelineFactory = Callable[[Settings, AsyncQdrantClient], RagPipeline]

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create shared clients and load the models once at startup; close them at shutdown."""
    settings: Settings = app.state.settings
    engine = create_engine(settings.database_url)
    api_key = settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else None
    qdrant = AsyncQdrantClient(url=settings.qdrant_url, api_key=api_key)

    app.state.engine = engine
    app.state.sessionmaker = create_sessionmaker(engine)
    app.state.qdrant = qdrant
    # Loading the ONNX models is slow CPU work; a thread keeps the event loop responsive.
    app.state.pipeline = await asyncio.to_thread(app.state.pipeline_factory, settings, qdrant)
    logger.info("Lumen API started")
    try:
        yield
    finally:
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
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=ALLOWED_HEADERS,
        allow_credentials=False,
    )
    app.include_router(health.router)
    app.include_router(build_api_v1_router())
    return app


app = create_app()
