import inspect
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from qatools_health.status import HealthCheckStatus


class HealthCheck(ABC):
    name: str
    critical: bool = False
    failure_status: HealthCheckStatus = HealthCheckStatus.UNHEALTHY
    interval: float = 300.0
    timeout: float = 10.0
    stale_after_intervals: float = 3.0

    def __init__(
        self,
        *,
        name: str | None = None,
        critical: bool | None = None,
        failure_status: HealthCheckStatus | None = None,
        interval: float | None = None,
        timeout: float | None = None,
        stale_after_intervals: float | None = None,
    ) -> None:
        if name is not None:
            self.name = name
        if critical is not None:
            self.critical = critical
        if failure_status is not None:
            self.failure_status = failure_status
        if interval is not None:
            self.interval = float(interval)
        if timeout is not None:
            self.timeout = float(timeout)
        if stale_after_intervals is not None:
            self.stale_after_intervals = float(stale_after_intervals)

        if not getattr(self, "name", ""):
            raise ValueError(f"{type(self).__name__} has no name, pass name= or set it on the class")
        if self.interval <= 0:
            raise ValueError(f"{self.name}: interval must be positive")
        if self.timeout <= 0:
            raise ValueError(f"{self.name}: timeout must be positive")
        if self.stale_after_intervals <= 0:
            raise ValueError(f"{self.name}: stale_after_intervals must be positive")

    @abstractmethod
    async def perform_check(self) -> Any: ...

    async def aclose(self) -> None:
        return None

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.name} interval={self.interval:g} critical={self.critical}>"


class CallableHealthCheck(HealthCheck):
    def __init__(self, fn: Callable[[], Any], **kwargs: Any) -> None:
        if not inspect.iscoroutinefunction(fn):
            raise TypeError(f"{getattr(fn, '__name__', fn)!r} is not an async function")
        if kwargs.get("name") is None:
            kwargs["name"] = getattr(fn, "__name__", None)
        super().__init__(**kwargs)
        self.fn = fn

    async def perform_check(self) -> Any:
        return await self.fn()


def healthcheck(fn: Callable[[], Any] | None = None, **kwargs: Any) -> Any:
    if fn is not None:
        return CallableHealthCheck(fn, **kwargs)

    def decorate(target: Callable[[], Any]) -> CallableHealthCheck:
        return CallableHealthCheck(target, **kwargs)

    return decorate
