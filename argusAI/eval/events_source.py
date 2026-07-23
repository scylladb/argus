"""Pull real SCT ERROR/CRITICAL events out of Argus via the ``argus`` CLI.

We shell out to the CLI rather than talking to ScyllaDB directly so the harness can
run anywhere the operator's CLI is already authenticated (keychain creds), with no DB
credentials, no Flask config, and no VPN to the cluster. It is exactly the interface a
human uses to look at a run, which keeps the evaluation honest about what data is
actually reachable.

Only the canonical (deduplicated) events are summarized in production — the CLI
already deduplicates server-side (``run events`` collapses repeats into
``repeated_at``), so what we fetch here mirrors the production input set.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

LOGGER = logging.getLogger(__name__)


def _resolve_cli(explicit: str | None) -> str:
    """Locate the argus binary: explicit override, then PATH, then ~/bin/argus."""
    if explicit:
        return explicit
    on_path = shutil.which("argus")
    if on_path:
        return on_path
    fallback = Path.home() / "bin" / "argus"
    if fallback.exists():
        return str(fallback)
    raise FileNotFoundError(
        "Could not find the 'argus' CLI on PATH or at ~/bin/argus. Set 'argus_cli' in the eval config to its full path."
    )


@dataclass
class EventSample:
    """One event to summarize, plus the provenance needed to trace it back to Argus."""

    run_id: str
    severity: str
    event_type: str
    node: str
    ts: str
    message: str
    repeats: int = 0

    @property
    def message_chars(self) -> int:
        return len(self.message)

    def key(self) -> str:
        """Dedup key: identical message text is the same summarization input, no matter
        which run surfaced it — matches production, where the summary is per unique event."""
        return self.message.strip()

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "severity": self.severity,
            "event_type": self.event_type,
            "node": self.node,
            "ts": self.ts,
            "message": self.message,
            "repeats": self.repeats,
            "message_chars": self.message_chars,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "EventSample":
        return cls(
            run_id=d.get("run_id", ""),
            severity=d.get("severity", ""),
            event_type=d.get("event_type", ""),
            node=d.get("node", ""),
            ts=d.get("ts", ""),
            message=d.get("message", ""),
            repeats=d.get("repeats", 0),
        )


@dataclass
class EventFetcher:
    argus_cli: str | None = None
    no_cache: bool = False
    severities: tuple[str, ...] = ("CRITICAL", "ERROR")
    # The CLI's `run events --limit` is applied per severity level (and only ever returns
    # CRITICAL/ERROR), so this is an upper bound on events fetched per severity, per run.
    per_severity_limit: int = 100
    timeout: float = 120.0  # per CLI invocation; a hung/auth-blocked CLI must not hang the sweep
    _cli: str = field(init=False, default="")

    def __post_init__(self):
        self._cli = _resolve_cli(self.argus_cli)

    def _run(self, args: list[str]) -> list[dict]:
        cmd = [self._cli, *args, "--non-interactive"]
        if self.no_cache:
            cmd.append("--no-cache")
        LOGGER.debug("Running: %s", " ".join(cmd))
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=self.timeout)
        except subprocess.TimeoutExpired:
            LOGGER.warning("argus CLI timed out after %.0fs: %s", self.timeout, " ".join(cmd))
            return []
        if proc.returncode != 0:
            LOGGER.warning("argus CLI failed (%s): %s", proc.returncode, proc.stderr.strip()[:400])
            return []
        out = proc.stdout.strip()
        if not out:
            return []
        try:
            data = json.loads(out)
        except json.JSONDecodeError:
            LOGGER.warning("Could not parse argus output as JSON: %s", out[:200])
            return []
        return data if isinstance(data, list) else []

    def events_for_run(self, run_id: str) -> list[EventSample]:
        rows = self._run(["run", "events", "--run-id", run_id, "--limit", str(self.per_severity_limit)])
        samples: list[EventSample] = []
        for row in rows:
            severity = row.get("severity", "")
            if severity not in self.severities:
                continue
            message = row.get("message") or ""
            if not message.strip():
                continue
            samples.append(
                EventSample(
                    run_id=run_id,
                    severity=severity,
                    event_type=row.get("event_type", ""),
                    node=row.get("node", "") or "",
                    ts=row.get("ts", ""),
                    message=message,
                    repeats=len(row.get("repeated_at") or []),
                )
            )
        LOGGER.info("Run %s: %d ERROR/CRITICAL events", run_id, len(samples))
        return samples

    def run_ids_for_test(self, test_id: str, limit: int) -> list[str]:
        rows = self._run(["run", "list", "--test-id", test_id, "--limit", str(limit)])
        return [r["id"] for r in rows if r.get("id")]

    def collect(
        self,
        run_ids: list[str] | None = None,
        test_id: str | None = None,
        test_run_limit: int = 20,
        max_events: int | None = None,
    ) -> list[EventSample]:
        """Gather deduplicated events from an explicit run list and/or a whole test.

        Events are deduplicated by message text across all runs (production summarizes
        each unique event once); ``max_events`` caps the set so a sweep stays cheap.
        """
        target_runs: list[str] = list(run_ids or [])
        if test_id:
            discovered = self.run_ids_for_test(test_id, test_run_limit)
            LOGGER.info("Test %s: discovered %d runs", test_id, len(discovered))
            target_runs.extend(r for r in discovered if r not in target_runs)

        seen: set[str] = set()
        collected: list[EventSample] = []
        for run_id in target_runs:
            for sample in self.events_for_run(run_id):
                k = sample.key()
                if k in seen:
                    continue
                seen.add(k)
                collected.append(sample)
                if max_events and len(collected) >= max_events:
                    LOGGER.info("Reached max_events=%d, stopping collection", max_events)
                    return collected
        return collected


def save_events(samples: list[EventSample], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([s.to_dict() for s in samples], indent=2), encoding="utf-8")
    LOGGER.info("Saved %d events to %s", len(samples), path)


def load_events(path: Path) -> list[EventSample]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [EventSample.from_dict(d) for d in data]


def load_events_from_env_or_file(path: Path | None) -> list[EventSample]:
    """Convenience for offline iteration: load a hand-curated events.json when the
    CLI/Argus isn't reachable (e.g. developing the report on a plane)."""
    if path and path.exists():
        return load_events(path)
    env_path = os.environ.get("ARGUS_EVAL_EVENTS")
    if env_path and Path(env_path).exists():
        return load_events(Path(env_path))
    return []
