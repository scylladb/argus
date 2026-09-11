import asyncio

import pytest
from support import PairedCheck, ScriptedCheck, settle, spin

from qatools_health import (
    HealthCheckResult,
    HealthCheckRunner,
    HealthCheckStatus,
    Severity,
    SubscriptionClosedError,
)

HEALTHY = HealthCheckStatus.HEALTHY
DEGRADED = HealthCheckStatus.DEGRADED
UNHEALTHY = HealthCheckStatus.UNHEALTHY


def build(clock, **kwargs):
    return HealthCheckRunner(service="zeus", clock=clock, **kwargs)


async def test_a_subscription_reads_the_last_result(clock):
    runner = build(clock)
    check = ScriptedCheck([HealthCheckResult.degraded("queue depth 812")], name="queue")
    subscription = runner.register(check)
    assert subscription.result is None
    assert subscription.status is UNHEALTHY
    runner.start()
    await settle(check)
    assert subscription.status is DEGRADED
    assert subscription.result.message == "queue depth 812"
    await runner.stop()


async def test_wait_for_returns_the_current_result_without_waiting(clock):
    runner = build(clock)
    check = ScriptedCheck([True], name="jira")
    subscription = runner.register(check)
    runner.start()
    await settle(check)
    assert (await subscription.wait_for(HEALTHY, timeout=0)).status is HEALTHY
    await runner.stop()


async def test_wait_for_resolves_on_the_first_probe(clock):
    runner = build(clock)
    check = ScriptedCheck([True], name="jira")
    subscription = runner.register(check)
    runner.start()
    assert (await subscription.wait_for(HEALTHY, timeout=2)).status is HEALTHY
    await runner.stop()


async def test_wait_for_times_out(clock):
    runner = build(clock)
    check = ScriptedCheck([HealthCheckResult.unhealthy("gone")], name="jira")
    subscription = runner.register(check)
    runner.start()
    with pytest.raises(TimeoutError):
        await subscription.wait_for(HEALTHY, timeout=0.05)
    await runner.stop()


async def test_wait_for_needs_a_status(clock):
    subscription = build(clock).register(ScriptedCheck(name="jira"))
    with pytest.raises(ValueError, match="at least one status"):
        await subscription.wait_for()


async def test_wait_for_on_a_closed_subscription_raises(clock):
    subscription = build(clock).register(ScriptedCheck(name="jira"))
    subscription.close()
    with pytest.raises(SubscriptionClosedError):
        await subscription.wait_for(HEALTHY)


async def test_a_close_while_waiting_raises(clock):
    runner = build(clock)
    check = ScriptedCheck([HealthCheckResult.unhealthy("gone")], name="jira")
    subscription = runner.register(check)
    runner.start()
    waiter = asyncio.create_task(subscription.wait_for(HEALTHY))
    await settle(check)
    subscription.close()
    with pytest.raises(SubscriptionClosedError):
        await waiter
    await runner.stop()


async def test_a_subscriber_hears_every_transition_once(clock):
    seen = []
    runner = build(clock)
    check = ScriptedCheck([True, HealthCheckResult.unhealthy("gone"), True], name="jira", interval=0.001)
    runner.register(check, on_change=lambda subject, result: seen.append(result.status))
    runner.start()
    await settle(check, calls=3)
    await asyncio.sleep(0.02)
    await runner.stop()
    assert seen == [HEALTHY, UNHEALTHY, HEALTHY]


async def test_a_never_run_check_delivers_no_callback(clock):
    seen = []
    runner = build(clock)
    runner.register(ScriptedCheck(name="jira"), on_change=lambda subject, result: seen.append(result))
    await spin()
    assert seen == []


async def test_a_late_subscriber_gets_the_current_result(clock):
    seen = []
    runner = build(clock)
    check = ScriptedCheck([True], name="jira")
    runner.register(check)
    runner.start()
    await settle(check)
    runner.register(ScriptedCheck(name="jira"), on_change=lambda subject, result: seen.append(result.status))
    await spin()
    assert seen == [HEALTHY]
    await runner.stop()


async def test_a_failing_subscriber_callback_keeps_the_subscription_open(clock, caplog):
    runner = build(clock)
    check = ScriptedCheck([True], name="jira")

    def explode(subject, result):
        raise RuntimeError("the source is gone")

    subscription = runner.register(check, on_change=explode)
    runner.start()
    await settle(check)
    await spin()
    assert subscription.closed is False
    assert "on_change callback failed for jira" in caplog.text
    await runner.stop()


async def test_a_subscription_is_a_context_manager(clock):
    runner = build(clock)
    check = ScriptedCheck([True], name="jira")
    with runner.register(check) as subscription:
        assert subscription.closed is False
    assert subscription.closed is True


async def test_the_last_close_retires_the_check(clock):
    runner = build(clock)
    check = ScriptedCheck([True], name="jira")
    first = runner.register(check)
    second = runner.register(ScriptedCheck(name="jira"))
    runner.start()
    await settle(check)
    first.close()
    await spin()
    assert runner.snapshot().checks[0].subscribers == 1
    assert check.closed == 0
    second.close()
    await spin()
    assert runner.snapshot().checks == ()
    assert check.closed == 1
    await runner.stop()


