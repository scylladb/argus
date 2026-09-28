import asyncio
from types import SimpleNamespace

import httpx2
from prometheus_client import CollectorRegistry
from qatools_health import (
    CheckSnapshot,
    HealthCheckResult,
    HealthCheckRunner,
    HealthCheckStatus,
    RunnerSnapshot,
    Severity,
    healthcheck,
)

from argus.backend.service.health.app import build_app


async def probed_runner(*checks) -> tuple[HealthCheckRunner, CollectorRegistry]:
    registry = CollectorRegistry()
    runner = HealthCheckRunner(service="argus", version="0.0.0")
    runner.register_collector(registry)
    group = runner.register_all(list(checks))
    runner.start()
    while not group.settled:
        await asyncio.sleep(0.01)
    await runner.stop()
    return runner, registry


def check(name, result, severity):
    async def probe():
        return result

    return healthcheck(probe, name=name, severity=severity)


def client_of(app) -> httpx2.AsyncClient:
    return httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url="http://health")


async def client_for(*checks) -> httpx2.AsyncClient:
    return client_of(build_app(*await probed_runner(*checks)))


async def test_health_lists_every_check_with_its_reason():
    client = await client_for(
        check("scylla", HealthCheckResult.healthy("3 of 3 hosts up"), Severity.CRITICAL),
        check("jira_api", HealthCheckResult.unhealthy("myself answered 401"), Severity.IMPORTANT),
    )
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "argus"
    assert body["status"] == "degraded"
    jira = next(item for item in body["checks"] if item["name"] == "jira_api")
    assert jira == {
        "name": "jira_api",
        "severity": "important",
        "status": "unhealthy",
        "message": "myself answered 401",
        "stale": jira["stale"],
        "last_run_timestamp": jira["last_run_timestamp"],
        "last_success_timestamp": 0.0,
    }


async def test_health_reports_the_error_of_a_check_that_raised():
    async def broken():
        raise ConnectionError("no host available")

    client = await client_for(healthcheck(broken, name="scylla", severity=Severity.CRITICAL))
    body = (await client.get("/health")).json()
    assert "no host available" in body["checks"][0]["message"]


async def test_ready_answers_503_while_a_critical_check_fails():
    client = await client_for(check("scylla", HealthCheckStatus.UNHEALTHY, Severity.CRITICAL))
    response = await client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "unhealthy"}


async def test_ready_answers_200_degraded_while_only_an_important_check_fails():
    client = await client_for(
        check("scylla", HealthCheckStatus.HEALTHY, Severity.CRITICAL),
        check("github_api", HealthCheckStatus.UNHEALTHY, Severity.IMPORTANT),
    )
    response = await client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "degraded"}


async def test_metrics_export_the_health_series():
    client = await client_for(check("scylla", HealthCheckStatus.HEALTHY, Severity.CRITICAL))
    response = await client.get("/metrics")
    assert response.status_code == 200
    assert 'healthcheck_status{service="argus"}' in response.text
    assert 'healthcheck_dependency_up{dependency="scylla",service="argus"}' in response.text


async def test_health_reports_a_stale_check_as_the_aggregate_counts_it():
    stale = CheckSnapshot(
        name="jira_api", severity=Severity.IMPORTANT, status=HealthCheckStatus.HEALTHY, stale=True,
        last_run_timestamp=1.0,
    )
    runner = SimpleNamespace(
        snapshot=lambda: RunnerSnapshot(
            service="argus", version="0.0.0", aggregate=HealthCheckStatus.DEGRADED, runner_up=True, checks=(stale,),
        ),
    )
    body = (await client_of(build_app(runner, CollectorRegistry())).get("/health")).json()
    assert body["status"] == "degraded"
    assert body["checks"][0]["status"] == "degraded"
    assert body["checks"][0]["stale"] is True


async def test_health_reports_a_check_that_has_not_run_as_pending():
    waiting = CheckSnapshot(name="scylla", severity=Severity.CRITICAL, status=HealthCheckStatus.UNHEALTHY, stale=True)
    runner = SimpleNamespace(
        snapshot=lambda: RunnerSnapshot(
            service="argus", version="0.0.0", aggregate=HealthCheckStatus.UNHEALTHY, runner_up=True, checks=(waiting,),
        ),
    )
    body = (await client_of(build_app(runner, CollectorRegistry())).get("/health")).json()
    assert body["status"] == "unhealthy"
    assert body["checks"][0]["status"] == "pending"
