"""The status and severity values, and the rules that order them."""

from enum import StrEnum


class HealthCheckStatus(StrEnum):
    """The outcome of one run of one health check."""

    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"


class Severity(StrEnum):
    """How much one dependency matters to the service that depends on it.

    A critical dependency can make the service unhealthy. An important one can
    only degrade it. An optional one never changes the aggregate.
    """

    CRITICAL = "critical"
    IMPORTANT = "important"
    OPTIONAL = "optional"


STATUS_ORDER: dict[HealthCheckStatus, int] = {
    HealthCheckStatus.HEALTHY: 0,
    HealthCheckStatus.DEGRADED: 1,
    HealthCheckStatus.UNHEALTHY: 2,
}

SEVERITY_ORDER: dict[Severity, int] = {
    Severity.OPTIONAL: 0,
    Severity.IMPORTANT: 1,
    Severity.CRITICAL: 2,
}

AGGREGATE_GAUGE_VALUE: dict[HealthCheckStatus, float] = {
    HealthCheckStatus.HEALTHY: 2.0,
    HealthCheckStatus.DEGRADED: 1.0,
    HealthCheckStatus.UNHEALTHY: 0.0,
}

DEPENDENCY_GAUGE_VALUE: dict[HealthCheckStatus, float] = {
    HealthCheckStatus.HEALTHY: 1.0,
    HealthCheckStatus.DEGRADED: 0.5,
    HealthCheckStatus.UNHEALTHY: 0.0,
}


def worse_of(*statuses: HealthCheckStatus) -> HealthCheckStatus:
    """Return the worst of the statuses. A call with no status returns HEALTHY."""
    if not statuses:
        return HealthCheckStatus.HEALTHY
    return max(statuses, key=STATUS_ORDER.__getitem__)


def is_worse(candidate: HealthCheckStatus, reference: HealthCheckStatus) -> bool:
    """Report whether the candidate status is worse than the reference status."""
    return STATUS_ORDER[candidate] > STATUS_ORDER[reference]


def strictest_severity(*severities: Severity) -> Severity:
    """Return the highest of the severities. A call with none returns IMPORTANT."""
    if not severities:
        return Severity.IMPORTANT
    return max(severities, key=SEVERITY_ORDER.__getitem__)
