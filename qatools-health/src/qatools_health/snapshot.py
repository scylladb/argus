from dataclasses import dataclass, field

from qatools_health.status import HealthCheckStatus, Severity


@dataclass(frozen=True, slots=True)
class CheckSnapshot:
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
    service: str
    version: str
    aggregate: HealthCheckStatus
    runner_up: bool
    checks: tuple[CheckSnapshot, ...] = field(default_factory=tuple)
