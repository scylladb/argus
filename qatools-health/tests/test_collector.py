from prometheus_client import CollectorRegistry, generate_latest
from support import ScriptedCheck, settle, spin

from qatools_health import HealthCheckResult, HealthCheckRunner, HealthCheckStatus, Severity


def families(runner):
    return {family.name: family for family in runner.collector.collect()}


def sample(runner, name, **labels):
    for family in runner.collector.collect():
        for item in family.samples:
            if item.name == name and all(item.labels.get(key) == value for key, value in labels.items()):
                return item
    return None


def build(clock, *checks, **kwargs):
    runner = HealthCheckRunner(service="argus", version="1.4.0", clock=clock, **kwargs)
    for check in checks:
        runner.register(check)
    return runner


def state_of(runner):
    return next(iter(runner._states.values()))


def test_every_family_the_spec_lists_is_present(clock):
    runner = build(clock, ScriptedCheck(name="jira"))
    assert set(families(runner)) == {
        "healthcheck_status",
        "healthcheck_dependency_up",
        "healthcheck_duration_seconds",
        "healthcheck_last_success_timestamp_seconds",
        "healthcheck_last_run_timestamp_seconds",
        "healthcheck_stale",
        "healthcheck_subscribers",
        "healthcheck_oldest_result_timestamp_seconds",
        "healthcheck_newest_result_timestamp_seconds",
        "healthcheck_runner_up",
        "healthcheck",
    }


def test_a_check_that_has_not_run_publishes_unhealthy(clock):
    runner = build(clock, ScriptedCheck(name="jira", severity=Severity.CRITICAL))
    assert sample(runner, "healthcheck_dependency_up", dependency="jira").value == 0.0
    assert sample(runner, "healthcheck_last_run_timestamp_seconds", dependency="jira").value == 0.0
    assert sample(runner, "healthcheck_stale", dependency="jira").value == 1.0
    assert sample(runner, "healthcheck_status", service="argus").value == 0.0


def test_the_dependency_series_carries_no_severity(clock):
    runner = build(clock, ScriptedCheck(name="scylla", severity=Severity.CRITICAL))
    assert set(sample(runner, "healthcheck_dependency_up", dependency="scylla").labels) == {"service", "dependency"}


def test_the_subscriber_count_follows_the_subscriptions(clock):
    runner = build(clock, ScriptedCheck(name="jira"))
    assert sample(runner, "healthcheck_subscribers", dependency="jira").value == 1.0
    runner.register(ScriptedCheck(name="jira"))
    assert sample(runner, "healthcheck_subscribers", dependency="jira").value == 2.0


async def test_a_degraded_check_reads_as_a_half(clock):
    check = ScriptedCheck([HealthCheckResult.degraded("queue depth 812")], name="queue")
    runner = build(clock, check)
    runner.start()
    await settle(check)
    assert sample(runner, "healthcheck_dependency_up", dependency="queue").value == 0.5
    assert sample(runner, "healthcheck_status", service="argus").value == 1.0
    await runner.stop()


def test_the_info_family_carries_the_version(clock):
    runner = build(clock, ScriptedCheck(name="jira"))
    assert sample(runner, "healthcheck_info", service="argus").labels["version"] == "1.4.0"


def test_no_message_reaches_a_label(clock):
    runner = build(clock, ScriptedCheck(name="jira"))
    state_of(runner).message = "the Jira token expired on Tuesday"
    for family in runner.collector.collect():
        for item in family.samples:
            assert "expired" not in "".join(item.labels.values())


def test_the_series_follow_the_registered_checks(clock):
    two = build(clock, ScriptedCheck(name="a"), ScriptedCheck(name="b"))
    one = build(clock, ScriptedCheck(name="a"))
    assert len(families(two)["healthcheck_dependency_up"].samples) == 2
    assert len(families(one)["healthcheck_dependency_up"].samples) == 1


async def test_retiring_a_check_removes_its_series(clock):
    runner = build(clock, ScriptedCheck(name="a"))
    subscription = runner.register(ScriptedCheck(name="b"))
    assert len(families(runner)["healthcheck_dependency_up"].samples) == 2
    subscription.close()
    await spin()
    assert sample(runner, "healthcheck_dependency_up", dependency="b") is None


async def test_runner_up_drops_after_stop(clock):
    runner = build(clock, ScriptedCheck(name="jira"))
    runner.start()
    assert sample(runner, "healthcheck_runner_up", service="argus").value == 1.0
    await runner.stop()
    assert sample(runner, "healthcheck_runner_up", service="argus").value == 0.0


def test_the_result_window_is_zero_before_the_first_run(clock):
    runner = build(clock, ScriptedCheck(name="a"), ScriptedCheck(name="b"))
    assert sample(runner, "healthcheck_oldest_result_timestamp_seconds", service="argus").value == 0.0
    assert sample(runner, "healthcheck_newest_result_timestamp_seconds", service="argus").value == 0.0


def test_the_result_window_is_zero_with_no_checks(clock):
    runner = build(clock)
    assert sample(runner, "healthcheck_oldest_result_timestamp_seconds", service="argus").value == 0.0


def test_the_collector_registers_and_unregisters(clock):
    registry = CollectorRegistry()
    runner = build(clock, ScriptedCheck(name="jira"))
    runner.register_collector(registry)
    assert b"healthcheck_status" in generate_latest(registry)
    runner.unregister_collector(registry)
    assert b"healthcheck_status" not in generate_latest(registry)


def test_the_aggregate_gauge_maps_every_status(clock):
    for status, expected in (
        (HealthCheckStatus.HEALTHY, 2.0),
        (HealthCheckStatus.DEGRADED, 1.0),
        (HealthCheckStatus.UNHEALTHY, 0.0),
    ):
        runner = build(clock, ScriptedCheck(name="jira", stale_after_intervals=1000, severity=Severity.CRITICAL))
        state = state_of(runner)
        state.status = status
        state.last_run_timestamp = clock.now
        assert sample(runner, "healthcheck_status", service="argus").value == expected
