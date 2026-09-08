import asyncio
import logging
import threading
import time
from collections.abc import Callable, Iterable

from prometheus_client import CollectorRegistry
from prometheus_client import REGISTRY as DEFAULT_REGISTRY

from qatools_health.check import HealthCheck
from qatools_health.collector import HealthMetricsCollector
from qatools_health.result import HealthCheckResult, coerce_result, exception_result
from qatools_health.snapshot import CheckSnapshot, RunnerSnapshot
from qatools_health.status import HealthCheckStatus, Severity, is_worse, strictest_severity
from qatools_health.subscription import (
    EVERYTHING_HEALTHY,
    CheckState,
    HealthCheckGroup,
    HealthCheckSubscription,
    OnChange,
    OnGroupChange,
    call_back,
)

LOGGER = logging.getLogger("qatools_health")

FIRST_RUN_SPREAD_SECONDS = 1.0

Driver = tuple[CheckState, HealthCheckStatus] | None


def merge_policy(running: HealthCheck, incoming: HealthCheck) -> None:
    running.severity = strictest_severity(running.severity, incoming.severity)
    running.interval = min(running.interval, incoming.interval)
    running.timeout = min(running.timeout, incoming.timeout)
    running.stale_after_intervals = min(running.stale_after_intervals, incoming.stale_after_intervals)


