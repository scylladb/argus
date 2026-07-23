"""Orchestrator: events × models × prompts → summaries → judge → results.json.

The unit of work is one (event, model, prompt) triple. All triples are independent, so
they run on a bounded thread pool (``max_concurrency``) — the same rate-limit guard the
production worker uses. A failed triple is recorded with its error and never aborts the
sweep, so one flaky model or one oversized event can't sink a whole run.
"""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import tiktoken

from argusAI.utils.summarizer import Summarizer, SummarizerError

from .config import EvalConfig, ModelSpec
from .events_source import EventFetcher, EventSample, load_events, save_events
from .judge import Judge
from .pricing import PricingBook
from .results import CellResult, JudgeScore

LOGGER = logging.getLogger(__name__)

_ENCODERS: dict[str, tiktoken.Encoding] = {}


def _count_tokens(model: str, text: str) -> int:
    """Token count under the model's encoding, so compression is measured in the unit we pay for.
    Falls back to o200k_base (GPT-4o/5 family) for models tiktoken does not yet know."""
    if not text:
        return 0
    enc = _ENCODERS.get(model)
    if enc is None:
        try:
            enc = tiktoken.encoding_for_model(model)
        except KeyError:
            enc = tiktoken.get_encoding("o200k_base")
        _ENCODERS[model] = enc
    return len(enc.encode(text))


class EvalHarness:
    def __init__(self, config: EvalConfig):
        self.cfg = config
        self.summarizer = Summarizer(
            api_key=config.api_key,
            base_url=config.openai_base_url,
            timeout=config.request_timeout,
        )
        self.pricing = PricingBook(config.pricing)
        self.judge = Judge(self.summarizer, config.judge_model, config.judge_params)

    # -- data ---------------------------------------------------------------
    def gather_events(self) -> list[EventSample]:
        if self.cfg.events_file and Path(self.cfg.events_file).exists():
            events = load_events(Path(self.cfg.events_file))
            LOGGER.info("Loaded %d events from %s", len(events), self.cfg.events_file)
            if self.cfg.max_events:
                events = events[: self.cfg.max_events]
            return self._maybe_dedup(events)
        fetcher = EventFetcher(argus_cli=self.cfg.argus_cli, no_cache=self.cfg.no_cache)
        events = fetcher.collect(
            run_ids=self.cfg.run_ids,
            test_id=self.cfg.test_id,
            test_run_limit=self.cfg.test_run_limit,
            max_events=self.cfg.max_events,
        )
        events = self._maybe_dedup(events)
        if events:
            save_events(events, self.cfg.output_dir / "events.json")
        return events

    def _maybe_dedup(self, events: list[EventSample]) -> list[EventSample]:
        """Collapse semantically-similar events (mirrors production) when enabled."""
        if not self.cfg.similarity_dedup:
            return events
        from .dedup import deduplicate_by_similarity  # noqa: PLC0415 - lazy: pulls in chromadb, an optional ('ai-eval') dep

        return deduplicate_by_similarity(events, self.cfg.similarity_threshold)

    # -- one cell -----------------------------------------------------------
    def _summarize_cell(self, event: EventSample, model: ModelSpec, prompt_name: str, prompt: str) -> CellResult:
        cell = CellResult(
            event_key=event.key(),
            run_id=event.run_id,
            event_type=event.event_type,
            node=event.node,
            severity=event.severity,
            model=model.name,
            model_label=model.display,
            prompt_name=prompt_name,
            input_chars=event.message_chars,
            summary_chars=0,
            input_tokens=_count_tokens(model.name, event.message),
        )
        try:
            res = self.summarizer.summarize(model.name, event.message, prompt=prompt, **model.params)
        except SummarizerError as exc:
            cell.error = str(exc)
            LOGGER.warning("summarize failed [%s/%s]: %s", model.name, prompt_name, exc)
            return cell
        cell.summary = res.summary
        cell.summary_chars = len(res.summary)
        cell.summary_tokens = _count_tokens(model.name, res.summary)
        cell.prompt_tokens = res.prompt_tokens
        cell.completion_tokens = res.completion_tokens
        cell.cached_tokens = res.cached_tokens
        cell.latency_ms = res.latency_ms
        cell.cost_usd = self.pricing.cost(model.name, res.prompt_tokens, res.completion_tokens, res.cached_tokens)
        if self.cfg.judge_enabled:
            # Judge.score never raises; the guard is belt-and-suspenders so one bad judge
            # can't sink the sweep even if that contract regresses.
            try:
                cell.judge = self.judge.score(event.message, res.summary)
            except Exception as exc:  # noqa: BLE001
                cell.judge = JudgeScore(error=f"judge crashed: {exc}")
                LOGGER.warning("judge crashed [%s/%s]: %s", model.name, prompt_name, exc)
        return cell

    # -- sweep --------------------------------------------------------------
    def run(self) -> dict:
        events = self.gather_events()
        if not events:
            raise RuntimeError(
                "No events to evaluate. Provide run_ids/test_id that have ERROR/CRITICAL "
                "events with retained message bodies, or point events_file at a saved set."
            )
        prompts = self.cfg.resolved_prompts()
        jobs = [
            (event, model, pname, ptext)
            for event in events
            for model in self.cfg.models
            for pname, ptext in prompts.items()
        ]
        LOGGER.info(
            "Sweeping %d events × %d models × %d prompts = %d cells (concurrency %d)",
            len(events),
            len(self.cfg.models),
            len(prompts),
            len(jobs),
            self.cfg.max_concurrency,
        )
        cells: list[CellResult] = []
        out_path = self.cfg.output_dir / "results.json"

        def _persist() -> dict:
            results = {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "prompts": prompts,
                "models": [m.display for m in self.cfg.models],
                "judge_model": self.cfg.judge_model if self.cfg.judge_enabled else None,
                "num_events": len(events),
                "unknown_priced_models": sorted({m.name for m in self.cfg.models if not self.pricing.has(m.name)}),
                "default_priced_models": sorted({m.name for m in self.cfg.models if self.pricing.is_default(m.name)}),
                "events": [e.to_dict() for e in events],
                "cells": [c.to_dict() for c in cells],
            }
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
            return results

        # Persist whatever completed even on Ctrl-C / unexpected crash, so paid API calls
        # already made are never lost (the per-cell paths above already can't raise).
        done = 0
        try:
            with ThreadPoolExecutor(max_workers=self.cfg.max_concurrency) as pool:
                futures = {pool.submit(self._summarize_cell, *job): job for job in jobs}
                for future in as_completed(futures):
                    try:
                        cells.append(future.result())
                    except Exception as exc:  # noqa: BLE001 - belt-and-suspenders
                        LOGGER.error("cell task raised unexpectedly, skipping: %s", exc)
                    done += 1
                    if done % 10 == 0 or done == len(jobs):
                        LOGGER.info("  %d/%d cells done", done, len(jobs))
        finally:
            results = _persist()
            LOGGER.info("Wrote %d cells to %s", len(cells), out_path)
        return results
