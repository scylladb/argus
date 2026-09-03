import asyncio
from typing import Any

import pytest

from qatools_health import HealthCheck


class FakeClock:
    def __init__(self, start: float = 1_000_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class ScriptedCheck(HealthCheck):
    name = "scripted"
    interval = 60.0
    timeout = 5.0

    def __init__(self, results: list[Any] | None = None, *, delay: float = 0.0, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.results = list(results or [])
        self.delay = delay
        self.calls = 0
        self.closed = 0
        self.started = asyncio.Event()

    async def perform_check(self) -> Any:
        self.calls += 1
        self.started.set()
        if self.delay:
            await asyncio.sleep(self.delay)
        if not self.results:
            return True
        value = self.results[0] if len(self.results) == 1 else self.results.pop(0)
        if isinstance(value, BaseException):
            raise value
        return value

    async def aclose(self) -> None:
        self.closed += 1


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()
