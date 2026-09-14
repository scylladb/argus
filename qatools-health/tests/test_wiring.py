import asyncio

import aiosqlite
import httpx
from prometheus_client import CollectorRegistry, generate_latest
from support import spin

from qatools_health import HealthCheckResult, HealthCheckRunner, HealthCheckStatus, healthcheck
from qatools_health.checks import (
    AnthropicApiHealthCheck,
    GitHubApiHealthCheck,
    JenkinsApiHealthCheck,
    SqliteHealthCheck,
    StalenessHealthCheck,
)

HEALTHY = HealthCheckStatus.HEALTHY


def stub_client(base_url="", json=None):
    def handle(request):
        return httpx.Response(200, json=json if json is not None else {})

    return httpx.AsyncClient(base_url=base_url, transport=httpx.MockTransport(handle))


async def test_a_service_wires_the_runner_the_way_the_readme_shows():
    depth = 0

    @healthcheck(name="queue_depth", interval=30)
    async def queue_depth():
        if depth > 500:
            return HealthCheckResult.degraded(f"queue depth {depth} over 500")
        return None

    store = await aiosqlite.connect(":memory:")
    registry = CollectorRegistry()
    shutdown = asyncio.Event()
    runner = HealthCheckRunner(service="zeus", version="1.4.0")

    runner.register(AnthropicApiHealthCheck("key", client=stub_client()))
    runner.register(queue_depth)
    runner.register(SqliteHealthCheck(store, name="sqlite:context"))
    runner.register(StalenessHealthCheck(lambda: 1_000_000.0, warn_after=900, fail_after=3600, name="jenkins_poll"))
    runner.register_collector(registry)

    serving = asyncio.create_task(runner.run(shutdown))

    jenkins = JenkinsApiHealthCheck(client=stub_client("https://jenkins.test"))
    github = GitHubApiHealthCheck("token", client=stub_client(json={"resources": {"core": {"remaining": 1}}}))

    with runner.register_all([jenkins, github]) as deps:
        assert await deps.wait_for(HEALTHY, timeout=5) is HEALTHY
        exposition = generate_latest(registry).decode()
        assert 'healthcheck_dependency_up{dependency="jenkins_api",service="zeus"} 1.0' in exposition
        assert 'healthcheck_subscribers{dependency="github_api",service="zeus"} 1.0' in exposition
        assert "queue depth" not in exposition

    await spin()
    assert 'dependency="jenkins_api"' not in generate_latest(registry).decode()

    shutdown.set()
    await asyncio.wait_for(serving, timeout=5)
    assert 'healthcheck_runner_up{service="zeus"} 0.0' in generate_latest(registry).decode()
    runner.unregister_collector(registry)
    await store.close()
