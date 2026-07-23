from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from argusAI.prompts import PRODUCTION_PROMPT_NAME, load_prompt

LOGGER = logging.getLogger(__name__)

DEFAULT_PROMPT = load_prompt(PRODUCTION_PROMPT_NAME)


@dataclass(frozen=True)
class SummarizationResult:
    summary: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int
    latency_ms: float

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
            from openai import OpenAI  # noqa: PLC0415 - lazy: openai is an optional ('ai' / 'ai-eval') dependency
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise SummarizerError(
                "The 'openai' package is required for summarization. Install it via the 'ai' "
                "optional dependency group (production worker) or 'ai-eval' (evaluation harness)."
            ) from exc

        client_kwargs: dict[str, Any] = {
            "api_key": api_key,
            "timeout": timeout,
            "max_retries": max_retries,
        }
        if base_url:
            client_kwargs["base_url"] = base_url
        self._client = OpenAI(**client_kwargs)

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
        try:
            response = self._client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": message},
                ],
                **params,
            )
        except Exception as exc:  # noqa: BLE001 - provider raises a wide variety
            raise SummarizerError(f"Summarization call failed for model {model}: {exc}") from exc
        latency_ms = (time.monotonic() - started) * 1000.0

        summary = (response.choices[0].message.content or "").strip()
        if not summary:
            raise SummarizerError(f"Model {model} returned an empty summary")

        usage = getattr(response, "usage", None)
        prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
        completion_tokens = getattr(usage, "completion_tokens", 0) or 0
        cached_tokens = 0
        details = getattr(usage, "prompt_tokens_details", None)
        if details is not None:
            cached_tokens = getattr(details, "cached_tokens", 0) or 0

        result = SummarizationResult(
            summary=summary,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cached_tokens=cached_tokens,
            latency_ms=latency_ms,
        )
        LOGGER.debug(
            "Summarized with %s: %d->%d tokens (%d cached) in %.0fms",
            model,
            prompt_tokens,
            completion_tokens,
            cached_tokens,
            latency_ms,
        )
        return result

    def raw_completion(self, model: str, system: str, user: str, **params: Any) -> str:
        try:
            response = self._client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                **params,
            )
        except Exception as exc:  # noqa: BLE001
            raise SummarizerError(f"Completion call failed for model {model}: {exc}") from exc
        return (response.choices[0].message.content or "").strip()
