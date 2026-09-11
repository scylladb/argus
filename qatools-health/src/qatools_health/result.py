"""The result of one health check run, and the rules that build one."""

from dataclasses import dataclass

from qatools_health.status import HealthCheckStatus


@dataclass(frozen=True, slots=True)
class HealthCheckResult:
    """What one run of one check found.

    The message explains a healthy or a degraded result to a person. The error
    carries the text of the exception that ended an unhealthy run.
    """

    status: HealthCheckStatus
    message: str = ""
    error: str | None = None

    @classmethod
    def healthy(cls, message: str = "") -> "HealthCheckResult":
        """Build a healthy result."""
        return cls(HealthCheckStatus.HEALTHY, message)

    @classmethod
    def degraded(cls, message: str) -> "HealthCheckResult":
        """Build a degraded result. The message must say what degraded."""
        return cls(HealthCheckStatus.DEGRADED, message)

    @classmethod
    def unhealthy(cls, message: str) -> "HealthCheckResult":
        """Build an unhealthy result. The message must say what failed."""
        return cls(HealthCheckStatus.UNHEALTHY, message)


def coerce_result(value: object) -> HealthCheckResult:
    """Turn the value a check returned into a result.

    A check may return a result, a status, a boolean, or None. None and True
    mean healthy. False means unhealthy. Any other type raises TypeError.
    """
    if isinstance(value, HealthCheckResult):
        return value
    if isinstance(value, HealthCheckStatus):
        return HealthCheckResult(value)
    if value is None or value is True:
        return HealthCheckResult(HealthCheckStatus.HEALTHY)
    if value is False:
        return HealthCheckResult(HealthCheckStatus.UNHEALTHY)
    raise TypeError(f"a check returned {type(value).__name__}, which is not a health check result")


def exception_result(exc: BaseException) -> HealthCheckResult:
    """Turn the exception that ended a run into an unhealthy result."""
    error = str(exc) or type(exc).__name__
    return HealthCheckResult(HealthCheckStatus.UNHEALTHY, error=error)
