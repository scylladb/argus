import asyncio
import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from prometheus_client import CollectorRegistry
from prometheus_client import REGISTRY as DEFAULT_REGISTRY

from qatools_health.check import HealthCheck
from qatools_health.collector import HealthMetricsCollector
from qatools_health.result import HealthCheckResult, coerce_result, exception_result
from qatools_health.snapshot import CheckSnapshot, RunnerSnapshot
from qatools_health.status import HealthCheckStatus, is_worse, worse_of

LOGGER = logging.getLogger("qatools_health")

FIRST_RUN_SPREAD_SECONDS = 1.0

Driver = tuple["CheckState", HealthCheckStatus] | None


@dataclass(slots=True)
class CheckState:
    check: HealthCheck
    status: HealthCheckStatus
    message: str = ""
    error: str | None = None
    duration_seconds: float = 0.0
    last_run_timestamp: float = 0.0
    last_success_timestamp: float = 0.0


class HealthCheckRunner:
    def __init__(
        self,
        checks: Sequence[HealthCheck],
        *,
        service: str,
        version: str = "",
        on_change: Callable[[HealthCheckStatus, str], None] | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        seen: set[str] = set()
        for check in checks:
            if check.name in seen:
                raise ValueError(f"duplicate health check name {check.name!r}")
            seen.add(check.name)

        self.service = service
        self.version = version
        self._on_change = on_change
        self._clock = clock
        self._states = [CheckState(check, check.failure_status) for check in checks]
        self._tasks: list[asyncio.Task[None]] = []
        self._runner_up = False
        self._aggregate = self._compute_aggregate()[0]
        self._collector = HealthMetricsCollector(self.snapshot)

    @property
    def collector(self) -> HealthMetricsCollector:
        return self._collector

    @property
    def status(self) -> HealthCheckStatus:
        return self._compute_aggregate()[0]

    def register(self, registry: CollectorRegistry | None = None) -> None:
        (registry or DEFAULT_REGISTRY).register(self._collector)

    def unregister(self, registry: CollectorRegistry | None = None) -> None:
        (registry or DEFAULT_REGISTRY).unregister(self._collector)

    def start(self) -> None:
        if self._tasks:
            raise RuntimeError("health check runner is already started")
        self._runner_up = True
        total = len(self._states)
        for index, state in enumerate(self._states):
            delay = FIRST_RUN_SPREAD_SECONDS * index / total if total else 0.0
            task = asyncio.create_task(self._loop(state, delay), name=f"healthcheck:{state.check.name}")
            self._tasks.append(task)

    async def stop(self) -> None:
        tasks, self._tasks = self._tasks, []
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        for state in self._states:
            try:
                await state.check.aclose()
            except Exception:  # noqa: BLE001
                LOGGER.exception("health check %s failed to close", state.check.name)
        self._runner_up = False

    async def run(self, shutdown: asyncio.Event) -> None:
        self.start()
        try:
            await shutdown.wait()
        finally:
            await self.stop()

    def snapshot(self) -> RunnerSnapshot:
        now = self._clock()
        aggregate, _ = self._compute_aggregate(now)
        return RunnerSnapshot(
            service=self.service,
            version=self.version,
            aggregate=aggregate,
            runner_up=self._runner_up,
            checks=tuple(
                CheckSnapshot(
                    name=state.check.name,
                    critical=state.check.critical,
                    status=state.status,
                    message=state.message,
                    error=state.error,
                    duration_seconds=state.duration_seconds,
                    last_run_timestamp=state.last_run_timestamp,
                    last_success_timestamp=state.last_success_timestamp,
                    stale=self._is_stale(state, now),
                )
                for state in self._states
            ),
        )

    async def _loop(self, state: CheckState, delay: float) -> None:
        try:
            if delay:
                await asyncio.sleep(delay)
            while True:
                await self._run_once(state)
                await asyncio.sleep(state.check.interval)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            self._runner_up = False
            LOGGER.exception("health check loop for %s stopped", state.check.name)

    async def _run_once(self, state: CheckState) -> None:
        check = state.check
        started = time.monotonic()
        try:
            value = await asyncio.wait_for(check.perform_check(), check.timeout)
            result = coerce_result(value, check.failure_status)
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            message = f"timed out after {check.timeout:g}s"
            result = HealthCheckResult(check.failure_status, message, error=message)
        except Exception as exc:  # noqa: BLE001
            result = exception_result(exc, check.failure_status)
        self._publish(state, result, time.monotonic() - started)

    def _publish(self, state: CheckState, result: HealthCheckResult, duration: float) -> None:
        previous = state.status
        now = self._clock()
        state.status = result.status
        state.message = result.message
        state.error = result.error
        state.duration_seconds = duration
        state.last_run_timestamp = now
        if result.status is HealthCheckStatus.HEALTHY:
            state.last_success_timestamp = now

        if result.status is not previous:
            self._log_transition(state, previous, result)
        self._notify_aggregate()

    def _log_transition(self, state: CheckState, previous: HealthCheckStatus, result: HealthCheckResult) -> None:
        detail = result.message or result.error or ""
        level = logging.WARNING if is_worse(result.status, previous) else logging.INFO
        LOGGER.log(level, "health check %s %s -> %s: %s", state.check.name, previous, result.status, detail)

    def _notify_aggregate(self) -> None:
        aggregate, driver = self._compute_aggregate()
        if aggregate is self._aggregate:
            return
        self._aggregate = aggregate
        reason = f"{driver[0].check.name} {driver[1].lower()}" if driver else "every dependency healthy"
        if self._on_change is None:
            return
        try:
            self._on_change(aggregate, reason)
        except Exception:  # noqa: BLE001
            LOGGER.exception("on_change callback failed for %s", self.service)

    def _compute_aggregate(self, now: float | None = None) -> tuple[HealthCheckStatus, Driver]:
        moment = self._clock() if now is None else now
        effective = [(state, self._effective_status(state, moment)) for state in self._states]

        for state, status in effective:
            if status is HealthCheckStatus.UNHEALTHY and state.check.critical:
                return HealthCheckStatus.UNHEALTHY, (state, status)
        for state, status in effective:
            if status is not HealthCheckStatus.HEALTHY:
                return HealthCheckStatus.DEGRADED, (state, status)
        return HealthCheckStatus.HEALTHY, None

    def _effective_status(self, state: CheckState, now: float) -> HealthCheckStatus:
        staleness = HealthCheckStatus.DEGRADED if self._is_stale(state, now) else HealthCheckStatus.HEALTHY
        return worse_of(state.status, staleness)

    def _is_stale(self, state: CheckState, now: float) -> bool:
        check = state.check
        return (now - state.last_run_timestamp) > check.interval * check.stale_after_intervals
