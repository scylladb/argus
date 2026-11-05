"""Regression baseline: freeze the current winner's aggregate scores, then check a later
run against them.

Why aggregate-and-tolerance instead of a golden results.json: both the summarizer and the
judge are non-deterministic, so cost, latency, and judge scores drift run to run. An
exact-match baseline would fail on noise and get ignored. Instead we store the per-series
means (from ``metrics.aggregate_series``) and, on compare, fail only when the two axes that
mean *information was lost* — faithfulness and coverage — drop by more than ``tolerance``
points. Conciseness, cost, and latency are tradeoffs: shown as deltas, never a failure.

Comparison is only meaningful on identical inputs, so ``--baseline`` forces the run onto the
frozen ``events.json`` stored beside ``baseline.json``.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .metrics import SeriesStats, aggregate_series

BASELINE_FILE = "baseline.json"
EVENTS_FILE = "events.json"

# Judge axes that gate the verdict — a drop here means dropped/invented information.
_GATED = ("avg_faithfulness", "avg_coverage")
# Field-aware rounding for the stored file. Judge means round hard (1 dp) so sub-point noise
# doesn't churn the committed baseline; cost is ~$0.002/cell so it needs 6 dp or it flattens
# to zero. Default 1 dp for anything not listed.
_ROUND = {
    "avg_coverage": 1,
    "avg_faithfulness": 1,
    "avg_conciseness": 1,
    "avg_overall": 1,
    "avg_compression": 3,
    "avg_cost": 6,
    "avg_latency_ms": 0,
    "avg_completion_tokens": 1,
}


def _round(stats: SeriesStats) -> dict:
    d = asdict(stats)
    return {k: (round(v, _ROUND.get(k, 1)) if isinstance(v, float) else v) for k, v in d.items()}


def serialize_baseline(results: dict, tolerance: float) -> dict:
    """Build the committed baseline document from a results dict (fresh or loaded)."""
    series, multi_prompt = aggregate_series(results)
    return {
        "generated_at": results.get("generated_at"),
        "judge_model": results.get("judge_model"),
        "num_events": results.get("num_events"),
        "tolerance": tolerance,
        "multi_prompt": multi_prompt,
        "series": [_round(s) for s in sorted(series, key=lambda s: s.key)],
    }


def save_baseline(results: dict, out_dir: Path, tolerance: float) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / BASELINE_FILE
    path.write_text(json.dumps(serialize_baseline(results, tolerance), indent=2), encoding="utf-8")
    return path


def load_baseline(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _fmt_delta(cur: float, base: float) -> str:
    d = cur - base
    return f"{cur:5.1f} ({d:+.1f})"


def compare(results: dict, baseline: dict, tolerance: float) -> tuple[list[dict], bool]:
    """Diff a fresh run against a stored baseline, series by series (matched on key).

    Returns (rows, ok). ok is False if any shared series regressed on a gated axis, or a
    baseline series is missing from the run. New series (in the run, not the baseline) are
    reported but never fail — you can't regress against a baseline that doesn't exist yet.
    """
    current = {s.key: s for s in aggregate_series(results)[0]}
    base_by_key = {b["key"]: b for b in baseline.get("series", [])}
    rows: list[dict] = []
    ok = True

    for key in sorted(base_by_key):
        base = base_by_key[key]
        cur = current.get(key)
        if cur is None:
            rows.append({"key": key, "status": "MISSING", "detail": "series absent from this run"})
            ok = False
            continue
        regressions = []
        for axis in _GATED:
            drop = base[axis] - getattr(cur, axis)
            if drop > tolerance:
                regressions.append(f"{axis.removeprefix('avg_')} -{drop:.1f}")
        # Dropped-critical / hallucination counts are informational, but a new hallucination
        # where there was none is worth shouting about even inside tolerance.
        halluc_delta = cur.total_hallucinations - base["total_hallucinations"]
        dropped_delta = cur.total_dropped - base["total_dropped"]
        row = {
            "key": key,
            "status": "PASS" if not regressions else "FAIL",
            "faith": _fmt_delta(cur.avg_faithfulness, base["avg_faithfulness"]),
            "cover": _fmt_delta(cur.avg_coverage, base["avg_coverage"]),
            "concise": _fmt_delta(cur.avg_conciseness, base["avg_conciseness"]),
            "cost": _fmt_delta(cur.avg_cost * 100, base["avg_cost"] * 100),  # cents/cell
            "halluc_delta": halluc_delta,
            "dropped_delta": dropped_delta,
            "detail": ", ".join(regressions),
        }
        if regressions:
            ok = False
        rows.append(row)

    for key in sorted(set(current) - set(base_by_key)):
        rows.append({"key": key, "status": "NEW", "detail": "no baseline entry (not gated)"})
    return rows, ok


def render_table(rows: list[dict], baseline: dict, tolerance: float) -> str:
    """Human-readable delta table for the terminal. Numbers are current (Δ vs baseline)."""
    head = (
        f"Baseline: {baseline.get('num_events')} events, judge={baseline.get('judge_model')}, "
        f"generated {baseline.get('generated_at')}\nTolerance: {tolerance:.1f} pts on faithfulness & coverage "
        f"(cost in cents/cell; hall/drop deltas informational)\n"
    )
    lines = [head, f"{'series':<34}{'faith':>13}{'cover':>13}{'concise':>13}{'cost':>13}  verdict"]
    lines.append("-" * 104)
    for r in rows:
        if r["status"] in ("MISSING", "NEW"):
            lines.append(f"{r['key']:<34}{'':>52}  {r['status']}: {r['detail']}")
            continue
        flags = ""
        if r["halluc_delta"] > 0:
            flags += f" +{r['halluc_delta']}halluc"
        if r["dropped_delta"] > 0:
            flags += f" +{r['dropped_delta']}drop"
        verdict = r["status"] + (f" ({r['detail']})" if r["detail"] else "") + flags
        lines.append(f"{r['key']:<34}{r['faith']:>13}{r['cover']:>13}{r['concise']:>13}{r['cost']:>13}  {verdict}")
    return "\n".join(lines)
