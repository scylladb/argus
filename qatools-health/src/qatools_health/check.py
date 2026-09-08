import inspect
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping, Sequence, Set
from typing import Any

from qatools_health.status import Severity

POLICY_KEYWORDS = frozenset({"name", "severity", "interval", "timeout", "stale_after_intervals"})


def freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return tuple(sorted((str(key), freeze(item)) for key, item in value.items()))
    if isinstance(value, str | bytes):
        return value
    try:
        hash(value)
    except TypeError:
        pass
    else:
        return value
    if isinstance(value, Set):
        return frozenset(freeze(item) for item in value)
    if isinstance(value, Sequence):
        return tuple(freeze(item) for item in value)
    return (type(value).__name__, id(value))


class HealthCheck(ABC):
    name: str
    severity: Severity = Severity.IMPORTANT
    interval: float = 300.0
    timeout: float = 10.0
    stale_after_intervals: float = 3.0

    _construction: tuple[Any, ...]

    def __new__(cls, *args: Any, **kwargs: Any) -> "HealthCheck":
        instance = super().__new__(cls)
        instance._construction = (
            freeze(args),
            tuple(sorted((key, freeze(value)) for key, value in kwargs.items() if key not in POLICY_KEYWORDS)),
        )
        return instance

    def __init__(
        self,
        *,
        name: str | None = None,
        severity: Severity | None = None,
        interval: float | None = None,
        timeout: float | None = None,
        stale_after_intervals: float | None = None,
    ) -> None:
        if name is not None:
            self.name = name
        if severity is not None:
            self.severity = Severity(severity)
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

    def identity(self) -> tuple[object, ...]:
        return (type(self), *self._construction)

    @abstractmethod
    async def perform_check(self) -> Any: ...

    async def aclose(self) -> None:
        return None

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.name} interval={self.interval:g} severity={self.severity}>"


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
