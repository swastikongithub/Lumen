"""The LiteLLM chain, using LiteLLM's built-in `mock_response` (no network, no keys)."""

from types import SimpleNamespace

import pytest

from app.config import Settings
from app.rag.generator import (
    GenerationInfo,
    LiteLLMGenerator,
    LlmBusyError,
    LlmUnavailableError,
    build_router,
    model_list,
    retry_after_seconds,
)

MESSAGES = [{"role": "user", "content": "attendance?"}]
RATE_LIMITED = "litellm.RateLimitError"  # mock_response value that makes LiteLLM raise a 429


def deployment(group: str, model: str, mock_response: str) -> dict:
    return {
        "model_name": group,
        "litellm_params": {"model": model, "api_key": "test-key", "mock_response": mock_response},
    }


def generator(*deployments: dict) -> LiteLLMGenerator:
    return LiteLLMGenerator(
        build_router(list(deployments), cooldown_seconds=60),
        entry_group=deployments[0]["model_name"],
        max_tokens=400,
        temperature=0.1,
        default_retry_after=60,
    )


async def collect(gen: LiteLLMGenerator) -> tuple[str, GenerationInfo]:
    info = GenerationInfo()
    text = "".join([piece async for piece in gen.stream(MESSAGES, info)])
    return text, info


async def test_streams_text_and_records_model_and_usage() -> None:
    gen = generator(deployment("primary", "groq/openai/gpt-oss-120b", "You need 75% [1]."))

    text, info = await collect(gen)

    assert text == "You need 75% [1]."
    assert info.model == "openai/gpt-oss-120b"
    assert info.tokens_in and info.tokens_out


async def test_falls_back_to_the_next_model_on_a_rate_limit() -> None:
    gen = generator(
        deployment("primary", "groq/openai/gpt-oss-120b", RATE_LIMITED),
        deployment("secondary", "groq/openai/gpt-oss-20b", "From the second model [1]."),
    )

    text, info = await collect(gen)

    assert text == "From the second model [1]."
    assert info.model == "openai/gpt-oss-20b"


async def test_every_model_rate_limited_raises_busy() -> None:
    gen = generator(
        deployment("primary", "groq/openai/gpt-oss-120b", RATE_LIMITED),
        deployment("secondary", "groq/openai/gpt-oss-20b", RATE_LIMITED),
    )

    with pytest.raises(LlmBusyError) as error:
        await collect(gen)

    assert error.value.retry_after > 0


async def test_no_configured_model_raises_unavailable() -> None:
    gen = LiteLLMGenerator(None, max_tokens=400, temperature=0.1, default_retry_after=60)

    assert not gen.configured
    with pytest.raises(LlmUnavailableError):
        await collect(gen)


async def test_complete_returns_the_whole_reply() -> None:
    gen = generator(deployment("primary", "groq/openai/gpt-oss-120b", "What is the fee?"))

    assert await gen.complete(MESSAGES, max_tokens=50) == "What is the fee?"


async def test_complete_falls_back_and_maps_errors_like_stream() -> None:
    fallback = generator(
        deployment("primary", "groq/openai/gpt-oss-120b", RATE_LIMITED),
        deployment("secondary", "groq/openai/gpt-oss-20b", "From the second model."),
    )
    busy = generator(deployment("primary", "groq/openai/gpt-oss-120b", RATE_LIMITED))
    unconfigured = LiteLLMGenerator(None, max_tokens=400, temperature=0.1, default_retry_after=60)

    assert await fallback.complete(MESSAGES, max_tokens=50) == "From the second model."
    with pytest.raises(LlmBusyError):
        await busy.complete(MESSAGES, max_tokens=50)
    with pytest.raises(LlmUnavailableError):
        await unconfigured.complete(MESSAGES, max_tokens=50)


def test_only_models_with_a_provider_key_join_the_chain() -> None:
    settings = Settings(_env_file=None, groq_api_key="groq-secret", gemini_api_key=None)

    deployments = model_list(settings)

    assert [d["model_name"] for d in deployments] == ["primary", "secondary"]
    params = deployments[0]["litellm_params"]
    assert params["model"] == "groq/openai/gpt-oss-120b"
    assert params["api_key"] == "groq-secret"
    assert params["reasoning_effort"] == "low"


def test_full_chain_falls_back_in_order() -> None:
    settings = Settings(_env_file=None, groq_api_key="g", gemini_api_key="m")

    router = build_router(model_list(settings), cooldown_seconds=60)

    assert [d["model_name"] for d in model_list(settings)] == ["primary", "secondary", "fallback"]
    assert router.settings().fallbacks == [{"primary": ["secondary", "fallback"]}]


def test_reasoning_effort_can_be_turned_off() -> None:
    settings = Settings(_env_file=None, groq_api_key="g", llm_reasoning_effort=None)

    assert "reasoning_effort" not in model_list(settings)[0]["litellm_params"]


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (SimpleNamespace(headers={"retry-after": "12.2"}), 13),
        (SimpleNamespace(response=SimpleNamespace(headers={"retry-after": "7"})), 7),
        (SimpleNamespace(cooldown_time=30.0), 30),
        (SimpleNamespace(headers={"retry-after": "soon"}), 60),
        (SimpleNamespace(), 60),
    ],
)
def test_retry_after_comes_from_the_provider_or_the_cooldown(error, expected) -> None:
    assert retry_after_seconds(error, default=60) == expected
