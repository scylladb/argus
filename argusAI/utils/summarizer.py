from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from argusAI.prompts import PRODUCTION_PROMPT_NAME, load_prompt

LOGGER = logging.getLogger(__name__)

DEFAULT_PROMPT = load_prompt(PRODUCTION_PROMPT_NAME)
# Ceiling for one response, thinking included. A summary is always shorter than its event,
# so this is a safety stop, not a target. Override per call with ``max_tokens=``.
DEFAULT_MAX_TOKENS = 16000


@dataclass(frozen=True)
class SummarizationResult:
    summary: str
    model: str
    prompt_tokens: int  # all input tokens: uncached + cache reads + cache writes
    completion_tokens: int
    cached_tokens: int  # input tokens served from the prompt cache
    latency_ms: float
    cache_write_tokens: int = 0  # input tokens written to the prompt cache

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class SummarizerError(RuntimeError):
    pass


class Summarizer:
    def __init__(
        self,
        api_key: str,
        base_url: str | None = None,
        timeout: float = 60.0,
        max_retries: int = 5,
    ):
        if not api_key:
            raise SummarizerError("Summarizer requires an API key")
        try:
            import anthropic  # noqa: PLC0415 - lazy: anthropic is an optional ('ai' / 'ai-eval') dependency
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise SummarizerError(
                "The 'anthropic' package is required for summarization. Install it via the 'ai' "
                "optional dependency group (production worker) or 'ai-eval' (evaluation harness)."
            ) from exc

        client_kwargs: dict[str, Any] = {
            "api_key": api_key,
            "timeout": timeout,
            "max_retries": max_retries,
        }
        if base_url:
            client_kwargs["base_url"] = base_url
        self._client = anthropic.Anthropic(**client_kwargs)

    def _create(self, model: str, system: str, user: str, **params: Any) -> tuple[Any, str]:
        """One Messages API call. Returns the response and its concatenated text.
        ``params`` go to the API verbatim (``thinking``, ``output_config``, ``max_tokens``, ...)."""
        params.setdefault("max_tokens", DEFAULT_MAX_TOKENS)
        try:
            response = self._client.messages.create(
                model=model,
                # The system prompt is identical across events, so cache it. Below the model's
                # minimum cacheable size the marker is a no-op.
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user}],
                **params,
            )
        except Exception as exc:  # noqa: BLE001 - provider raises a wide variety
            raise SummarizerError(f"API call failed for model {model}: {exc}") from exc
        if response.stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            category = getattr(details, "category", None)
            raise SummarizerError(f"Model {model} refused the request (category={category})")
        if response.stop_reason == "max_tokens":
            raise SummarizerError(f"Model {model} hit max_tokens={params['max_tokens']}; output truncated")
        text = "".join(block.text for block in response.content if block.type == "text").strip()
        return response, text

    def summarize(
        self,
        model: str,
        message: str,
        prompt: str = DEFAULT_PROMPT,
        **params: Any,
    ) -> SummarizationResult:
        if not message:
            raise SummarizerError("Cannot summarize an empty message")

        started = time.monotonic()
        response, summary = self._create(model, prompt, message, **params)
        latency_ms = (time.monotonic() - started) * 1000.0
        if not summary:
            raise SummarizerError(f"Model {model} returned an empty summary")

        usage = response.usage
        uncached = usage.input_tokens or 0
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
        cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
        result = SummarizationResult(
            summary=summary,
            model=model,
            prompt_tokens=uncached + cache_read + cache_write,
            completion_tokens=usage.output_tokens or 0,
            cached_tokens=cache_read,
            latency_ms=latency_ms,
            cache_write_tokens=cache_write,
        )
        LOGGER.debug(
            "Summarized with %s: %d->%d tokens (%d cached) in %.0fms",
            model,
            result.prompt_tokens,
            result.completion_tokens,
            result.cached_tokens,
            latency_ms,
        )
        return result

    def raw_completion(self, model: str, system: str, user: str, **params: Any) -> str:
        return self._create(model, system, user, **params)[1]
