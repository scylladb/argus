"""Gate a component on its dependencies, and share one dependency between two components.

The publisher sends reports only while its group is HEALTHY. The auditor
subscribes to the same upstream with its own callback, and both hear every
transition from one probe loop.
"""

import argparse
import asyncio
import logging
import tempfile
from collections.abc import Callable
from pathlib import Path

import aiosqlite
from upstream import FlakyUpstream, UpstreamHealthCheck

from qatools_health import HealthCheck, HealthCheckResult, HealthCheckRunner, HealthCheckStatus
from qatools_health.checks import SqliteHealthCheck

HEALTHY = HealthCheckStatus.HEALTHY


class ReportPublisher:
    """Send a report on a loop, but only while every dependency is HEALTHY."""

    def __init__(
        self,
        runner: HealthCheckRunner,
        upstream_url: str,
        database: Path,
        emit: Callable[[str], None],
    ) -> None:
        self._runner = runner
        self._upstream_url = upstream_url
        self._database = database
        self._emit = emit
        self.published = 0

    async def run(self, shutdown: asyncio.Event) -> None:
        """Register the group, wait for HEALTHY before each report, and close on shutdown."""
        dependencies = [
            UpstreamHealthCheck(self._upstream_url),
            SqliteHealthCheck(self._database, name="sqlite:reports", interval=0.5),
        ]
        with self._runner.register_all(dependencies, on_change=self._on_dependencies_change) as gate:
            while not shutdown.is_set():
                try:
                    await gate.wait_for(HEALTHY, timeout=0.5)
                except TimeoutError:
                    continue
                self.published += 1
                self._emit(f"publisher: report {self.published} sent")
                await asyncio.sleep(0.2)

    def _on_dependencies_change(
        self,
        status: HealthCheckStatus,
        reason: str,
        statuses: dict[str, HealthCheckStatus],
    ) -> None:
        verdict = "resumes" if status is HEALTHY else "pauses"
        members = ", ".join(f"{name}={value}" for name, value in sorted(statuses.items()))
        self._emit(f"publisher {verdict}: {reason} ({members})")


class Auditor:
    """Record every transition of the upstream the publisher also depends on."""

    def __init__(self, runner: HealthCheckRunner, upstream_url: str, emit: Callable[[str], None]) -> None:
        self._runner = runner
        self._upstream_url = upstream_url
        self._emit = emit

    async def run(self, shutdown: asyncio.Event) -> None:
        """Hold a subscription to the upstream until shutdown."""
        with self._runner.register(UpstreamHealthCheck(self._upstream_url), on_change=self._on_upstream_change):
            await shutdown.wait()

    def _on_upstream_change(self, check: HealthCheck, result: HealthCheckResult) -> None:
        self._emit(f"auditor heard {check.name} {result.status}")


async def main(
    duration: float = 5.0,
    outage_after: float = 1.5,
    outage_for: float = 1.5,
    emit: Callable[[str], None] = print,
) -> ReportPublisher:
    """Run both components through one outage and one recovery, then stop."""
    upstream = await FlakyUpstream().start()
    runner = HealthCheckRunner(service="gated-example")
    shutdown = asyncio.Event()

    with tempfile.TemporaryDirectory() as directory:
        database = Path(directory) / "reports.db"
        async with aiosqlite.connect(database):
            pass

        publisher = ReportPublisher(runner, upstream.url, database, emit)
        auditor = Auditor(runner, upstream.url, emit)
        components = asyncio.gather(publisher.run(shutdown), auditor.run(shutdown), runner.run(shutdown))

        await asyncio.sleep(outage_after)
        emit(f"upstream goes down after {publisher.published} reports")
        upstream.healthy = False
        await asyncio.sleep(outage_for)
        emit(f"upstream comes back after {publisher.published} reports")
        upstream.healthy = True
        await asyncio.sleep(max(0.0, duration - outage_after - outage_for))

        emit(f"probe loops for the shared upstream: {len(runner.snapshot().checks)} checks")
        shutdown.set()
        await components

    await upstream.close()
    return publisher


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=float, default=5.0)
    arguments = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    asyncio.run(main(duration=arguments.duration))
