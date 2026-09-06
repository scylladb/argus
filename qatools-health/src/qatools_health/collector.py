from collections.abc import Callable, Iterable

from prometheus_client.metrics_core import GaugeMetricFamily, InfoMetricFamily, Metric

from qatools_health.snapshot import RunnerSnapshot
from qatools_health.status import AGGREGATE_GAUGE_VALUE, DEPENDENCY_GAUGE_VALUE

SERVICE = ["service"]
DEPENDENCY = ["service", "dependency"]


class HealthMetricsCollector:
    def __init__(self, read_snapshot: Callable[[], RunnerSnapshot]) -> None:
        self._read_snapshot = read_snapshot

    def describe(self) -> Iterable[Metric]:
        return ()

    def collect(self) -> Iterable[Metric]:
        snapshot = self._read_snapshot()
        service = snapshot.service

        aggregate = GaugeMetricFamily(
            "healthcheck_status",
            "Aggregate health of the service: 2 healthy, 1 degraded, 0 unhealthy",
            labels=SERVICE,
        )
        aggregate.add_metric([service], AGGREGATE_GAUGE_VALUE[snapshot.aggregate])

        dependency_up = GaugeMetricFamily(
            "healthcheck_dependency_up",
            "Health of one dependency: 1 healthy, 0.5 degraded, 0 unhealthy",
            labels=["service", "dependency", "critical"],
        )
        duration = GaugeMetricFamily(
            "healthcheck_duration_seconds",
            "Duration of the last run of this check",
            labels=DEPENDENCY,
        )
        last_success = GaugeMetricFamily(
            "healthcheck_last_success_timestamp_seconds",
            "Unix time of the last healthy result",
            labels=DEPENDENCY,
        )
        last_run = GaugeMetricFamily(
            "healthcheck_last_run_timestamp_seconds",
            "Unix time the last run finished",
            labels=DEPENDENCY,
        )
        stale = GaugeMetricFamily(
            "healthcheck_stale",
            "1 when the last value is older than stale_after_intervals intervals",
            labels=DEPENDENCY,
        )

        for check in snapshot.checks:
            labels = [service, check.name]
            dependency_up.add_metric(
                [service, check.name, str(check.critical).lower()],
                DEPENDENCY_GAUGE_VALUE[check.status],
            )
            duration.add_metric(labels, check.duration_seconds)
            last_success.add_metric(labels, check.last_success_timestamp)
            last_run.add_metric(labels, check.last_run_timestamp)
            stale.add_metric(labels, 1.0 if check.stale else 0.0)

        completions = [check.last_run_timestamp for check in snapshot.checks]
        oldest = GaugeMetricFamily(
            "healthcheck_oldest_result_timestamp_seconds",
            "Completion time of the oldest published result",
            labels=SERVICE,
        )
        oldest.add_metric([service], min(completions) if completions else 0.0)
        newest = GaugeMetricFamily(
            "healthcheck_newest_result_timestamp_seconds",
            "Completion time of the newest published result",
            labels=SERVICE,
        )
        newest.add_metric([service], max(completions) if completions else 0.0)

        runner_up = GaugeMetricFamily(
            "healthcheck_runner_up",
            "0 once health checking has stopped",
            labels=SERVICE,
        )
        runner_up.add_metric([service], 1.0 if snapshot.runner_up else 0.0)

        info = InfoMetricFamily("healthcheck", "Build identity of the service", labels=SERVICE)
        info.add_metric([service], {"version": snapshot.version})

        return (
            aggregate,
            dependency_up,
            duration,
            last_success,
            last_run,
            stale,
            oldest,
            newest,
            runner_up,
            info,
        )
