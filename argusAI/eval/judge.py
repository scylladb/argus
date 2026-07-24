"""LLM-as-judge: score one summary against its original event.

Everything about judging lives here — the prompt, the call, and the tolerant parsing of
the model's JSON reply — so the concept is one cohesive unit rather than being smeared
across the orchestrator and the prompt module.

A frontier model scores each candidate summary against the ORIGINAL event (not against a
reference summary): the question is "did we lose information?", which the original answers
directly, without a second layer of model opinion.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from argusAI.prompts import JUDGE_PROMPT_NAME, load_prompt
from argusAI.utils.summarizer import Summarizer, SummarizerError

from .results import JudgeScore

LOGGER = logging.getLogger(__name__)

JUDGE_SYSTEM = load_prompt(JUDGE_PROMPT_NAME)


def _judge_user(original: str, summary: str) -> str:
    return f"=== ORIGINAL EVENT ===\n{original}\n\n=== CANDIDATE SUMMARY ===\n{summary}\n\nScore it."


def _coerce_score(value: object) -> int | None:
    """Coerce a judge-supplied score to int without ever raising, or None when the field is
    absent or non-numeric — models sometimes return null, "85", or "high". None lets the
    caller tell a real 0 apart from a missing score."""
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        try:
            return int(float(value))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None


def _to_int(value: object, default: int = 0) -> int:
    parsed = _coerce_score(value)
    return parsed if parsed is not None else default


def _as_str_list(value: object) -> list[str]:
    """Coerce a judge-supplied list field to list[str]; tolerate a bare scalar or null."""
    if isinstance(value, list):
        return [str(x) for x in value]
    if value in (None, "", 0):
        return []
    return [str(value)]


def parse_judge(raw: str) -> JudgeScore:
    """Judge models are asked for bare JSON but sometimes wrap it or add trailing prose.
    Decode the first JSON object and ignore anything after it; never raise — a bad judge
    response must degrade to JudgeScore(error=...), not abort the sweep."""
    start = raw.find("{")
    if start == -1:
        return JudgeScore(error=f"no JSON in judge output: {raw[:120]}")
    try:
        # raw_decode stops at the end of the first value, so trailing text (or braces
        # inside string values) can't over-capture the way a greedy regex would.
        data, _ = json.JSONDecoder().raw_decode(raw[start:])
    except json.JSONDecodeError as exc:
        return JudgeScore(error=f"judge JSON parse failed: {exc}")
    if not isinstance(data, dict):
        return JudgeScore(error=f"judge JSON was not an object: {type(data).__name__}")
    scores = {field: _coerce_score(data.get(field)) for field in ("coverage", "faithfulness", "conciseness")}
    if all(v is None for v in scores.values()):
        # An object with no usable numeric score is an unjudged cell, not a genuine 0 —
        # scoring it 0 would drag the model's average down instead of excluding it.
        return JudgeScore(error=f"judge returned no numeric scores: {raw[start : start + 120]}")
    return JudgeScore(
        coverage=scores["coverage"] or 0,
        faithfulness=scores["faithfulness"] or 0,
        conciseness=scores["conciseness"] or 0,
        dropped_critical=_as_str_list(data.get("dropped_critical")),
        hallucinations=_as_str_list(data.get("hallucinations")),
        verdict=str(data.get("verdict", "")),
    )


class Judge:
    """Scores summaries with one frontier model. Reuses the harness's Summarizer client so
    there's a single OpenAI connection for the whole sweep."""

    def __init__(self, summarizer: Summarizer, model: str, params: dict[str, Any] | None = None):
        self._summarizer = summarizer
        self._model = model
        self._params = params or {}

    def score(self, original: str, summary: str) -> JudgeScore:
        """Never raises: a provider error or unparseable reply becomes JudgeScore(error=...)."""
        try:
            raw = self._summarizer.raw_completion(
                self._model, JUDGE_SYSTEM, _judge_user(original, summary), **self._params
            )
        except SummarizerError as exc:
            return JudgeScore(error=str(exc))
        return parse_judge(raw)
