from dataclasses import dataclass

from qatools_health.status import HealthCheckStatus


@dataclass(frozen=True, slots=True)
class HealthCheckResult:
    status: HealthCheckStatus
    message: str = ""
    error: str | None = None

    @classmethod
    def healthy(cls, message: str = "") -> "HealthCheckResult":
        return cls(HealthCheckStatus.HEALTHY, message)

    @classmethod
    def degraded(cls, message: str) -> "HealthCheckResult":
        return cls(HealthCheckStatus.DEGRADED, message)

    @classmethod
    def unhealthy(cls, message: str) -> "HealthCheckResult":
        return cls(HealthCheckStatus.UNHEALTHY, message)


def coerce_result(value: object, failure_status: HealthCheckStatus) -> HealthCheckResult:
    if isinstance(value, HealthCheckResult):
        return value
    if isinstance(value, HealthCheckStatus):
        return HealthCheckResult(value)
    if value is None or value is True:
        return HealthCheckResult(HealthCheckStatus.HEALTHY)
    if value is False:
        return HealthCheckResult(failure_status)
    raise TypeError(f"a check returned {type(value).__name__}, which is not a health check result")


def exception_result(exc: BaseException, failure_status: HealthCheckStatus) -> HealthCheckResult:
    error = str(exc) or type(exc).__name__
    return HealthCheckResult(failure_status, error=error)
