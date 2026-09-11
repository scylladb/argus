"""The subscription over one running check, and the group over several."""

import asyncio
import inspect
import logging
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from qatools_health.check import HealthCheck
from qatools_health.result import HealthCheckResult
from qatools_health.status import STATUS_ORDER, HealthCheckStatus, worse_of

LOGGER = logging.getLogger("qatools_health")

OnChange = Callable[[HealthCheck, HealthCheckResult], Awaitable[None] | None]
OnGroupChange = Callable[[HealthCheckStatus, str], Awaitable[None] | None]

EVERYTHING_HEALTHY = "every dependency healthy"


class SubscriptionClosedError(RuntimeError):
    """Raised when a caller waits on a subscription that is already closed."""


async def call_back(callback: Any, *args: Any, subject: str) -> None:
    """Call a change callback and log whatever it raises.

    The callback belongs to the service, not to the runner. A callback that
    fails must not stop the probe loop that reported the change.
    """
    try:
        outcome = callback(*args)
        if inspect.isawaitable(outcome):
            await outcome
    except Exception:  # noqa: BLE001
        LOGGER.exception("on_change callback failed for %s", subject)


@dataclass(slots=True)
class CheckState:
    """Everything the runner knows about one check and its subscribers.

    Two registrations of one dependency share one state, so they share one probe
    loop and one published result.
    """

    check: HealthCheck
    identity: tuple[object, ...]
    clock: Callable[[], float]
    lock: Any
    retire: Callable[["CheckState"], None]
    status: HealthCheckStatus = HealthCheckStatus.UNHEALTHY
    message: str = ""
    error: str | None = None
    duration_seconds: float = 0.0
    last_run_timestamp: float = 0.0
    last_success_timestamp: float = 0.0
    result: HealthCheckResult | None = None
    subscriptions: list["HealthCheckSubscription"] = field(default_factory=list)
    task: asyncio.Task[None] | None = None
    probe: asyncio.Task[None] | None = None
    retired: bool = False

    def is_stale(self, now: float | None = None) -> bool:
        """Report whether the last result is older than the staleness window."""
        moment = self.clock() if now is None else now
        return (moment - self.last_run_timestamp) > self.check.interval * self.check.stale_after_intervals

    def effective_status(self, now: float | None = None) -> HealthCheckStatus:
        """Return the published status, degraded to at least DEGRADED when stale."""
        staleness = HealthCheckStatus.DEGRADED if self.is_stale(now) else HealthCheckStatus.HEALTHY
        return worse_of(self.status, staleness)

    def attach(self, subscription: "HealthCheckSubscription") -> None:
        """Add one subscriber to this check."""
        with self.lock:
            self.subscriptions.append(subscription)

    def detach(self, subscription: "HealthCheckSubscription") -> None:
        """Remove one subscriber, and retire the check when the last one leaves."""
        with self.lock:
            if subscription in self.subscriptions:
                self.subscriptions.remove(subscription)
            abandoned = not self.subscriptions
        if abandoned:
            self.retire(self)


class HealthCheckSubscription:
    """One holder of one running check.

    The subscription keeps the check alive and delivers every status change to
    the callback. Close it to release the check. Use it as a context manager to
    close it on the way out.
    """

    def __init__(self, state: CheckState, on_change: OnChange | None = None) -> None:
        self._state = state
        self._on_change = on_change
        self._closed = False
        self._seen: HealthCheckStatus | None = None
        self._waiters: list[tuple[frozenset[HealthCheckStatus], asyncio.Future[HealthCheckResult]]] = []
        self._listeners: list[Callable[["HealthCheckSubscription"], Awaitable[None]]] = []

    @property
    def check(self) -> HealthCheck:
        """The check instance the runner is probing."""
        return self._state.check

    @property
    def status(self) -> HealthCheckStatus:
        """The worst status among the members."""
        """The status of the check right now, staleness included."""
        return self._state.effective_status()

    @property
    def result(self) -> HealthCheckResult | None:
        """The last published result, or None before the first run finished."""
        return self._state.result

    @property
    def closed(self) -> bool:
        """Whether this group has been closed."""
        """Whether this subscription has been closed."""
        return self._closed

    def add_listener(self, listener: Callable[["HealthCheckSubscription"], Awaitable[None]]) -> None:
        """Add a listener that a group uses to follow its members."""
        self._listeners.append(listener)

    async def deliver(self, result: HealthCheckResult) -> None:
        """Hand one published result to the waiters, the callback and the listeners."""
        if self._closed:
            return
        previous, self._seen = self._seen, result.status
        self._resolve(result)
        if previous is not None and previous is result.status:
            return
        if self._on_change is not None:
            await call_back(self._on_change, self._state.check, result, subject=self._state.check.name)
        for listener in tuple(self._listeners):
            await listener(self)

    async def wait_for(
        self,
        *statuses: HealthCheckStatus,
        timeout: float | None = None,
    ) -> HealthCheckResult:
        """Wait until the check reaches one of the statuses, and return that result.

        A check already in one of the statuses returns at once. A closed
        subscription raises SubscriptionClosedError, and so does one that closes
        while a caller waits.
        """
        if not statuses:
            raise ValueError("wait_for needs at least one status")
        if self._closed:
            raise SubscriptionClosedError(f"the subscription to {self._state.check.name} is closed")
        wanted = frozenset(statuses)
        settled = self._state.result
        if settled is not None and self._state.effective_status() in wanted:
            return settled
        future: asyncio.Future[HealthCheckResult] = asyncio.get_running_loop().create_future()
        entry = (wanted, future)
        self._waiters.append(entry)
        try:
            return await asyncio.wait_for(future, timeout)
        finally:
            if entry in self._waiters:
                self._waiters.remove(entry)

    def close(self) -> None:
        """Release the check. Waiters raise, and the last close retires the check."""
        if self._closed:
            return
        self._closed = True
        self._abandon_waiters()
        self._listeners.clear()
        self._state.detach(self)

    def __enter__(self) -> "HealthCheckSubscription":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _resolve(self, result: HealthCheckResult) -> None:
        status = self._state.effective_status()
        pending = []
        for entry in self._waiters:
            wanted, future = entry
            if future.done():
                continue
            if status in wanted:
                future.set_result(result)
            else:
                pending.append(entry)
        self._waiters = pending

    def _abandon_waiters(self) -> None:
        waiters, self._waiters = self._waiters, []
        for _, future in waiters:
            if not future.done():
                future.set_exception(SubscriptionClosedError(f"the subscription to {self._state.check.name} closed"))