async def test_retiring_a_check_takes_it_out_of_the_aggregate(clock):
    runner = build(clock)
    failing = ScriptedCheck([HealthCheckResult.unhealthy("gone")], name="scylla", severity=Severity.CRITICAL)
    healthy = ScriptedCheck([True], name="jira")
    subscription = runner.register(failing)
    runner.register(healthy)
    runner.start()
    await settle(failing)
    await settle(healthy)
    assert runner.status is UNHEALTHY
    subscription.close()
    await spin()
    assert runner.status is HEALTHY
    await runner.stop()


async def test_a_retired_identity_can_be_registered_again(clock):
    runner = build(clock)
    first = ScriptedCheck([True], name="jira")
    runner.register(first).close()
    await spin()
    second = ScriptedCheck([True], name="jira")
    runner.register(second)
    runner.start()
    await settle(second)
    assert second.calls == 1
    await runner.stop()


async def test_the_group_reads_the_worst_member(clock):
    runner = build(clock)
    jenkins = ScriptedCheck([True], name="jenkins_api")
    github = ScriptedCheck([HealthCheckResult.unhealthy("gone")], name="github_api")
    group = runner.register_all([jenkins, github])
    runner.start()
    await settle(jenkins)
    await settle(github)
    await spin()
    assert group.status is UNHEALTHY
    assert len(group.members) == 2
    await runner.stop()


async def test_the_group_looks_a_member_up_by_identity(clock):
    runner = build(clock)
    jenkins = ScriptedCheck([True], name="jenkins_api")
    group = runner.register_all([jenkins])
    assert group[ScriptedCheck(name="jenkins_api")] is group.members[0]
    with pytest.raises(KeyError):
        group[PairedCheck(name="acli")]


async def test_the_group_waits_for_every_member(clock):
    runner = build(clock)
    first, second = ScriptedCheck([True], name="a"), ScriptedCheck([True], name="b")
    group = runner.register_all([first, second])
    runner.start()
    assert await group.wait_for(HEALTHY, timeout=3) is HEALTHY
    await runner.stop()


async def test_the_group_callback_names_the_member_behind_the_status(clock):
    seen = []
    runner = build(clock)
    good = ScriptedCheck([True], name="a")
    bad = ScriptedCheck([HealthCheckResult.unhealthy("gone")], name="b")
    runner.register_all([good, bad], on_change=lambda status, reason: seen.append((status, reason)))
    runner.start()
    await settle(good)
    await settle(bad)
    await spin()
    assert seen[-1] == (UNHEALTHY, "b unhealthy")
    await runner.stop()


async def test_the_group_reports_a_healthy_reason(clock):
    seen = []
    runner = build(clock)
    check = ScriptedCheck([True], name="a")
    runner.register_all([check], on_change=lambda status, reason: seen.append(reason))
    runner.start()
    await settle(check)
    await spin()
    assert seen == ["every dependency healthy"]
    await runner.stop()


async def test_the_group_closes_every_member(clock):
    runner = build(clock)
    first, second = ScriptedCheck([True], name="a"), ScriptedCheck([True], name="b")
    with runner.register_all([first, second]) as group:
        runner.start()
        await settle(first)
        assert group.status is not None
    await spin()
    assert (first.closed, second.closed) == (1, 1)
    assert runner.snapshot().checks == ()


async def test_a_group_wait_in_flight_raises_when_the_group_closes(clock):
    runner = build(clock)
    check = ScriptedCheck([HealthCheckResult.unhealthy("gone")], name="a")
    group = runner.register_all([check])
    runner.start()
    waiter = asyncio.create_task(group.wait_for(HEALTHY))
    await settle(check)
    group.close()
    with pytest.raises(SubscriptionClosedError):
        await waiter
    await runner.stop()


async def test_a_closed_group_refuses_to_wait(clock):
    runner = build(clock)
    group = runner.register_all([ScriptedCheck(name="a")])
    group.close()
    with pytest.raises(SubscriptionClosedError):
        await group.wait_for(HEALTHY)
    with pytest.raises(ValueError, match="at least one status"):
        await runner.register_all([ScriptedCheck(name="b")]).wait_for()


def test_register_all_registers_every_check_or_none(clock):
    runner = build(clock)
    with pytest.raises(ValueError):
        runner.register_all([ScriptedCheck(name="a"), PairedCheck(name="a")])
    assert runner.snapshot().checks == ()


async def test_register_all_collapses_a_dependency_the_wiring_already_holds(clock):
    runner = build(clock)
    check = ScriptedCheck([True], name="jenkins_api")
    wiring = runner.register(check)
    group = runner.register_all([ScriptedCheck(name="jenkins_api")])
    assert group.members[0].check is check
    assert len(runner.snapshot().checks) == 1
    assert runner.snapshot().checks[0].subscribers == 2
    group.close()
    await spin()
    assert check.closed == 0
    wiring.close()
    await spin()
    assert check.closed == 1


async def test_the_group_wait_returns_at_once_once_every_member_answered(clock):
    runner = build(clock)
    check = ScriptedCheck([True], name="a")
    group = runner.register_all([check])
    runner.start()
    await settle(check)
    await spin()
    assert await group.wait_for(HEALTHY, timeout=0) is HEALTHY
    assert group.closed is False
    await runner.stop()


async def test_an_empty_group_reads_healthy(clock):
    group = build(clock).register_all([])
    assert group.status is HEALTHY
    assert await group.wait_for(HEALTHY, timeout=0) is HEALTHY
    group.close()
