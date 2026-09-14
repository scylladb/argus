import pytest

from qatools_health import HealthCheckResult, HealthCheckStatus, Severity, coerce_result, is_worse, worse_of
from qatools_health import strictest_severity
from qatools_health.result import exception_result


def test_constructors_carry_the_status():
    assert HealthCheckResult.healthy().status is HealthCheckStatus.HEALTHY
    assert HealthCheckResult.degraded("slow").status is HealthCheckStatus.DEGRADED
    assert HealthCheckResult.unhealthy("gone").status is HealthCheckStatus.UNHEALTHY


def test_result_is_frozen():
    with pytest.raises(AttributeError):
        HealthCheckResult.healthy().status = HealthCheckStatus.DEGRADED


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (HealthCheckResult.degraded("queue depth 812"), HealthCheckStatus.DEGRADED),
        (HealthCheckStatus.DEGRADED, HealthCheckStatus.DEGRADED),
        (True, HealthCheckStatus.HEALTHY),
        (None, HealthCheckStatus.HEALTHY),
        (False, HealthCheckStatus.UNHEALTHY),
    ],
)
def test_coercion_table(value, expected):
    assert coerce_result(value).status is expected


def test_coercion_keeps_the_result_it_was_given():
    result = HealthCheckResult.degraded("queue depth 812")
    assert coerce_result(result) is result


def test_coercion_rejects_anything_else():
    with pytest.raises(TypeError):
        coerce_result("HEALTHY")


def test_exception_result_records_the_message():
    result = exception_result(RuntimeError("no route to host"))
    assert result.status is HealthCheckStatus.UNHEALTHY
    assert result.error == "no route to host"


def test_exception_result_falls_back_to_the_type_name():
    assert exception_result(TimeoutError()).error == "TimeoutError"


def test_worse_of_picks_the_worst():
    assert worse_of(HealthCheckStatus.HEALTHY, HealthCheckStatus.DEGRADED) is HealthCheckStatus.DEGRADED
    assert worse_of(HealthCheckStatus.UNHEALTHY, HealthCheckStatus.DEGRADED) is HealthCheckStatus.UNHEALTHY
    assert worse_of() is HealthCheckStatus.HEALTHY


def test_is_worse_orders_the_statuses():
    assert is_worse(HealthCheckStatus.UNHEALTHY, HealthCheckStatus.DEGRADED)
    assert not is_worse(HealthCheckStatus.HEALTHY, HealthCheckStatus.DEGRADED)


def test_the_strictest_severity_wins():
    assert strictest_severity(Severity.OPTIONAL, Severity.IMPORTANT) is Severity.IMPORTANT
    assert strictest_severity(Severity.CRITICAL, Severity.IMPORTANT) is Severity.CRITICAL
    assert strictest_severity() is Severity.IMPORTANT
