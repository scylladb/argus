import asyncio
import logging

import pytest

from qatools_health import HealthCheckResult, HealthCheckRunner, HealthCheckStatus
from tests.conftest import ScriptedCheck

HEALTHY = HealthCheckStatus.HEALTHY
DEGRADED = HealthCheckStatus.DEGRADED
UNHEALTHY = HealthCheckStatus.UNHEALTHY


def build(checks, clock, **kwargs):
    return HealthCheckRunner(checks, service="zeus", clock=clock, **kwargs)


async def settle(check: ScriptedCheck, calls: int = 1) -> None:
    async with asyncio.timeout(2):
        while check.calls < calls:
            await asyncio.sleep(0)


def test_a_duplicate_name_is_rejected(clock):
    with pytest.raises(ValueError, match="duplicate health check name"):
        build([ScriptedCheck(name="a"), ScriptedCheck(name="a")], clock)


def test_a_never_run_critical_check_makes_the_service_unhealthy(clock):
    runner = build([ScriptedCheck(name="scylla", critical=True)], clock)
    assert runner.status is UNHEALTHY


def test_a_never_run_optional_check_degrades_the_service(clock):
    runner = build([ScriptedCheck(name="jira")], clock)
    assert runner.status is DEGRADED


async def test_a_healthy_run_clears_the_aggregate(clock):
    check = ScriptedCheck([True], name="jira")
    runner = build([check], clock)
    runner.start()
    await settle(check)
    assert runner.status is HEALTHY
    await runner.stop()


async def test_an_exception_records_the_failure_status_and_the_message(clock):
    check = ScriptedCheck([RuntimeError("no route to host")], name="jira")
    runner = build([check], clock)
    runner.start()
    await settle(check)
    published = runner.snapshot().checks[0]
    assert published.status is UNHEALTHY
    assert published.error == "no route to host"
    await runner.stop()


async def test_failure_status_replaces_unhealthy_for_an_optional_dependency(clock):
    check = ScriptedCheck([RuntimeError("boom")], name="jira", failure_status=DEGRADED)
    runner = build([check], clock)
    runner.start()
    await settle(check)
    assert runner.snapshot().checks[0].status is DEGRADED
    await runner.stop()


async def test_a_run_over_its_timeout_is_recorded_as_a_timeout(clock):
    check = ScriptedCheck(name="slow", timeout=0.01, delay=5)
    runner = build([check], clock)
    runner.start()
    await settle(check)
    await asyncio.sleep(0.05)
    published = runner.snapshot().checks[0]
    assert published.status is UNHEALTHY
    assert published.message == "timed out after 0.01s"
    await runner.stop()


async def test_a_check_never_overlaps_itself(clock):
    check = ScriptedCheck(name="slow", interval=0.001, delay=0.05)
    runner = build([check], clock)
    runner.start()
    await settle(check)
    await asyncio.sleep(0.02)
    assert check.calls == 1
    await runner.stop()


async def test_stop_closes_every_check(clock):
    first, second = ScriptedCheck(name="a"), ScriptedCheck(name="b")
    runner = build([first, second], clock)
    runner.start()
    await settle(first)
    await runner.stop()
    assert (first.closed, second.closed) == (1, 1)


async def test_stop_survives_a_check_that_fails_to_close(clock):
    class Rude(ScriptedCheck):
        async def aclose(self):
            raise OSError("busy")

    runner = build([Rude(name="rude")], clock)
    runner.start()
    await runner.stop()
    assert runner.snapshot().runner_up is False


def test_start_twice_is_rejected(clock):
    runner = build([ScriptedCheck(name="a")], clock)

    async def go():
        runner.start()
        with pytest.raises(RuntimeError, match="already started"):
            runner.start()
        await runner.stop()

    asyncio.run(go())


async def test_run_stops_when_the_shutdown_event_is_set(clock):
    check = ScriptedCheck(name="a")
    runner = build([check], clock)
    shutdown = asyncio.Event()
    task = asyncio.create_task(runner.run(shutdown))
    await settle(check)
    shutdown.set()
    await asyncio.wait_for(task, timeout=2)
    assert check.closed == 1


async def test_a_stale_check_degrades_the_service(clock):
    check = ScriptedCheck([True], name="jira", interval=10, stale_after_intervals=2)
    runner = build([check], clock)
    runner.start()
    await settle(check)
    assert runner.status is HEALTHY
    clock.advance(21)
    assert runner.status is DEGRADED
    assert runner.snapshot().checks[0].status is HEALTHY
    await runner.stop()


async def test_staleness_never_softens_a_status(clock):
    check = ScriptedCheck([HealthCheckResult.unhealthy("gone")], name="jira", interval=10, stale_after_intervals=2)
    runner = build([check], clock)
    runner.start()
    await settle(check)
    clock.advance(21)
    assert runner.status is DEGRADED
    assert runner.snapshot().checks[0].status is UNHEALTHY
    await runner.stop()


