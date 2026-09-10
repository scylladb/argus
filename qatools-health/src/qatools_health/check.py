"""The base class every health check extends, and the decorator over a function."""

import inspect
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping, Sequence, Set
from typing import Any

from qatools_health.status import Severity

POLICY_KEYWORDS = frozenset({"name", "severity", "interval", "timeout", "stale_after_intervals"})


def freeze(value: Any) -> Any:
    """Turn a constructor argument into a hashable stand-in for it.

    A mapping becomes a sorted tuple of pairs. A set becomes a frozenset. Any
    other sequence becomes a tuple. A value that no rule reaches falls back to
    its type name and its identity, so it only ever matches itself.
    """
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
    """One dependency the service needs, and the policy that probes it.

    A subclass sets the name and the policy as class attributes, and implements
    perform_check. A constructor keyword overrides the policy for one instance.
    The runner reads identity to find two registrations of one dependency, so
    the policy keywords stay out of it.
    """

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
        """Return what makes this the dependency it is.

        Two instances with one identity share one probe loop and one metric series.
        The class and the arguments that select the dependency form the identity.
        Override this when an argument does not select a dependency.
        """
        return (type(self), *self._construction)

    @abstractmethod
    async def perform_check(self) -> Any:
        """Probe the dependency once.

        Return a result, a status, a boolean, or None. Raise to report a
        failure. The runner applies the timeout and records what comes back.
        """

    async def aclose(self) -> None:
        """Release what the check holds. The runner calls this when the check retires."""
        return None

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.name} interval={self.interval:g} severity={self.severity}>"


class CallableHealthCheck(HealthCheck):
    """A check over one async function, built by the healthcheck decorator."""

    def __init__(self, fn: Callable[[], Any], **kwargs: Any) -> None:
        if not inspect.iscoroutinefunction(fn):
            raise TypeError(f"{getattr(fn, '__name__', fn)!r} is not an async function")
        if kwargs.get("name") is None:
            kwargs["name"] = getattr(fn, "__name__", None)
        super().__init__(**kwargs)
        self.fn = fn

    async def perform_check(self) -> Any:
        """Await the wrapped function and return what it gives back."""
        return await self.fn()


def healthcheck(fn: Callable[[], Any] | None = None, **kwargs: Any) -> Any:
    """Turn an async function into a check.

    The decorator works bare or with policy keywords. A bare use takes the
    function name as the check name.
    """
    if fn is not None:
        return CallableHealthCheck(fn, **kwargs)

    def decorate(target: Callable[[], Any]) -> CallableHealthCheck:
        return CallableHealthCheck(target, **kwargs)

    return decorate
