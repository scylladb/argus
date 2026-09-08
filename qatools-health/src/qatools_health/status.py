from enum import StrEnum


class HealthCheckStatus(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"


class Severity(StrEnum):
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
    if not statuses:
        return HealthCheckStatus.HEALTHY
    return max(statuses, key=STATUS_ORDER.__getitem__)


def is_worse(candidate: HealthCheckStatus, reference: HealthCheckStatus) -> bool:
    return STATUS_ORDER[candidate] > STATUS_ORDER[reference]


def strictest_severity(*severities: Severity) -> Severity:
    if not severities:
        return Severity.IMPORTANT
    return max(severities, key=SEVERITY_ORDER.__getitem__)
