"""Evaluation config: which models, which prompts, which events, and the API key.

Everything the design mandates be configurable (model + key, plus the prompt) lives
here. The key is never written to the config file — it comes from the ``OPENAI_API_KEY``
environment variable (or ``openai_api_key_env`` naming a different var), matching the
existing ``*_TOKEN``/``*_SECRET`` secret conventions and keeping keys out of git.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .prompts import DEFAULT_PROMPT_NAME, PROMPTS


@dataclass
class ModelSpec:
    """One candidate to evaluate. ``params`` is passed straight to the API call, so a
    reasoning model can get ``reasoning_effort`` and a classic model ``temperature``
    without special-casing anywhere in the code."""

    name: str
    params: dict[str, Any] = field(default_factory=dict)
    label: str | None = None

    @property
    def display(self) -> str:
        return self.label or self.name


@dataclass
class EvalConfig:
    # --- what to summarize ---
    run_ids: list[str] = field(default_factory=list)
    test_id: str | None = None
    test_run_limit: int = 20
    max_events: int | None = 30
    events_file: Path | None = None  # reuse a saved events.json instead of refetching
    similarity_dedup: bool = False  # collapse semantically-similar events (mirrors production)
    similarity_threshold: float = 0.05  # cosine distance; matches the worker

    # --- how to summarize ---
    models: list[ModelSpec] = field(default_factory=list)
    prompt_names: list[str] = field(default_factory=lambda: [DEFAULT_PROMPT_NAME])

    # --- judging ---
    judge_enabled: bool = True
    judge_model: str = "gpt-5"
    judge_params: dict[str, Any] = field(default_factory=dict)

    # --- provider / secrets ---
    openai_api_key_env: str = "OPENAI_API_KEY"
    openai_base_url: str | None = None
    request_timeout: float = 90.0
    max_concurrency: int = 4

    # --- infra ---
    argus_cli: str | None = None
    no_cache: bool = False
    output_dir: Path = Path("argusAI/eval/out")
    pricing: dict[str, dict] = field(default_factory=dict)

    @property
    def api_key(self) -> str:
        key = os.environ.get(self.openai_api_key_env, "")
        if not key:
            raise RuntimeError(
                f"No API key found in environment variable '{self.openai_api_key_env}'. "
                f"Export it, e.g.: export {self.openai_api_key_env}=sk-..."
            )
        return key

    def resolved_prompts(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for name in self.prompt_names:
            if name not in PROMPTS:
                raise KeyError(f"Unknown prompt '{name}'. Known: {sorted(PROMPTS)}")
            out[name] = PROMPTS[name]
        return out

    @classmethod
    def from_yaml(cls, path: str | Path) -> "EvalConfig":
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, raw: dict) -> "EvalConfig":
        models = [
            ModelSpec(
                name=m["name"] if isinstance(m, dict) else m,
                params=(m.get("params", {}) if isinstance(m, dict) else {}),
                label=(m.get("label") if isinstance(m, dict) else None),
            )
            for m in raw.get("models", [])
        ]
        displays = [m.display for m in models]
        collisions = sorted({d for d in displays if displays.count(d) > 1})
        if collisions:
            raise ValueError(
                f"Duplicate model display name(s): {', '.join(collisions)}. Give each entry a distinct "
                "'label' so configs of the same model (e.g. different params) don't merge into one series."
            )
        cfg = cls(
            run_ids=list(raw.get("run_ids", [])),
            test_id=raw.get("test_id"),
            test_run_limit=int(raw.get("test_run_limit", 20)),
            max_events=raw.get("max_events", 30),
            events_file=(Path(raw["events_file"]) if raw.get("events_file") else None),
            similarity_dedup=bool(raw.get("similarity_dedup", False)),
            similarity_threshold=float(raw.get("similarity_threshold", 0.05)),
            models=models,
            prompt_names=list(raw.get("prompts", [DEFAULT_PROMPT_NAME])),
            judge_enabled=bool(raw.get("judge_enabled", True)),
            judge_model=raw.get("judge_model", "gpt-5"),
            judge_params=dict(raw.get("judge_params", {})),
            openai_api_key_env=raw.get("openai_api_key_env", "OPENAI_API_KEY"),
            openai_base_url=raw.get("openai_base_url"),
            request_timeout=float(raw.get("request_timeout", 90.0)),
            max_concurrency=int(raw.get("max_concurrency", 4)),
            argus_cli=raw.get("argus_cli"),
            no_cache=bool(raw.get("no_cache", False)),
            output_dir=Path(raw.get("output_dir", "argusAI/eval/out")),
            pricing=dict(raw.get("pricing", {})),
        )
        if not cfg.models:
            raise ValueError("Config must list at least one model under 'models'")
        return cfg