async def test_a_critical_unhealthy_check_makes_the_service_unhealthy(clock):
    critical = ScriptedCheck([HealthCheckResult.unhealthy("gone")], name="scylla", critical=True)
    optional = ScriptedCheck([True], name="jira")
    runner = build([critical, optional], clock)
    runner.start()
    await settle(critical)
    await settle(optional)
    assert runner.status is UNHEALTHY
    await runner.stop()


async def test_an_optional_unhealthy_check_only_degrades_the_service(clock):
    optional = ScriptedCheck([HealthCheckResult.unhealthy("gone")], name="jira")
    healthy = ScriptedCheck([True], name="scylla", critical=True)
    runner = build([optional, healthy], clock)
    runner.start()
    await settle(optional)
    await settle(healthy)
    assert runner.status is DEGRADED
    await runner.stop()


async def test_on_change_fires_once_per_transition_and_names_the_check(clock):
    seen = []
    check = ScriptedCheck([True, HealthCheckResult.unhealthy("gone")], name="jira", interval=0.001)
    runner = build([check], clock, on_change=lambda status, reason: seen.append((status, reason)))
    runner.start()
    await settle(check, calls=2)
    await asyncio.sleep(0.02)
    await runner.stop()
    assert seen[0] == (HEALTHY, "every dependency healthy")
    assert seen[1] == (DEGRADED, "jira unhealthy")


async def test_a_failing_on_change_does_not_reach_the_service(clock, caplog):
    def explode(status, reason):
        raise RuntimeError("systemd is not listening")

    check = ScriptedCheck([True], name="jira")
    runner = build([check], clock, on_change=explode)
    with caplog.at_level(logging.ERROR, logger="qatools_health"):
        runner.start()
        await settle(check)
    assert "on_change callback failed" in caplog.text
    await runner.stop()


async def test_a_status_change_is_logged_once(clock, caplog):
    check = ScriptedCheck(
        [True, HealthCheckResult.unhealthy("gone"), HealthCheckResult.unhealthy("gone"), True],
        name="jira",
        interval=0.001,
    )
    runner = build([check], clock)
    with caplog.at_level(logging.INFO, logger="qatools_health"):
        runner.start()
        await settle(check, calls=4)
        await asyncio.sleep(0.02)
    await runner.stop()
    transitions = [record for record in caplog.records if record.msg.startswith("health check %s %s")]
    assert [record.levelno for record in transitions] == [logging.INFO, logging.WARNING, logging.INFO]


async def test_the_first_runs_are_spread_over_a_second(clock):
    checks = [ScriptedCheck(name=f"check{index}") for index in range(4)]
    runner = build(checks, clock)
    runner.start()
    await settle(checks[0])
    assert checks[0].calls == 1
    assert checks[3].calls == 0
    await runner.stop()


async def test_a_check_returning_a_bad_type_is_recorded_as_a_failure(clock):
    check = ScriptedCheck(["HEALTHY"], name="jira")
    runner = build([check], clock)
    runner.start()
    await settle(check)
    published = runner.snapshot().checks[0]
    assert published.status is UNHEALTHY
    assert "not a health check result" in (published.error or "")
    await runner.stop()


async def test_the_snapshot_records_the_timestamps(clock):
    check = ScriptedCheck([True], name="jira")
    runner = build([check], clock)
    runner.start()
    await settle(check)
    published = runner.snapshot().checks[0]
    assert published.last_run_timestamp == clock.now
    assert published.last_success_timestamp == clock.now
    await runner.stop()


async def test_an_unhealthy_result_leaves_the_last_success_alone(clock):
    check = ScriptedCheck([True, HealthCheckResult.unhealthy("gone")], name="jira", interval=0.001)
    runner = build([check], clock)
    runner.start()
    await settle(check)
    success_at = clock.now
    clock.advance(60)
    await settle(check, calls=2)
    await asyncio.sleep(0.02)
    published = runner.snapshot().checks[0]
    assert published.last_success_timestamp == success_at
    assert published.last_run_timestamp == clock.now
    await runner.stop()


async def test_a_framework_failure_drops_runner_up_and_stays_inside(clock, caplog):
    check = ScriptedCheck([True], name="jira", interval=0.001)
    runner = build([check], clock)
    with caplog.at_level(logging.ERROR, logger="qatools_health"):
        runner.start()
        await settle(check)
        check.interval = "not a number"
        await asyncio.sleep(0.05)
    check.interval = 0.001
    assert runner.snapshot().runner_up is False
    assert "health check loop for jira stopped" in caplog.text
    await runner.stop()
