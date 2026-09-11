import asyncio
from typing import Any

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

    def identity(self) -> tuple[object, ...]:
        return (type(self), self.name)

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


class PairedCheck(HealthCheck):
    async def perform_check(self) -> Any:
        return True


async def settle(check: ScriptedCheck, calls: int = 1, timeout: float = 2.0) -> None:
    async with asyncio.timeout(timeout):
        while check.calls < calls:
            await asyncio.sleep(0)


async def spin(times: int = 12) -> None:
    for _ in range(times):
        await asyncio.sleep(0)
