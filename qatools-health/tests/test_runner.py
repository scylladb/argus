import asyncio
import logging

import pytest
from support import PairedCheck, ScriptedCheck, settle, spin

from qatools_health import HealthCheckResult, HealthCheckRunner, HealthCheckStatus, Severity

HEALTHY = HealthCheckStatus.HEALTHY
DEGRADED = HealthCheckStatus.DEGRADED
UNHEALTHY = HealthCheckStatus.UNHEALTHY


def build(clock, *checks, **kwargs):
    runner = HealthCheckRunner(service="zeus", clock=clock, **kwargs)
    for check in checks:
        runner.register(check)
    return runner


def published(runner, index=0):
    return runner.snapshot().checks[index]


def test_registration_returns_a_subscription_over_the_instance(clock):
    check = ScriptedCheck(name="jira")
    subscription = build(clock, check).register(ScriptedCheck(name="jira"))
    assert subscription.check is check


def test_a_second_name_for_one_dependency_is_rejected(clock):
    runner = build(clock, PairedCheck(name="jira"))
    with pytest.raises(ValueError, match="already registered as"):
        runner.register(PairedCheck(name="jira:second"))


def test_a_second_dependency_under_one_name_is_rejected(clock):
    runner = build(clock, ScriptedCheck(name="jira"))
    with pytest.raises(ValueError, match="already names another dependency"):
        runner.register(PairedCheck(name="jira"))


def test_a_duplicate_takes_the_strictest_policy(clock):
    check = ScriptedCheck(name="jira", severity=Severity.OPTIONAL, interval=60, timeout=9)
    runner = build(clock, check)
    runner.register(ScriptedCheck(name="jira", severity=Severity.CRITICAL, interval=10, timeout=2))
    assert (check.severity, check.interval, check.timeout) == (Severity.CRITICAL, 10.0, 2.0)
    assert len(runner.snapshot().checks) == 1


async def test_a_duplicate_shares_one_probe_loop(clock):
    first, second = ScriptedCheck([True], name="jira"), ScriptedCheck([True], name="jira")
    runner = build(clock, first, second)
    runner.start()
    await settle(first)
    await spin()
    assert (first.calls, second.calls) == (1, 0)
    assert published(runner).subscribers == 2
    await runner.stop()


def test_a_never_run_critical_check_makes_the_service_unhealthy(clock):
    assert build(clock, ScriptedCheck(name="scylla", severity=Severity.CRITICAL)).status is UNHEALTHY


def test_a_never_run_important_check_degrades_the_service(clock):
    assert build(clock, ScriptedCheck(name="jira")).status is DEGRADED


def test_an_optional_check_never_changes_the_aggregate(clock):
    runner = build(clock, ScriptedCheck(name="jira", severity=Severity.OPTIONAL))
    assert runner.status is HEALTHY


async def test_a_healthy_run_clears_the_aggregate(clock):
    check = ScriptedCheck([True], name="jira")
    runner = build(clock, check)
    runner.start()
    await settle(check)
    assert runner.status is HEALTHY
    await runner.stop()


async def test_an_exception_records_unhealthy_and_the_message(clock):
    check = ScriptedCheck([RuntimeError("no route to host")], name="jira")
    runner = build(clock, check)
    runner.start()
    await settle(check)
    assert published(runner).status is UNHEALTHY
    assert published(runner).error == "no route to host"
    await runner.stop()


async def test_a_run_over_its_timeout_is_recorded_as_a_timeout(clock):
    check = ScriptedCheck(name="slow", timeout=0.01, delay=5)
    runner = build(clock, check)
    runner.start()
    await settle(check)
    await asyncio.sleep(0.05)
    assert published(runner).status is UNHEALTHY
    assert published(runner).message == "timed out after 0.01s"
    await runner.stop()


async def test_a_check_never_overlaps_itself(clock):
    check = ScriptedCheck(name="slow", interval=0.001, delay=0.05)
    runner = build(clock, check)
    runner.start()
    await settle(check)
    await asyncio.sleep(0.02)
    assert check.calls == 1
    await runner.stop()


