"""The checks over state the service holds itself."""

import inspect
import time
from collections.abc import Callable
from typing import Any

from qatools_health.check import HealthCheck
from qatools_health.result import HealthCheckResult


class StalenessHealthCheck(HealthCheck):
    """Grade the age of a timestamp the service keeps.

    The getter returns a Unix time, or None before the service has one. An age
    over warn_after degrades. An age over fail_after fails. Use this to watch a
    poll loop or a cache that must keep moving.
    """

    interval = 60.0

    def __init__(
        self,
        getter: Callable[[], Any],
        warn_after: float,
        fail_after: float,
        *,
        clock: Callable[[], float] = time.time,
        **kwargs: Any,
    ) -> None:
        if warn_after > fail_after:
            raise ValueError("warn_after must not be greater than fail_after")
        super().__init__(**kwargs)
        self.getter = getter
        self.warn_after = float(warn_after)
        self.fail_after = float(fail_after)
        self.clock = clock

    async def perform_check(self) -> Any:
        """Read the timestamp and grade how old it is."""
        value = self.getter()
        if inspect.isawaitable(value):
            value = await value
        if value is None:
            return HealthCheckResult.unhealthy("no timestamp recorded yet")
        age = self.clock() - float(value)
        if age > self.fail_after:
            return HealthCheckResult.unhealthy(f"last update {age:.0f}s ago, over {self.fail_after:g}s")
        if age > self.warn_after:
            return HealthCheckResult.degraded(f"last update {age:.0f}s ago, over {self.warn_after:g}s")
        return HealthCheckResult.healthy(f"last update {age:.0f}s ago")
