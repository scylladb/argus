"""Aggregation over result cells — the analysis layer between raw cells and the report.

One place computes means over judge fields, so the charts, the summary table, and the
per-prompt breakdown all agree. Everything here reads the serialized cell dicts (as loaded
from results.json), not live objects, so it works equally on a fresh sweep or a saved run.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from statistics import mean


@dataclass
class SeriesStats:
    """Aggregated metrics for one series (a model, or a model·prompt pair)."""

    key: str
    model: str
    prompt_name: str
    n: int
    errors: int
    avg_coverage: float
    avg_faithfulness: float
    avg_conciseness: float
    avg_overall: float
    avg_cost: float
    avg_compression: float
    avg_latency_ms: float
    avg_completion_tokens: float
    # Token accounting: input = original event tokens, summary = tokens in the stored summary,
    # saved = input - summary (what a downstream reader no longer has to ingest).
    avg_input_tokens: float
    avg_summary_tokens: float
    avg_tokens_saved: float
    total_input_tokens: int
    total_summary_tokens: int
    total_tokens_saved: int
    savings_pct: float
    total_dropped: int
    total_hallucinations: int


def _judged_avg(cells: list[dict], field: str) -> float:
    """Average one judge field over every successfully-judged cell (skips errored/unjudged);
    0.0 when nothing was judged."""
    vals = [float(c["judge"].get(field, 0)) for c in cells if c.get("judge") and c["judge"].get("error") is None]
    return mean(vals) if vals else 0.0


def _count(cells: list[dict], field: str) -> int:
    return sum(len((c.get("judge") or {}).get(field, []) or []) for c in cells)


def _avg(cells: list[dict], field: str, default: float = 0.0) -> float:
    vals = [c.get(field, default) for c in cells]
    return mean(vals) if vals else default


def _series_stats(key: str, model: str, prompt_name: str, cells: list[dict]) -> SeriesStats:
    ok = [c for c in cells if not c.get("error")]
    total_input = sum(c.get("input_tokens", 0) for c in ok)
    total_summary = sum(c.get("summary_tokens", 0) for c in ok)
    total_saved = total_input - total_summary
    return SeriesStats(
        key=key,
        model=model,
        prompt_name=prompt_name,
        n=len(ok),
        errors=len(cells) - len(ok),
        avg_coverage=_judged_avg(ok, "coverage"),
        avg_faithfulness=_judged_avg(ok, "faithfulness"),
        avg_conciseness=_judged_avg(ok, "conciseness"),
        avg_overall=_judged_avg(ok, "overall"),
        avg_cost=_avg(ok, "cost_usd"),
        avg_compression=_avg(ok, "compression_ratio"),
        avg_latency_ms=_avg(ok, "latency_ms"),
        avg_completion_tokens=_avg(ok, "completion_tokens"),
        avg_input_tokens=_avg(ok, "input_tokens"),
        avg_summary_tokens=_avg(ok, "summary_tokens"),
        avg_tokens_saved=_avg(ok, "input_tokens") - _avg(ok, "summary_tokens"),
        total_input_tokens=total_input,
        total_summary_tokens=total_summary,
        total_tokens_saved=total_saved,
        savings_pct=(total_saved / total_input * 100) if total_input else 0.0,
        total_dropped=_count(ok, "dropped_critical"),
        total_hallucinations=_count(ok, "hallucinations"),
    )


def aggregate_series(results: dict) -> tuple[list[SeriesStats], bool]:
    """Group cells into series (model, or model·prompt when several prompts are present),
    best-overall first. Returns (stats, multi_prompt)."""
    cells = results.get("cells", [])
    multi_prompt = len({c["prompt_name"] for c in cells}) > 1
    buckets: dict[str, list[dict]] = defaultdict(list)
    labels: dict[str, tuple[str, str]] = {}
    for c in cells:
        model = c.get("model_label") or c["model"]
        key = f"{model} · {c['prompt_name']}" if multi_prompt else model
        buckets[key].append(c)
        labels[key] = (model, c["prompt_name"])

    stats = [_series_stats(key, *labels[key], cs) for key, cs in buckets.items()]
    stats.sort(key=lambda s: s.avg_overall, reverse=True)
    return stats, multi_prompt


def prompt_stat_line(cells: list[dict]) -> tuple[str, float]:
    """(display stat, sort key) for one prompt's scored cells; sort key -1 when unscored."""
    if not cells:
        return "not scored in this run", -1.0
    q = mean(c["judge"]["overall"] for c in cells)
    stat = (
        f"Q {q:.1f} · coverage {mean(c['judge']['coverage'] for c in cells):.0f} · "
        f"faithful {mean(c['judge']['faithfulness'] for c in cells):.0f} · "
        f"size {mean(c['compression_ratio'] for c in cells) * 100:.0f}% of original · "
        f"{_count(cells, 'dropped_critical')} dropped · "
        f"{_count(cells, 'hallucinations')} hallucinated"
    )
    return stat, q