async def test_stop_closes_every_check(clock):
    first, second = ScriptedCheck(name="a"), ScriptedCheck(name="b")
    runner = build(clock, first, second)
    runner.start()
    await settle(first)
    await runner.stop()
    assert (first.closed, second.closed) == (1, 1)


async def test_stop_survives_a_check_that_fails_to_close(clock):
    class Rude(ScriptedCheck):
        async def aclose(self):
            raise OSError("busy")

    runner = build(clock, Rude(name="rude"))
    runner.start()
    await runner.stop()
    assert runner.snapshot().runner_up is False


async def test_stop_ends_every_open_subscription(clock):
    runner = HealthCheckRunner(service="zeus", clock=clock)
    subscription = runner.register(ScriptedCheck(name="jira"))
    runner.start()
    await runner.stop()
    assert subscription.closed is True


def test_start_twice_is_rejected(clock):
    runner = build(clock, ScriptedCheck(name="a"))

    async def go():
        runner.start()
        with pytest.raises(RuntimeError, match="already started"):
            runner.start()
        await runner.stop()

    asyncio.run(go())


async def test_run_stops_when_the_shutdown_event_is_set(clock):
    check = ScriptedCheck(name="a")
    runner = build(clock, check)
    shutdown = asyncio.Event()
    task = asyncio.create_task(runner.run(shutdown))
    await settle(check)
    shutdown.set()
    await asyncio.wait_for(task, timeout=2)
    assert check.closed == 1


async def test_a_stale_check_degrades_the_service(clock):
    check = ScriptedCheck([True], name="jira", interval=10, stale_after_intervals=2)
    runner = build(clock, check)
    runner.start()
    await settle(check)
    assert runner.status is HEALTHY
    clock.advance(21)
    assert runner.status is DEGRADED
    assert published(runner).status is HEALTHY
    assert published(runner).stale is True
    await runner.stop()


async def test_staleness_never_softens_a_status(clock):
    check = ScriptedCheck([HealthCheckResult.unhealthy("gone")], name="jira", interval=10, stale_after_intervals=2)
    runner = build(clock, check)
    runner.start()
    await settle(check)
    clock.advance(21)
    assert runner.status is DEGRADED
    assert published(runner).status is UNHEALTHY
    await runner.stop()


async def test_a_critical_unhealthy_check_makes_the_service_unhealthy(clock):
    critical = ScriptedCheck([HealthCheckResult.unhealthy("gone")], name="scylla", severity=Severity.CRITICAL)
    important = ScriptedCheck([True], name="jira")
    runner = build(clock, critical, important)
    runner.start()
    await settle(critical)
    await settle(important)
    assert runner.status is UNHEALTHY
    await runner.stop()


async def test_an_important_unhealthy_check_only_degrades_the_service(clock):
    important = ScriptedCheck([HealthCheckResult.unhealthy("gone")], name="jira")
    critical = ScriptedCheck([True], name="scylla", severity=Severity.CRITICAL)
    runner = build(clock, important, critical)
    runner.start()
    await settle(important)
    await settle(critical)
    assert runner.status is DEGRADED
    await runner.stop()


async def test_an_optional_failure_leaves_the_service_healthy(clock):
    optional = ScriptedCheck([HealthCheckResult.unhealthy("gone")], name="jira", severity=Severity.OPTIONAL)
    critical = ScriptedCheck([True], name="scylla", severity=Severity.CRITICAL)
    runner = build(clock, optional, critical)
    runner.start()
    await settle(optional)
    await settle(critical)
    assert runner.status is HEALTHY
    assert published(runner).status is UNHEALTHY
    await runner.stop()


async def test_on_change_fires_once_per_transition_and_names_the_check(clock):
    seen = []
    check = ScriptedCheck([True, HealthCheckResult.unhealthy("gone")], name="jira", interval=0.001)
    runner = build(clock, check, on_change=lambda status, reason: seen.append((status, reason)))
    runner.start()
    await settle(check, calls=2)
    await asyncio.sleep(0.02)
    await runner.stop()
    assert seen[0] == (HEALTHY, "every dependency healthy")
    assert seen[1] == (DEGRADED, "jira unhealthy")


