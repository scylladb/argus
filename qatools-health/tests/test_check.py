import pytest

from qatools_health import CallableHealthCheck, HealthCheck, HealthCheckStatus, healthcheck


class ProbeCheck(HealthCheck):
    name = "probe"
    critical = True
    interval = 30.0

    async def perform_check(self):
        return None


def test_class_attributes_become_the_defaults():
    check = ProbeCheck()
    assert (check.name, check.critical, check.interval) == ("probe", True, 30.0)
    assert check.timeout == 10.0
    assert check.stale_after_intervals == 3.0


def test_constructor_overrides_one_instance_only():
    override = ProbeCheck(name="probe:second", critical=False, interval=5, timeout=1)
    assert (override.name, override.critical, override.interval, override.timeout) == ("probe:second", False, 5.0, 1.0)
    assert ProbeCheck().name == "probe"


def test_failure_status_is_overridable():
    check = ProbeCheck(failure_status=HealthCheckStatus.DEGRADED)
    assert check.failure_status is HealthCheckStatus.DEGRADED


def test_a_check_without_a_name_is_rejected():
    class Unnamed(HealthCheck):
        async def perform_check(self):
            return None

    with pytest.raises(ValueError, match="has no name"):
        Unnamed()


@pytest.mark.parametrize("kwargs", [{"interval": 0}, {"timeout": -1}, {"stale_after_intervals": 0}])
def test_non_positive_schedule_values_are_rejected(kwargs):
    with pytest.raises(ValueError, match="must be positive"):
        ProbeCheck(**kwargs)


async def test_aclose_is_a_no_op_by_default():
    assert await ProbeCheck().aclose() is None


async def test_the_decorator_builds_an_instance():
    @healthcheck(name="queue_depth", interval=30)
    async def queue_depth():
        return True

    assert isinstance(queue_depth, CallableHealthCheck)
    assert (queue_depth.name, queue_depth.interval) == ("queue_depth", 30.0)
    assert await queue_depth.perform_check() is True


async def test_the_decorator_takes_the_function_name():
    @healthcheck
    async def api_queue_depth():
        return None

    assert api_queue_depth.name == "api_queue_depth"


def test_the_decorator_rejects_a_synchronous_function():
    with pytest.raises(TypeError, match="not an async function"):

        @healthcheck(name="blocking")
        def blocking():
            return True


def test_repr_names_the_check():
    assert "probe" in repr(ProbeCheck())
