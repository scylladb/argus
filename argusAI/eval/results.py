"""The serializable domain types produced by the sweep and consumed by the report.

These are the shared vocabulary between ``harness`` (which produces them) and ``report``
(which reads their serialized form from ``results.json``). Keeping them here — not inside
the orchestrator — means the shape of a result is defined in one obvious place.

The on-disk JSON schema is exactly ``CellResult.to_dict()``: every dataclass field, plus
two derived keys the report relies on — ``compression_ratio`` and, when judged,
``judge.overall``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class JudgeScore:
    """A frontier model's assessment of one summary against its original event."""

    coverage: int = 0
    faithfulness: int = 0
    conciseness: int = 0
    dropped_critical: list[str] = field(default_factory=list)
    hallucinations: list[str] = field(default_factory=list)
    verdict: str = ""
    error: str | None = None

    @property
    def overall(self) -> float:
        """Coverage and faithfulness dominate; a hallucination is worse than a terse
        omission, and conciseness only breaks ties. Weights are opinionated on purpose —
        adjust here if the team weighs the trade-off differently."""
        return 0.45 * self.coverage + 0.40 * self.faithfulness + 0.15 * self.conciseness


@dataclass
class CellResult:
    """One (event, model, prompt) outcome — the atomic row of the report."""

    event_key: str
    run_id: str
    event_type: str
    node: str
    severity: str
    model: str
    model_label: str
    prompt_name: str
    input_chars: int
    summary_chars: int
    input_tokens: int = 0
    summary_tokens: int = 0
    summary: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    judge: JudgeScore | None = None
    error: str | None = None

    @property
    def compression_ratio(self) -> float:
        # Measured in tokens (what the API bills), not characters.
        return (self.summary_tokens / self.input_tokens) if self.input_tokens else 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        if self.judge is not None:
            d["judge"] = asdict(self.judge)
            d["judge"]["overall"] = round(self.judge.overall, 1)
        d["compression_ratio"] = round(self.compression_ratio, 3)
        return d
