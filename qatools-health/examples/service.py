"""Run a whole service with health checks, callbacks and Prometheus metrics.

The upstream goes down after --outage-after seconds and comes back after
--outage-for seconds. Pass --port to serve /metrics.
"""

import argparse
import asyncio
import logging
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

import aiosqlite
from prometheus_client import CollectorRegistry, generate_latest, start_http_server
from upstream import FlakyUpstream, UpstreamHealthCheck

from qatools_health import HealthCheck, HealthCheckResult, HealthCheckRunner, HealthCheckStatus, Severity, healthcheck
from qatools_health.checks import SqliteHealthCheck, StalenessHealthCheck, TcpHealthCheck

QUEUE_DEPTH_LIMIT = 100


class Worker:
    """A background loop that records when it last ran."""

    def __init__(self) -> None:
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.last_tick: float | None = None

    async def run(self, shutdown: asyncio.Event) -> None:
        """Tick every 100 milliseconds until shutdown."""
        while not shutdown.is_set():
            self.last_tick = time.time()
            await asyncio.sleep(0.1)


def build_runner(
    worker: Worker,
    upstream: FlakyUpstream,
    database: Path,
    emit: Callable[[str], None],
) -> HealthCheckRunner:
    """Build the runner and register every dependency of the service."""

    @healthcheck(name="queue_depth", interval=0.25)
    async def queue_depth() -> HealthCheckResult:
        depth = worker.queue.qsize()
        if depth > QUEUE_DEPTH_LIMIT:
            return HealthCheckResult.degraded(f"queue depth {depth} over {QUEUE_DEPTH_LIMIT}")
        return HealthCheckResult.healthy(f"queue depth {depth}")

    def on_service_change(
        status: HealthCheckStatus,
        reason: str,
        statuses: dict[str, HealthCheckStatus],
    ) -> None:
        failing = sorted(name for name, value in statuses.items() if value is not HealthCheckStatus.HEALTHY)
        emit(f"service {status}: {reason} (not healthy: {', '.join(failing) or 'none'})")

    def on_upstream_change(check: HealthCheck, result: HealthCheckResult) -> None:
        emit(f"{check.name} {result.status}: {result.message or result.error}")

    runner = HealthCheckRunner(service="example", version="1.0.0", on_change=on_service_change)
    runner.register(UpstreamHealthCheck(upstream.url), on_change=on_upstream_change)
    runner.register(TcpHealthCheck(upstream.host, upstream.port, name="upstream_tcp", interval=0.5))
    runner.register(SqliteHealthCheck(database, name="sqlite:example", interval=0.5))
    runner.register(
        StalenessHealthCheck(
            lambda: worker.last_tick,
            warn_after=1.0,
            fail_after=3.0,
            name="worker_tick",
            interval=0.25,
        )
    )
    runner.register(queue_depth)
    runner.register(TcpHealthCheck("127.0.0.1", 1, name="optional_cache", severity=Severity.OPTIONAL, timeout=0.5))
    return runner


def health_lines(registry: CollectorRegistry) -> list[str]:
    """Return the aggregate and the per-dependency lines of the exposition."""
    exposition = generate_latest(registry).decode()
    wanted = ("healthcheck_status{", "healthcheck_dependency_up{")
    return [line for line in exposition.splitlines() if line.startswith(wanted)]


async def main(
    duration: float = 6.0,
    outage_after: float = 2.0,
    outage_for: float = 2.0,
    port: int | None = None,
    emit: Callable[[str], None] = print,
) -> CollectorRegistry:
    """Run the service through one outage and one recovery, then stop."""
    worker = Worker()
    upstream = await FlakyUpstream().start()
    shutdown = asyncio.Event()
    registry = CollectorRegistry()

    with tempfile.TemporaryDirectory() as directory:
        database = Path(directory) / "example.db"
        async with aiosqlite.connect(database) as connection:
            await connection.execute("CREATE TABLE IF NOT EXISTS jobs (id INTEGER PRIMARY KEY)")

        runner = build_runner(worker, upstream, database, emit)
        runner.register_collector(registry)
        if port is not None:
            start_http_server(port, registry=registry)
            emit(f"metrics on http://127.0.0.1:{port}/metrics")

        services = asyncio.gather(worker.run(shutdown), runner.run(shutdown))

        await asyncio.sleep(outage_after)
        emit("upstream goes down")
        upstream.healthy = False
        await asyncio.sleep(outage_for)
        emit("upstream comes back")
        upstream.healthy = True
        await asyncio.sleep(max(0.0, duration - outage_after - outage_for))

        for line in health_lines(registry):
            emit(line)

        shutdown.set()
        await services
        runner.unregister_collector(registry)

    await upstream.close()
    return registry


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=float, default=6.0)
    parser.add_argument("--outage-after", type=float, default=2.0)
    parser.add_argument("--outage-for", type=float, default=2.0)
    parser.add_argument("--port", type=int, default=None)
    arguments = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    asyncio.run(
        main(
            duration=arguments.duration,
            outage_after=arguments.outage_after,
            outage_for=arguments.outage_for,
            port=arguments.port,
        )
    )
