"""Shared setup for the eval scripts: logging, Qdrant clients, models, the production config.

Loading an ONNX model takes seconds, so embedders and re-rankers are created once per
run and shared between configurations.
"""

import logging
import sys
from collections.abc import Sequence
from functools import cache

from qdrant_client import AsyncQdrantClient, QdrantClient

from app.config import Settings
from app.evals.golden import GoldenCase
from app.evals.retrieval import Mode, RetrievalConfig, Searcher
from app.rag.reranker import CrossEncoderScorer
from app.rag.retriever import QueryEmbedder

QUIET_LOGGERS = ("httpx", "fastembed", "LiteLLM", "LiteLLM Router", "docling", "RapidOCR")


def setup_logging(verbose: bool = False) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # τ, ₹ on Windows consoles
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    for name in QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)


def _api_key(settings: Settings) -> str | None:
    return settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else None


def sync_client(settings: Settings) -> QdrantClient:
    return QdrantClient(url=settings.qdrant_url, api_key=_api_key(settings))


def async_client(settings: Settings) -> AsyncQdrantClient:
    return AsyncQdrantClient(url=settings.qdrant_url, api_key=_api_key(settings))


@cache
def embedder(model_name: str) -> QueryEmbedder:
    return QueryEmbedder(model_name)


@cache
def scorer(model_name: str) -> CrossEncoderScorer:
    return CrossEncoderScorer(model_name)


def short_model_name(model_name: str) -> str:
    """ "Xenova/ms-marco-MiniLM-L-12-v2" -> "ms-marco-MiniLM-L-12-v2"."""
    return model_name.rsplit("/", 1)[-1]


def production_config(settings: Settings) -> RetrievalConfig:
    """What the API serves: hybrid RRF candidates re-ranked by the configured model."""
    return RetrievalConfig(
        name=f"Hybrid + {short_model_name(settings.rerank_model)}",
        mode=Mode.HYBRID,
        reranker=settings.rerank_model,
        candidates=settings.retrieve_fused_limit,
    )


def make_searcher(
    settings: Settings,
    client: AsyncQdrantClient,
    collection: str,
    origins: Sequence[str] | None = None,
) -> Searcher:
    return Searcher(
        client,
        collection,
        embedder(settings.embed_model).embed,
        dense_limit=settings.retrieve_dense_limit,
        sparse_limit=settings.retrieve_sparse_limit,
        origins=settings.retrieval_origins if origins is None else origins,
    )


def covered_cases(cases: Sequence[GoldenCase], source_ids: set[str]) -> list[GoldenCase]:
    """Answerable cases whose every piece of evidence has a location in `source_ids`
    (e.g. the documents in the CI fixture). Unanswerable cases are left out."""
    return [
        case
        for case in cases
        if case.answerable
        and all(
            any(loc.source_id in source_ids for loc in evidence.locations)
            for evidence in case.relevant
        )
    ]
