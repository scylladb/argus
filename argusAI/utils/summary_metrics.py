"""Prometheus metrics for the event-summarization worker.

The similarity worker runs as its own process (not under uWSGI), so it exposes its own
scrape endpoint via prometheus_client instead of the Flask exporter. Series are labeled by
`model` so production behaviour lines up directly against the offline eval sweep in
argusAI/eval: input/output token sizes, compression ratio, latency and volume are the same
axes the harness reports, letting you check whether a model that won on the eval set behaves
the same on live traffic (and re-baseline when the model or prompt changes).
"""

from __future__ import annotations

import logging

from prometheus_client import Counter, Histogram, start_http_server

LOGGER = logging.getLogger(__name__)

_NS = "argus_event_summarization"

# Outcome tally — `outcome` is one of ok/failed/dropped. `severity` (ERROR/CRITICAL) is
# bounded, so it stays on the counter for triage slicing without cardinality worry.
SUMMARIES = Counter(
    f"{_NS}_total",
    "Event summarizations attempted, by outcome.",
    ["model", "severity", "outcome"],
)

# Input size fed to the summarizer, in tokens — compare the live event-size distribution
# against the eval set the winner was chosen on.
INPUT_TOKENS = Histogram(
    f"{_NS}_input_tokens",
    "Original event size in tokens (summarizer input).",
    ["model"],
    buckets=(100, 250, 500, 1000, 2000, 4000, 8000, 16000, float("inf")),
)

OUTPUT_TOKENS = Histogram(
    f"{_NS}_output_tokens",
    "Summary size in completion tokens.",
    ["model"],
    buckets=(50, 100, 200, 400, 800, 1600, 3200, float("inf")),
)

# Summary chars / original chars. <1 compressed, >1 expanded — the production stand-in for
# the eval's conciseness axis (the LLM-judge score can't be computed without the original).
COMPRESSION_RATIO = Histogram(
    f"{_NS}_compression_ratio",
    "Summary length / original length in chars (<1 compresses, >1 expands).",
    ["model"],
    buckets=(0.1, 0.25, 0.4, 0.5, 0.6, 0.75, 0.9, 1.0, 1.5, float("inf")),
)

LATENCY = Histogram(
    f"{_NS}_latency_seconds",
    "Summarization API call latency.",
    ["model"],
    buckets=(0.5, 1, 2, 4, 8, 16, 32, 64, float("inf")),
)

# Delay from the event's own timestamp to its summary being persisted — how fresh the
# summary is by the time a triager could read it.
LAG = Histogram(
    f"{_NS}_lag_seconds",
    "Delay from event timestamp to summary persisted.",
    ["model"],
    buckets=(1, 5, 15, 30, 60, 120, 300, 600, 1800, float("inf")),
)

CACHED_PROMPT_TOKENS = Counter(
    f"{_NS}_cached_prompt_tokens_total",
    "Prompt tokens served from the provider cache (cost signal).",
    ["model"],
)


def record_success(
    model: str,
    input_tokens: int,
    original_chars: int,
    summary_chars: int,
    completion_tokens: int,
    cached_tokens: int,
    latency_ms: float,
    lag_seconds: float,
) -> None:
    """Observe the per-summary distributions on a successful summarization."""
    if input_tokens:
        INPUT_TOKENS.labels(model).observe(input_tokens)
    OUTPUT_TOKENS.labels(model).observe(completion_tokens)
    if original_chars:
        COMPRESSION_RATIO.labels(model).observe(summary_chars / original_chars)
    LATENCY.labels(model).observe(latency_ms / 1000.0)
    LAG.labels(model).observe(lag_seconds)
    if cached_tokens:
        CACHED_PROMPT_TOKENS.labels(model).inc(cached_tokens)


def start_metrics_server(port: int) -> None:
    """Serve the default registry on `port` for Prometheus to scrape. Failures are logged
    and swallowed — metrics exposure must never take down the summarization worker."""
    try:
        start_http_server(port)
        LOGGER.info("Event summarization metrics exposed on :%d/metrics", port)
    except Exception as exc:  # noqa: BLE001 - metrics must never break the worker
        LOGGER.warning("Could not start summarization metrics server on :%d: %s", port, exc)
