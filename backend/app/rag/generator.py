"""Step 7 of the query pipeline (SPEC §9.2): stream the answer from an LLM.

LiteLLM's Router holds up to three models, tried in order: primary -> secondary ->
fallback (by default two Groq models, whose free limits are counted per model, then
Gemini Flash). A model that answers 429 or 5xx is skipped at once (no retries on the
same model) and put on a cooldown, so the next requests go straight to the next one.
Only models whose provider has an API key configured join the chain.

When every model is rate-limited the caller gets LlmBusyError with `retry_after`, which
becomes the SSE `error` event the UI shows as a countdown. Any other failure is
LlmUnavailableError.

`stream` writes answers; `complete` returns a short reply in one piece (the follow-up
rewrite, SPEC §9 step 2). Both go through the same chain.
"""

import logging
import math
import os
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import SecretStr

# LiteLLM downloads its model price list from GitHub when imported, unless told to use
# the copy bundled with the package. The API should not depend on that request.
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

import litellm
from litellm import Router

from app.config import Settings

logger = logging.getLogger(__name__)

litellm.suppress_debug_info = True  # no "Give Feedback / Get Help" banners in the logs

Messages = Sequence[dict[str, str]]


class LlmBusyError(Exception):
    """Every model in the chain is rate-limited."""

    def __init__(self, retry_after: int) -> None:
        super().__init__(f"every model is rate-limited; retry after {retry_after}s")
        self.retry_after = retry_after


class LlmUnavailableError(Exception):
    """No model could answer: no key configured, provider down, or the stream broke off."""


@dataclass
class GenerationInfo:
    """Filled in while an answer streams: which model answered and the tokens it used."""

    model: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None


class Generator(Protocol):
    def stream(self, messages: Messages, info: GenerationInfo) -> AsyncIterator[str]: ...

    async def complete(self, messages: Messages, *, max_tokens: int) -> str: ...


def model_list(settings: Settings) -> list[dict[str, Any]]:
    """Router deployments for the configured models whose provider has a key."""
    keys: dict[str, SecretStr | None] = {
        "groq": settings.groq_api_key,
        "gemini": settings.gemini_api_key,
    }
    chain = (
        ("primary", settings.llm_primary_model),
        ("secondary", settings.llm_secondary_model),
        ("fallback", settings.llm_fallback_model),
    )
    deployments = []
    for group, model in chain:
        provider = model.split("/", 1)[0]
        key = keys.get(provider)
        if key is None:
            logger.warning("LLM %s (%s) left out: no API key for %s", group, model, provider)
            continue
        params: dict[str, Any] = {
            "model": model,
            "api_key": key.get_secret_value(),
            "timeout": settings.llm_timeout_seconds,
            # Leave out settings a model doesn't support (reasoning_effort on non-reasoners).
            "drop_params": True,
        }
        if settings.llm_reasoning_effort:
            params["reasoning_effort"] = settings.llm_reasoning_effort
        deployments.append({"model_name": group, "litellm_params": params})
    return deployments


def build_router(deployments: list[dict[str, Any]], cooldown_seconds: int) -> Router:
    groups = [deployment["model_name"] for deployment in deployments]
    fallbacks = [{groups[0]: groups[1:]}] if len(groups) > 1 else []
    return Router(
        model_list=deployments,
        fallbacks=fallbacks,
        num_retries=0,  # move on to the next model instead of retrying a rate-limited one
        cooldown_time=cooldown_seconds,
    )


def retry_after_seconds(error: Exception, default: int) -> int:
    """The provider's Retry-After header or the router's cooldown, else `default`."""
    response = getattr(error, "response", None)
    headers = getattr(error, "headers", None) or getattr(response, "headers", None) or {}
    candidates = (headers.get("retry-after"), getattr(error, "cooldown_time", None))
    for value in candidates:
        try:
            seconds = math.ceil(float(value))
        except (TypeError, ValueError):
            continue
        if seconds > 0:
            return seconds
    return default


class LiteLLMGenerator:
    def __init__(
        self,
        router: Router | None,
        *,
        entry_group: str = "primary",
        max_tokens: int,
        temperature: float,
        default_retry_after: int,
    ) -> None:
        self._router = router
        self._entry_group = entry_group  # the first model group of the chain
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._default_retry_after = default_retry_after

    @classmethod
    def from_settings(cls, settings: Settings) -> "LiteLLMGenerator":
        deployments = model_list(settings)
        router = build_router(deployments, settings.llm_cooldown_seconds) if deployments else None
        if router is None:
            logger.warning("No LLM API key configured: answers will fail with 'unavailable'")
        return cls(
            router,
            entry_group=deployments[0]["model_name"] if deployments else "primary",
            max_tokens=settings.answer_max_tokens,
            temperature=settings.llm_temperature,
            default_retry_after=settings.llm_cooldown_seconds,
        )

    @property
    def configured(self) -> bool:
        return self._router is not None

    async def _call(self, messages: Messages, **params: Any) -> Any:
        """One request through the chain, with failures mapped to the two errors above."""
        if self._router is None:
            raise LlmUnavailableError("no LLM provider key is configured")
        try:
            return await self._router.acompletion(
                model=self._entry_group, messages=list(messages), **params
            )
        except (litellm.RateLimitError, litellm.RouterRateLimitError) as error:
            raise LlmBusyError(retry_after_seconds(error, self._default_retry_after)) from error
        except Exception as error:
            logger.warning("LLM request failed: %s", type(error).__name__)
            raise LlmUnavailableError(type(error).__name__) from error

    async def complete(self, messages: Messages, *, max_tokens: int) -> str:
        """The whole reply at once, at temperature 0; "" if the model wrote no text."""
        response = await self._call(messages, max_tokens=max_tokens, temperature=0.0)
        choices = getattr(response, "choices", None) or []
        return (choices[0].message.content or "") if choices else ""

    async def stream(self, messages: Messages, info: GenerationInfo) -> AsyncIterator[str]:
        """Yield the answer text as it arrives; fill `info` along the way."""
        response = await self._call(
            messages,
            stream=True,
            stream_options={"include_usage": True},  # token counts in the last chunk
            max_tokens=self._max_tokens,
            temperature=self._temperature,
        )
        try:
            async for chunk in response:
                usage = getattr(chunk, "usage", None)
                if usage:
                    info.tokens_in = usage.prompt_tokens
                    info.tokens_out = usage.completion_tokens
                text = chunk.choices[0].delta.content if chunk.choices else None
                if text:
                    info.model = info.model or chunk.model
                    yield text
        except Exception as error:
            logger.warning("LLM stream broke off: %s", type(error).__name__)
            raise LlmUnavailableError(type(error).__name__) from error
