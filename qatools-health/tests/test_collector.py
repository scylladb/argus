import asyncio

from prometheus_client import CollectorRegistry, generate_latest

from qatools_health import HealthCheckResult, HealthCheckRunner, HealthCheckStatus
from tests.conftest import ScriptedCheck


def families(runner):
    return {family.name: family for family in runner.collector.collect()}


def sample(runner, name, **labels):
    for family in runner.collector.collect():
        for item in family.samples:
            if item.name == name and all(item.labels.get(key) == value for key, value in labels.items()):
                return item
    return None


def build(checks, clock, **kwargs):
    return HealthCheckRunner(checks, service="argus", version="1.4.0", clock=clock, **kwargs)


def test_every_family_the_spec_lists_is_present(clock):
    runner = build([ScriptedCheck(name="jira")], clock)
    assert set(families(runner)) == {
        "healthcheck_status",
        "healthcheck_dependency_up",
        "healthcheck_duration_seconds",
        "healthcheck_last_success_timestamp_seconds",
        "healthcheck_last_run_timestamp_seconds",
        "healthcheck_stale",
        "healthcheck_oldest_result_timestamp_seconds",
        "healthcheck_newest_result_timestamp_seconds",
        "healthcheck_runner_up",
        "healthcheck",
    }


def test_a_check_that_has_not_run_publishes_its_failure_status(clock):
    runner = build([ScriptedCheck(name="jira", critical=True)], clock)
    assert sample(runner, "healthcheck_dependency_up", dependency="jira").value == 0.0
    assert sample(runner, "healthcheck_last_run_timestamp_seconds", dependency="jira").value == 0.0
    assert sample(runner, "healthcheck_stale", dependency="jira").value == 1.0
    assert sample(runner, "healthcheck_status", service="argus").value == 0.0


def test_the_critical_flag_is_a_label(clock):
    runner = build([ScriptedCheck(name="scylla", critical=True), ScriptedCheck(name="jira")], clock)
    assert sample(runner, "healthcheck_dependency_up", dependency="scylla").labels["critical"] == "true"
    assert sample(runner, "healthcheck_dependency_up", dependency="jira").labels["critical"] == "false"


async def test_a_degraded_check_reads_as_a_half(clock):
    check = ScriptedCheck([HealthCheckResult.degraded("queue depth 812")], name="queue")
    runner = build([check], clock)
    runner.start()
    async with asyncio.timeout(2):
        while check.calls < 1:
            await asyncio.sleep(0)
    assert sample(runner, "healthcheck_dependency_up", dependency="queue").value == 0.5
    assert sample(runner, "healthcheck_status", service="argus").value == 1.0
    await runner.stop()


def test_the_info_family_carries_the_version(clock):
    runner = build([ScriptedCheck(name="jira")], clock)
    info = sample(runner, "healthcheck_info", service="argus")
    assert info.labels["version"] == "1.4.0"


def test_no_message_reaches_a_label(clock):
    check = ScriptedCheck(name="jira")
    runner = build([check], clock)
    runner._states[0].message = "the Jira token expired on Tuesday"
    for family in runner.collector.collect():
        for item in family.samples:
            assert "expired" not in "".join(item.labels.values())


def test_the_series_follow_the_list_of_checks(clock):
    two = build([ScriptedCheck(name="a"), ScriptedCheck(name="b")], clock)
    one = build([ScriptedCheck(name="a")], clock)
    assert len(families(two)["healthcheck_dependency_up"].samples) == 2
    assert len(families(one)["healthcheck_dependency_up"].samples) == 1


async def test_runner_up_drops_after_stop(clock):
    runner = build([ScriptedCheck(name="jira")], clock)
    runner.start()
    assert sample(runner, "healthcheck_runner_up", service="argus").value == 1.0
    await runner.stop()
    assert sample(runner, "healthcheck_runner_up", service="argus").value == 0.0


def test_the_result_window_is_zero_before_the_first_run(clock):
    runner = build([ScriptedCheck(name="a"), ScriptedCheck(name="b")], clock)
    assert sample(runner, "healthcheck_oldest_result_timestamp_seconds", service="argus").value == 0.0
    assert sample(runner, "healthcheck_newest_result_timestamp_seconds", service="argus").value == 0.0


def test_the_collector_registers_and_unregisters(clock):
    registry = CollectorRegistry()
    runner = build([ScriptedCheck(name="jira")], clock)
    runner.register(registry)
    assert b"healthcheck_status" in generate_latest(registry)
    runner.unregister(registry)
    assert b"healthcheck_status" not in generate_latest(registry)


def test_the_aggregate_gauge_maps_every_status(clock):
    for status, expected in (
        (HealthCheckStatus.HEALTHY, 2.0),
        (HealthCheckStatus.DEGRADED, 1.0),
        (HealthCheckStatus.UNHEALTHY, 0.0),
    ):
        check = ScriptedCheck(name="jira", stale_after_intervals=1000, critical=True)
        runner = build([check], clock)
        runner._states[0].status = status
        runner._states[0].last_run_timestamp = clock.now
        assert sample(runner, "healthcheck_status", service="argus").value == expected
