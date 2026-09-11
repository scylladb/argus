"""Health checking for the ScyllaDB QA Tools services.

Build a HealthCheckRunner, register the checks the service depends on, and
run it beside the service. Each register call returns a subscription that
holds the check and reports every change. The runner also exposes a
Prometheus collector over the same state.
"""

from qatools_health.check import CallableHealthCheck, HealthCheck, healthcheck
from qatools_health.collector import HealthMetricsCollector
from qatools_health.result import HealthCheckResult, coerce_result
from qatools_health.runner import HealthCheckRunner
from qatools_health.snapshot import CheckSnapshot, RunnerSnapshot
from qatools_health.status import HealthCheckStatus, Severity, is_worse, strictest_severity, worse_of
from qatools_health.subscription import (
    HealthCheckGroup,
    HealthCheckSubscription,
    OnChange,
    OnGroupChange,
    SubscriptionClosedError,
)

__all__ = [
    "CallableHealthCheck",
    "CheckSnapshot",
    "HealthCheck",
    "HealthCheckGroup",
    "HealthCheckResult",
    "HealthCheckRunner",
    "HealthCheckStatus",
    "HealthCheckSubscription",
    "HealthMetricsCollector",
    "OnChange",
    "OnGroupChange",
    "RunnerSnapshot",
    "Severity",
    "SubscriptionClosedError",
    "coerce_result",
    "healthcheck",
    "is_worse",
    "strictest_severity",
    "worse_of",
]