async def test_on_change_awaits_a_coroutine_callback(clock):
    seen = []

    async def record(status, reason):
        seen.append(status)

    check = ScriptedCheck([True], name="jira")
    runner = build(clock, check, on_change=record)
    runner.start()
    await settle(check)
    await spin()
    await runner.stop()
    assert seen == [HEALTHY]


async def test_a_failing_on_change_does_not_reach_the_service(clock, caplog):
    def explode(status, reason):
        raise RuntimeError("systemd is not listening")

    check = ScriptedCheck([True], name="jira")
    runner = build(clock, check, on_change=explode)
    with caplog.at_level(logging.ERROR, logger="qatools_health"):
        runner.start()
        await settle(check)
        await spin()
    assert "on_change callback failed" in caplog.text
    await runner.stop()


async def test_a_status_change_is_logged_once(clock, caplog):
    check = ScriptedCheck(
        [True, HealthCheckResult.unhealthy("gone"), HealthCheckResult.unhealthy("gone"), True],
        name="jira",
        interval=0.001,
    )
    runner = build(clock, check)
    with caplog.at_level(logging.INFO, logger="qatools_health"):
        runner.start()
        await settle(check, calls=4)
        await asyncio.sleep(0.02)
    await runner.stop()
    transitions = [record for record in caplog.records if record.msg.startswith("health check %s %s")]
    assert [record.levelno for record in transitions] == [logging.INFO, logging.WARNING, logging.INFO]


async def test_the_first_runs_are_spread_over_a_second(clock):
    checks = [ScriptedCheck(name=f"check{index}") for index in range(4)]
    runner = build(clock, *checks)
    runner.start()
    await settle(checks[0])
    assert checks[0].calls == 1
    assert checks[3].calls == 0
    await runner.stop()


async def test_a_check_registered_after_start_runs_at_once(clock):
    runner = HealthCheckRunner(service="zeus", clock=clock)
    runner.start()
    check = ScriptedCheck([True], name="jira")
    runner.register(check)
    await settle(check)
    assert check.calls == 1
    await runner.stop()


async def test_registration_is_safe_from_another_thread(clock):
    runner = HealthCheckRunner(service="zeus", clock=clock)
    runner.start()
    check = ScriptedCheck([True], name="jira")
    subscription = await asyncio.to_thread(runner.register, check)
    assert (await subscription.wait_for(HEALTHY, timeout=2)).status is HEALTHY
    await runner.stop()


async def test_a_check_returning_a_bad_type_is_recorded_as_a_failure(clock):
    check = ScriptedCheck(["HEALTHY"], name="jira")
    runner = build(clock, check)
    runner.start()
    await settle(check)
    assert published(runner).status is UNHEALTHY
    assert "not a health check result" in (published(runner).error or "")
    await runner.stop()


async def test_the_snapshot_records_the_timestamps(clock):
    check = ScriptedCheck([True], name="jira")
    runner = build(clock, check)
    runner.start()
    await settle(check)
    assert published(runner).last_run_timestamp == clock.now
    assert published(runner).last_success_timestamp == clock.now
    await runner.stop()


async def test_an_unhealthy_result_leaves_the_last_success_alone(clock):
    check = ScriptedCheck([True, HealthCheckResult.unhealthy("gone")], name="jira", interval=0.001)
    runner = build(clock, check)
    runner.start()
    await settle(check)
    success_at = clock.now
    clock.advance(60)
    await settle(check, calls=2)
    await asyncio.sleep(0.02)
    assert published(runner).last_success_timestamp == success_at
    assert published(runner).last_run_timestamp == clock.now
    await runner.stop()


async def test_a_framework_failure_drops_runner_up_and_stays_inside(clock, caplog):
    check = ScriptedCheck([True], name="jira", interval=0.001)
    runner = build(clock, check)
    with caplog.at_level(logging.ERROR, logger="qatools_health"):
        runner.start()
        await settle(check)
        check.interval = "not a number"
        await asyncio.sleep(0.05)
    check.interval = 0.001
    assert runner.snapshot().runner_up is False
    assert "health check loop for jira stopped" in caplog.text
    await runner.stop()
