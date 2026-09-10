"""A read-only view of the runner, taken under its lock."""

from dataclasses import dataclass, field

from qatools_health.status import HealthCheckStatus, Severity


@dataclass(frozen=True, slots=True)
class CheckSnapshot:
    """The state of one check at the moment the snapshot was taken."""

    name: str
    severity: Severity
    status: HealthCheckStatus
    message: str = ""
    error: str | None = None
    duration_seconds: float = 0.0
    last_run_timestamp: float = 0.0
    last_success_timestamp: float = 0.0
    stale: bool = True
    subscribers: int = 0


@dataclass(frozen=True, slots=True)
class RunnerSnapshot:
    """The state of the whole runner at the moment the snapshot was taken."""

    service: str
    version: str
    aggregate: HealthCheckStatus
    runner_up: bool
    checks: tuple[CheckSnapshot, ...] = field(default_factory=tuple)
