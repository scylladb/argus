from enum import StrEnum


class HealthCheckStatus(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"


SEVERITY: dict[HealthCheckStatus, int] = {
    HealthCheckStatus.HEALTHY: 0,
    HealthCheckStatus.DEGRADED: 1,
    HealthCheckStatus.UNHEALTHY: 2,
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
    return max(statuses, key=SEVERITY.__getitem__)


def is_worse(candidate: HealthCheckStatus, reference: HealthCheckStatus) -> bool:
    return SEVERITY[candidate] > SEVERITY[reference]
