"""Langfuse tracing (SPEC §9 step 9): one trace per chat request, one span per pipeline step.

    chat              root span, opened by POST /chat (app/api/chat.py)
      rewrite         follow-up -> standalone question (an LLM call)
      cache-lookup    the semantic answer cache (SPEC §7.2)
      retrieve        hybrid Qdrant search
      rerank          cross-encoder scores; the best one is compared with τ
      generate        the streamed answer (an LLM call)
      cache-store

The LLM calls themselves are recorded by LiteLLM's `langfuse_otel` callback (model, prompt,
tokens, cost, and every fallback attempt) as generations under the step that made them.
Both sides use OpenTelemetry, so the callback finds the span that is open at the time.

Tracing is off unless LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are set: then `Tracer`
does nothing and no data leaves the process. Langfuse is imported in this module only;
the rest of the app sees `Tracer` and `Span`.

What a trace holds: the question, the standalone question, retrieved chunk IDs and scores,
and the answer (the /privacy page names Langfuse). It never holds the session ID, an IP
address or device details. Traces are grouped by conversation ID.
"""

import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Protocol

from app.config import Settings

if TYPE_CHECKING:
    from langfuse import Langfuse

logger = logging.getLogger(__name__)


class Span(Protocol):
    """An open observation. `update` sets output, metadata, level or status_message."""

    trace_id: str | None

    def update(self, **fields: Any) -> None: ...


class _NoSpan:
    trace_id: str | None = None

    def update(self, **fields: Any) -> None:
        pass


NO_SPAN = _NoSpan()


class Tracer:
    """Langfuse when a client is given, otherwise a no-op with the same methods."""

    def __init__(self, client: "Langfuse | None" = None) -> None:
        self._client = client

    @property
    def enabled(self) -> bool:
        return self._client is not None

    @contextmanager
    def trace(self, name: str, *, session_id: str, input: Any = None) -> Iterator[Span]:
        """The root span of one request. Its `trace_id` is stored with the answer."""
        if self._client is None:
            yield NO_SPAN
            return
        from langfuse import propagate_attributes

        with (
            self._client.start_as_current_observation(name=name, input=input) as span,
            propagate_attributes(session_id=session_id, trace_name=name),
        ):
            yield span

    @contextmanager
    def span(self, name: str, *, input: Any = None, as_type: str = "span") -> Iterator[Span]:
        """A child of whatever span is open, in this task or the thread it started."""
        if self._client is None:
            yield NO_SPAN
            return
        with self._client.start_as_current_observation(
            name=name,
            as_type=as_type,  # type: ignore[call-overload]
            input=input,
        ) as span:
            yield span

    def shutdown(self) -> None:
        """Send what is still buffered. Called when the API stops."""
        if self._client is not None:
            self._client.shutdown()


def register_litellm_callback(settings: Settings) -> None:
    """Make LiteLLM report every LLM call to Langfuse as a generation.

    The callback reads its keys from the environment only, so they are copied there.
    """
    assert settings.langfuse_public_key and settings.langfuse_secret_key
    os.environ["LANGFUSE_PUBLIC_KEY"] = settings.langfuse_public_key
    os.environ["LANGFUSE_SECRET_KEY"] = settings.langfuse_secret_key.get_secret_value()
    os.environ["LANGFUSE_HOST"] = settings.langfuse_base_url
    # app.rag.generator imports LiteLLM with the bundled price list; reuse that import.
    from app.rag.generator import litellm

    if "langfuse_otel" not in litellm.callbacks:
        litellm.callbacks.append("langfuse_otel")


def build_tracer(settings: Settings) -> Tracer:
    """The tracer for the running API: Langfuse when both keys are set, else a no-op."""
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        logger.info("Langfuse tracing is off: LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY not set")
        return Tracer()
    from langfuse import Langfuse

    client = Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key.get_secret_value(),
        base_url=settings.langfuse_base_url,
    )
    register_litellm_callback(settings)
    logger.info("Langfuse tracing is on (%s)", settings.langfuse_base_url)
    return Tracer(client)
