import inspect
import time
from collections.abc import Callable
from typing import Any

from qatools_health.check import HealthCheck
from qatools_health.result import HealthCheckResult


class StalenessHealthCheck(HealthCheck):
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
        value = self.getter()
        if inspect.isawaitable(value):
            value = await value
        if value is None:
            return HealthCheckResult(self.failure_status, "no timestamp recorded yet")
        age = self.clock() - float(value)
        if age > self.fail_after:
            return HealthCheckResult(self.failure_status, f"last update {age:.0f}s ago, over {self.fail_after:g}s")
        if age > self.warn_after:
            return HealthCheckResult.degraded(f"last update {age:.0f}s ago, over {self.warn_after:g}s")
        return HealthCheckResult.healthy(f"last update {age:.0f}s ago")
