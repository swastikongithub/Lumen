"""Tracing: a no-op without keys; with Langfuse, every step is a span in one trace.

Spans go to an in-memory exporter, so nothing is sent anywhere.
"""

import asyncio
import os
from collections.abc import Iterator

import pytest
from langfuse import Langfuse
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.config import Settings
from app.observability import NO_SPAN, Tracer, build_tracer, register_litellm_callback
from app.rag.generator import litellm


@pytest.fixture
def exporter() -> InMemorySpanExporter:
    return InMemorySpanExporter()


@pytest.fixture
def langfuse(exporter: InMemorySpanExporter) -> Iterator[Langfuse]:
    client = Langfuse(
        public_key="pk-lf-test",
        secret_key="sk-lf-test",
        base_url="http://127.0.0.1:9",  # never contacted: spans go to `exporter`
        tracer_provider=TracerProvider(),
        span_exporter=exporter,
    )
    yield client
    client.shutdown()


def finished(client: Langfuse, exporter: InMemorySpanExporter) -> dict[str, ReadableSpan]:
    client.flush()
    return {span.name: span for span in exporter.get_finished_spans()}


def test_without_keys_tracing_is_a_no_op() -> None:
    tracer = build_tracer(Settings(_env_file=None))

    with tracer.trace("chat", session_id="conv-1") as root, tracer.span("retrieve") as span:
        span.update(output=[1, 2])
        root.update(output="answer")

    assert not tracer.enabled
    assert root is NO_SPAN and root.trace_id is None
    tracer.shutdown()


async def test_steps_nest_under_the_request_trace(
    langfuse: Langfuse, exporter: InMemorySpanExporter
) -> None:
    tracer = Tracer(langfuse)

    def rerank_in_a_thread() -> None:
        with tracer.span("rerank") as span:
            span.update(output={"best_score": 1.5})

    with tracer.trace("chat", session_id="conv-1", input={"question": "q"}) as root:
        with tracer.span("retrieve", as_type="retriever", input="q") as span:
            span.update(output=["chunk-1"])
        await asyncio.to_thread(rerank_in_a_thread)
        root.update(output="answer")

    spans = finished(langfuse, exporter)
    chat, retrieve, rerank = spans["chat"], spans["retrieve"], spans["rerank"]
    assert root.trace_id == format(chat.context.trace_id, "032x")
    assert {span.context.trace_id for span in spans.values()} == {chat.context.trace_id}
    assert retrieve.parent.span_id == rerank.parent.span_id == chat.context.span_id
    assert retrieve.attributes["langfuse.observation.type"] == "retriever"
    assert rerank.attributes["langfuse.observation.output"] == '{"best_score": 1.5}'


async def test_traces_are_grouped_by_conversation_not_by_device(
    langfuse: Langfuse, exporter: InMemorySpanExporter
) -> None:
    tracer = Tracer(langfuse)

    with tracer.trace("chat", session_id="conversation-id"), tracer.span("retrieve"):
        pass

    for span in finished(langfuse, exporter).values():
        assert span.attributes["session.id"] == "conversation-id"
        assert "user.id" not in span.attributes


def test_litellm_callback_gets_the_keys_once(monkeypatch: pytest.MonkeyPatch) -> None:
    # setenv (unlike delenv) restores a variable that was unset by deleting it again.
    for name in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST"):
        monkeypatch.setenv(name, "")
    monkeypatch.setattr(litellm, "callbacks", [])
    settings = Settings(
        _env_file=None,
        langfuse_public_key="pk-lf-test",
        langfuse_secret_key="sk-lf-test",
        langfuse_base_url="https://us.cloud.langfuse.com",
    )

    register_litellm_callback(settings)
    register_litellm_callback(settings)

    assert litellm.callbacks == ["langfuse_otel"]
    assert os.environ["LANGFUSE_SECRET_KEY"] == "sk-lf-test"
    assert os.environ["LANGFUSE_HOST"] == "https://us.cloud.langfuse.com"
