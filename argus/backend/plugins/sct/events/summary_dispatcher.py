from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

import tiktoken

from argus.backend.plugins.sct.events import summary_metrics as metrics
from argus.backend.plugins.sct.events.prompts import load_prompt
from argus.backend.plugins.sct.events.summarizer import DEFAULT_PROMPT, Summarizer, SummarizerError
from argus.backend.plugins.sct.testrun import SCTEvent

LOGGER = logging.getLogger(__name__)

# Events under this many input tokens are already short enough to read in full, so a summary
# saves nothing. Operators override via EVENT_SUMMARIZATION_MIN_TOKENS; set 0 to summarize everything.
_DEFAULT_MIN_TOKENS = 150
_STATS_LOG_EVERY = 50  # emit a rolling aggregate line every N completed summarizations


@dataclass(frozen=True, slots=True)
class UniqueEvent:
    run_id: UUID
    severity: str
    ts: datetime
    message: str


def _resolve_encoder() -> tiktoken.Encoding:
    """Local tokenizer for the min-token gate. Claude's tokenizer is not public, so counts are an
    approximation; the eval harness measures with the same encoder so gate and sweep agree."""
    return tiktoken.get_encoding("o200k_base")


def _lag_seconds(ts: datetime) -> float:
    """Seconds from the event's timestamp to now — the summarization lag."""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - ts).total_seconds())


def _resolve_prompt(config: dict) -> str:
    inline = config.get("EVENT_SUMMARIZATION_PROMPT")
    if inline:
        return inline
    version = config.get("EVENT_SUMMARIZATION_PROMPT_VERSION") or os.environ.get("EVENT_SUMMARIZATION_PROMPT_VERSION")
    if version:
        try:
            return load_prompt(version)
        except FileNotFoundError as exc:
            LOGGER.warning("%s; falling back to the default prompt", exc)
    return DEFAULT_PROMPT


class SummaryDispatcher:
    def __init__(self, config: dict):
        self.model = config.get("ANTHROPIC_SUMMARY_MODEL", "claude-sonnet-5-5")
        # Effort steers the model's thinking depth. Summarization is extraction, so `low` holds
        # quality at a fraction of the output tokens. Empty disables the parameter for models
        # without effort support.
        effort = config.get("ANTHROPIC_SUMMARY_EFFORT", "low")
        self.model_params: dict = {"output_config": {"effort": effort}} if effort else {}
        self.prompt = _resolve_prompt(config)
        self.min_tokens = 0
        self.max_backlog = 0
        self._encoder: tiktoken.Encoding | None = None
        self._encoder_lock: asyncio.Lock | None = None
        self._semaphore: asyncio.Semaphore | None = None
        self._summarizer: Summarizer | None = None
        self._pending = 0
        self.enabled = False

        self._n_ok = 0
        self._n_failed = 0
        self._n_dropped = 0
        self._n_since_log = 0

        try:
            if not config.get("EVENT_SUMMARIZATION_ENABLED", False):
                raise ValueError("EVENT_SUMMARIZATION_ENABLED=false")
            self.min_tokens = int(config.get("EVENT_SUMMARIZATION_MIN_TOKENS", _DEFAULT_MIN_TOKENS))
            max_concurrency = int(config.get("EVENT_SUMMARIZATION_MAX_CONCURRENCY", 4))
            self.max_backlog = int(config.get("EVENT_SUMMARIZATION_MAX_BACKLOG", 1000))
            api_key = config.get("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError("ANTHROPIC_API_KEY is missing")
            self._summarizer = Summarizer(api_key=api_key, base_url=config.get("ANTHROPIC_BASE_URL"))
            self._semaphore = asyncio.Semaphore(max_concurrency)
            self._encoder_lock = asyncio.Lock()
        except Exception as exc:  # noqa: BLE001 - summarization setup must never break event processing
            LOGGER.info("Event summarization disabled: %s", exc)
            return

        self.enabled = True
        LOGGER.info(
            "Event summarization enabled (model=%s, params=%s, concurrency=%d, max_backlog=%d, min_tokens=%d)",
            self.model,
            self.model_params,
            max_concurrency,
            self.max_backlog,
            self.min_tokens,
        )

    async def summarize(self, events: list[UniqueEvent]) -> None:
        if not self.enabled:
            return
        await asyncio.gather(*(self._summarize_one(event) for event in events))

    async def _get_encoder(self) -> tiktoken.Encoding:
        """Input tokens are counted once per event for both the gate and the input-size metric.
        tiktoken may download the encoding on first use, so it loads off the event loop, on the
        first summary rather than when the worker starts."""
        async with self._encoder_lock:
            if self._encoder is None:
                self._encoder = await asyncio.to_thread(_resolve_encoder)
        return self._encoder

    async def _summarize_one(self, event: UniqueEvent) -> None:
        if not event.message:
            return
        try:
            encoder = await self._get_encoder()
        except Exception as exc:  # noqa: BLE001 - a summary is best effort and never fails the caller
            self._bump("failed", event.severity)
            LOGGER.warning("Could not load the token encoder; skipping run_id=%s ts=%s: %s", event.run_id, event.ts, exc)
            return
        input_tokens = len(encoder.encode(event.message))
        if input_tokens < self.min_tokens:
            return
        if self._pending >= self.max_backlog:
            self._bump("dropped", event.severity)
            LOGGER.warning("Summarization backlog full; dropping run_id=%s ts=%s", event.run_id, event.ts)
            return
        self._pending += 1
        try:
            async with self._semaphore:
                result = await asyncio.to_thread(
                    self._summarizer.summarize, self.model, event.message, prompt=self.prompt, **self.model_params
                )
            await SCTEvent.find(run_id=event.run_id, severity=event.severity, ts=event.ts).update(
                summary=result.summary
            )
            lag = _lag_seconds(event.ts)
            self._bump("ok", event.severity)
            metrics.record_success(
                self.model,
                input_tokens,
                len(event.message),
                len(result.summary),
                result.completion_tokens,
                result.cached_tokens,
                result.latency_ms,
                lag,
            )
            LOGGER.info(
                "Summarized run_id=%s severity=%s ts=%s: %d->%d chars, %d->%d tok (%d cached), %.0fms, lag=%.1fs",
                event.run_id,
                event.severity,
                event.ts,
                len(event.message),
                len(result.summary),
                result.prompt_tokens,
                result.completion_tokens,
                result.cached_tokens,
                result.latency_ms,
                lag,
            )
        except SummarizerError as exc:
            self._bump("failed", event.severity)
            LOGGER.warning("Summarization failed run_id=%s ts=%s: %s", event.run_id, event.ts, exc)
        except Exception as exc:  # noqa: BLE001 - a summary is best effort and never fails the caller
            self._bump("failed", event.severity)
            LOGGER.error("Summarize/store error run_id=%s ts=%s: %s", event.run_id, event.ts, exc, exc_info=True)
        finally:
            self._pending -= 1

    def _bump(self, kind: str, severity: str) -> None:
        """Increment an aggregate counter and emit a rolling tally every _STATS_LOG_EVERY events."""
        metrics.SUMMARIES.labels(self.model, severity, kind).inc()
        if kind == "ok":
            self._n_ok += 1
        elif kind == "failed":
            self._n_failed += 1
        elif kind == "dropped":
            self._n_dropped += 1
        self._n_since_log += 1
        if self._n_since_log >= _STATS_LOG_EVERY:
            self._n_since_log = 0
            LOGGER.info(
                "Summarization totals: %d ok, %d failed, %d dropped (backlog full)",
                self._n_ok,
                self._n_failed,
                self._n_dropped,
            )