class HealthCheckGroup:
    """One holder of several running checks, reported as one status.

    The group status is the worst status among its members. The callback fires
    on a change of that worst status, not on every member change.
    """

    def __init__(self, members: Iterable[HealthCheckSubscription], on_change: OnGroupChange | None = None) -> None:
        self._members = tuple(members)
        self._on_change = on_change
        self._closed = False
        self._seen: HealthCheckStatus | None = None
        self._waiters: list[tuple[frozenset[HealthCheckStatus], asyncio.Future[HealthCheckStatus]]] = []
        for member in self._members:
            member.add_listener(self._member_changed)

    @property
    def members(self) -> tuple[HealthCheckSubscription, ...]:
        """The subscriptions in this group, in registration order."""
        return self._members

    @property
    def status(self) -> HealthCheckStatus:
        """The worst status among the members."""
        return worse_of(*(member.status for member in self._members))

    @property
    def closed(self) -> bool:
        """Whether this group has been closed."""
        return self._closed

    def __getitem__(self, check: HealthCheck) -> HealthCheckSubscription:
        """Return the member that holds the dependency this check names."""
        identity = check.identity()
        for member in self._members:
            if member.check.identity() == identity:
                return member
        raise KeyError(check.name)

    async def wait_for(
        self,
        *statuses: HealthCheckStatus,
        timeout: float | None = None,
    ) -> HealthCheckStatus:
        """Wait until the group reaches one of the statuses, and return it.

        A group already in one of the statuses returns at once, but only after every
        member has published a first result.
        """
        if not statuses:
            raise ValueError("wait_for needs at least one status")
        if self._closed:
            raise SubscriptionClosedError("the group is closed")
        wanted = frozenset(statuses)
        status = self.status
        if status in wanted and all(member.result is not None for member in self._members):
            return status
        future: asyncio.Future[HealthCheckStatus] = asyncio.get_running_loop().create_future()
        entry = (wanted, future)
        self._waiters.append(entry)
        try:
            return await asyncio.wait_for(future, timeout)
        finally:
            if entry in self._waiters:
                self._waiters.remove(entry)

    def close(self) -> None:
        """Close every member and end every wait on the group."""
        if self._closed:
            return
        self._closed = True
        waiters, self._waiters = self._waiters, []
        for _, future in waiters:
            if not future.done():
                future.set_exception(SubscriptionClosedError("the group closed"))
        for member in self._members:
            member.close()

    def __enter__(self) -> "HealthCheckGroup":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    async def _member_changed(self, _: HealthCheckSubscription) -> None:
        if self._closed:
            return
        status = self.status
        self._resolve(status)
        if self._seen is not None and self._seen is status:
            return
        self._seen = status
        if self._on_change is not None:
            await call_back(self._on_change, status, self._reason(), subject="the dependency group")

    def _resolve(self, status: HealthCheckStatus) -> None:
        pending = []
        for entry in self._waiters:
            wanted, future = entry
            if future.done():
                continue
            if status in wanted:
                future.set_result(status)
            else:
                pending.append(entry)
        self._waiters = pending

    def _reason(self) -> str:
        if not self._members:
            return EVERYTHING_HEALTHY
        driver = max(self._members, key=lambda member: STATUS_ORDER[member.status])
        if driver.status is HealthCheckStatus.HEALTHY:
            return EVERYTHING_HEALTHY
        return f"{driver.check.name} {driver.status.lower()}"