class HealthCheckRunner:
    def __init__(
        self,
        *,
        service: str,
        version: str = "",
        on_change: OnGroupChange | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.service = service
        self.version = version
        self._on_change = on_change
        self._clock = clock
        self._lock = threading.RLock()
        self._states: dict[tuple[object, ...], CheckState] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._background: set[asyncio.Task[None]] = set()
        self._started = False
        self._stopped = False
        self._runner_up = False
        self._aggregate = HealthCheckStatus.HEALTHY
        self._collector = HealthMetricsCollector(self.snapshot)

    @property
    def collector(self) -> HealthMetricsCollector:
        return self._collector

    @property
    def status(self) -> HealthCheckStatus:
        return self._compute()[0]

    def register(self, check: HealthCheck, *, on_change: OnChange | None = None) -> HealthCheckSubscription:
        state = self._intern(check)
        subscription = HealthCheckSubscription(state, on_change)
        state.attach(subscription)
        self._schedule(self._activate, state, subscription)
        self._refresh_aggregate()
        return subscription

    def register_all(
        self,
        checks: Iterable[HealthCheck],
        *,
        on_change: OnGroupChange | None = None,
    ) -> HealthCheckGroup:
        batch = tuple(checks)
        with self._lock:
            self._validate(batch)
            members = [self._subscribe(check) for check in batch]
        for state, subscription in members:
            self._schedule(self._activate, state, subscription)
        self._refresh_aggregate()
        return HealthCheckGroup([subscription for _, subscription in members], on_change)

    def register_collector(self, registry: CollectorRegistry | None = None) -> None:
        (registry or DEFAULT_REGISTRY).register(self._collector)

    def unregister_collector(self, registry: CollectorRegistry | None = None) -> None:
        (registry or DEFAULT_REGISTRY).unregister(self._collector)

    def start(self) -> None:
        if self._started:
            raise RuntimeError("health check runner is already started")
        self._loop = asyncio.get_running_loop()
        self._started = True
        self._stopped = False
        self._runner_up = True
        with self._lock:
            states = list(self._states.values())
        total = len(states)
        for index, state in enumerate(states):
            delay = FIRST_RUN_SPREAD_SECONDS * index / total if total else 0.0
            self._arm(state, delay)
        self._refresh_aggregate()

    async def stop(self) -> None:
        self._stopped = True
        self._started = False
        with self._lock:
            states = list(self._states.values())
        for state in states:
            await self._teardown(state)
        for state in states:
            for subscription in tuple(state.subscriptions):
                subscription.close()
        pending, self._background = self._background, set()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        self._runner_up = False

    async def run(self, shutdown: asyncio.Event) -> None:
        self.start()
        try:
            await shutdown.wait()
        finally:
            await self.stop()

    def snapshot(self) -> RunnerSnapshot:
        now = self._clock()
        with self._lock:
            aggregate, _ = self._compute(now)
            return RunnerSnapshot(
                service=self.service,
                version=self.version,
                aggregate=aggregate,
                runner_up=self._runner_up,
                checks=tuple(
                    CheckSnapshot(
                        name=state.check.name,
                        severity=state.check.severity,
                        status=state.status,
                        message=state.message,
                        error=state.error,
                        duration_seconds=state.duration_seconds,
                        last_run_timestamp=state.last_run_timestamp,
                        last_success_timestamp=state.last_success_timestamp,
                        stale=state.is_stale(now),
                        subscribers=len(state.subscriptions),
                    )
                    for state in self._states.values()
                ),
            )

    def _validate(self, batch: Iterable[HealthCheck]) -> None:
        names = {state.check.name: identity for identity, state in self._states.items()}
        owners = {identity: state.check.name for identity, state in self._states.items()}
        for check in batch:
            identity = check.identity()
            claimed = names.get(check.name)
            if claimed is not None and claimed != identity:
                raise ValueError(f"health check name {check.name!r} already names another dependency")
            owner = owners.get(identity)
            if owner is not None and owner != check.name:
                raise ValueError(f"health check {check.name!r} is the dependency already registered as {owner!r}")
            names[check.name] = identity
            owners[identity] = check.name

    def _intern(self, check: HealthCheck) -> CheckState:
        with self._lock:
            self._validate([check])
            state, _ = self._slot(check)
            return state

    def _subscribe(self, check: HealthCheck) -> tuple[CheckState, HealthCheckSubscription]:
        state, _ = self._slot(check)
        subscription = HealthCheckSubscription(state)
        state.attach(subscription)
        return state, subscription

    def _slot(self, check: HealthCheck) -> tuple[CheckState, bool]:
        identity = check.identity()
        state = self._states.get(identity)
        if state is None:
            state = CheckState(
                check=check,
                identity=identity,
                clock=self._clock,
                lock=self._lock,
                retire=self._retire,
            )
            self._states[identity] = state
            return state, True
        merge_policy(state.check, check)
        return state, False

    def _activate(self, state: CheckState, subscription: HealthCheckSubscription) -> None:
        if self._started and state.task is None and not state.retired:
            self._arm(state, 0.0)
        if state.result is not None:
            self._spawn(self._deliver_current, state, subscription)

    async def _deliver_current(self, state: CheckState, subscription: HealthCheckSubscription) -> None:
        result = state.result
        if result is not None:
            await subscription.deliver(result)

    def _arm(self, state: CheckState, delay: float) -> None:
        if state.task is not None or state.retired:
            return
        state.task = asyncio.create_task(self._probe_loop(state, delay), name=f"healthcheck:{state.check.name}")

    def _retire(self, state: CheckState) -> None:
        if self._stopped or state.retired:
            return
        with self._lock:
            if state.subscriptions:
                return
            state.retired = True
            self._states.pop(state.identity, None)
        self._spawn(self._teardown, state)
        self._refresh_aggregate()

    async def _teardown(self, state: CheckState) -> None:
        state.retired = True
        task, state.task = state.task, None
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        probe = state.probe
        if probe is not None and not probe.done():
            await asyncio.gather(probe, return_exceptions=True)
        try:
            await state.check.aclose()
        except Exception:  # noqa: BLE001
            LOGGER.exception("health check %s failed to close", state.check.name)

    async def _probe_loop(self, state: CheckState, delay: float) -> None:
        try:
            if delay:
                await asyncio.sleep(delay)
            while True:
                state.probe = asyncio.create_task(self._run_once(state), name=f"probe:{state.check.name}")
                await asyncio.shield(state.probe)
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
            result = coerce_result(value)
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            message = f"timed out after {check.timeout:g}s"
            result = HealthCheckResult(HealthCheckStatus.UNHEALTHY, message, error=message)
        except Exception as exc:  # noqa: BLE001
            result = exception_result(exc)
        await self._publish(state, result, time.monotonic() - started)

    async def _publish(self, state: CheckState, result: HealthCheckResult, duration: float) -> None:
        with self._lock:
            previous = state.status
            now = self._clock()
            state.status = result.status
            state.message = result.message
            state.error = result.error
            state.result = result
            state.duration_seconds = duration
            state.last_run_timestamp = now
            if result.status is HealthCheckStatus.HEALTHY:
                state.last_success_timestamp = now
            subscriptions = tuple(state.subscriptions)

        if result.status is not previous:
            self._log_transition(state, previous, result)
        for subscription in subscriptions:
            await subscription.deliver(result)
        await self._notify_aggregate()

    def _log_transition(self, state: CheckState, previous: HealthCheckStatus, result: HealthCheckResult) -> None:
        detail = result.message or result.error or ""
        level = logging.WARNING if is_worse(result.status, previous) else logging.INFO
        LOGGER.log(level, "health check %s %s -> %s: %s", state.check.name, previous, result.status, detail)

    async def _notify_aggregate(self) -> None:
        with self._lock:
            aggregate, driver = self._compute()
            changed = aggregate is not self._aggregate
            self._aggregate = aggregate
            reason = self._reason(driver)
        if changed and self._on_change is not None:
            await call_back(self._on_change, aggregate, reason, subject=self.service)

    def _refresh_aggregate(self) -> None:
        if not self._started or self._loop is None:
            with self._lock:
                self._aggregate = self._compute()[0]
            return
        self._spawn(self._notify_aggregate)

    def _compute(self, now: float | None = None) -> tuple[HealthCheckStatus, Driver]:
        moment = self._clock() if now is None else now
        with self._lock:
            effective = [(state, state.effective_status(moment)) for state in self._states.values()]

        for state, status in effective:
            if status is HealthCheckStatus.UNHEALTHY and state.check.severity is Severity.CRITICAL:
                return HealthCheckStatus.UNHEALTHY, (state, status)
        for state, status in effective:
            if status is not HealthCheckStatus.HEALTHY and state.check.severity is not Severity.OPTIONAL:
                return HealthCheckStatus.DEGRADED, (state, status)
        return HealthCheckStatus.HEALTHY, None

    def _reason(self, driver: Driver) -> str:
        if driver is None:
            return EVERYTHING_HEALTHY
        state, status = driver
        return f"{state.check.name} {status.lower()}"

    def _schedule(self, fn: Callable[..., None], *args: object) -> None:
        loop = self._loop
        if loop is None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                return
        if loop.is_closed():
            return
        loop.call_soon_threadsafe(fn, *args)

    def _spawn(self, coroutine: Callable[..., object], *args: object) -> None:
        def launch() -> None:
            task = asyncio.ensure_future(coroutine(*args))
            self._background.add(task)
            task.add_done_callback(self._background.discard)

        self._schedule(launch)
