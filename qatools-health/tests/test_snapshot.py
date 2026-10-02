import pytest

from qatools_health import CheckSnapshot, HealthCheckStatus, Severity


@pytest.mark.parametrize(
    ("status", "stale", "effective"),
    [
        (HealthCheckStatus.HEALTHY, False, HealthCheckStatus.HEALTHY),
        (HealthCheckStatus.HEALTHY, True, HealthCheckStatus.DEGRADED),
        (HealthCheckStatus.DEGRADED, True, HealthCheckStatus.DEGRADED),
        (HealthCheckStatus.UNHEALTHY, True, HealthCheckStatus.UNHEALTHY),
        (HealthCheckStatus.UNHEALTHY, False, HealthCheckStatus.UNHEALTHY),
    ],
)
def test_a_stale_snapshot_reads_at_least_degraded(status, stale, effective):
    snapshot = CheckSnapshot(name="jira_api", severity=Severity.IMPORTANT, status=status, stale=stale)
    assert snapshot.effective_status is effective
