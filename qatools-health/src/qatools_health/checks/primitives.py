import asyncio
import shutil
import time
from collections.abc import Container, Mapping, Sequence
from typing import Any

import httpx

from qatools_health.check import CallableHealthCheck, HealthCheck
from qatools_health.result import HealthCheckResult

DEFAULT_EXPECTED_STATUS = range(200, 400)


class HttpHealthCheck(HealthCheck):
    name = "http"
    method = "GET"

    def __init__(
        self,
        url: str,
        *,
        method: str | None = None,
        expect: Container[int] = DEFAULT_EXPECTED_STATUS,
        latency_budget: float | None = None,
        headers: Mapping[str, str] | None = None,
        auth: Any = None,
        client: httpx.AsyncClient | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.url = url
        if method is not None:
            self.method = method
        self.expect = expect
        self.latency_budget = latency_budget
        self.headers = dict(headers) if headers else {}
        self.auth = auth
        self._client = client
        self._owns_client = client is None

    def build_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=self.timeout, follow_redirects=True)

    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = self.build_client()
        return self._client

    async def request(self, url: str, *, method: str | None = None, **kwargs: Any) -> httpx.Response:
        options: dict[str, Any] = {"headers": self.headers, "auth": self.auth}
        options.update(kwargs)
        return await self.client().request(method or self.method, url, **options)

    async def perform_check(self) -> Any:
        started = time.monotonic()
        response = await self.request(self.url)
        elapsed = time.monotonic() - started
        if response.status_code not in self.expect:
            return HealthCheckResult(self.failure_status, f"{self.url} answered {response.status_code}")
        if self.latency_budget is not None and elapsed > self.latency_budget:
            return HealthCheckResult.degraded(f"{elapsed:.2f}s over the budget of {self.latency_budget:g}s")
        return HealthCheckResult.healthy(f"{response.status_code} in {elapsed:.2f}s")

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None


class TcpHealthCheck(HealthCheck):
    name = "tcp"

    def __init__(self, host: str, port: int, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.host = host
        self.port = port

    async def perform_check(self) -> Any:
        started = time.monotonic()
        _, writer = await asyncio.open_connection(self.host, self.port)
        try:
            elapsed = time.monotonic() - started
        finally:
            writer.close()
            await writer.wait_closed()
        return HealthCheckResult.healthy(f"{self.host}:{self.port} accepted a connection in {elapsed:.2f}s")


class BinaryHealthCheck(HealthCheck):
    name = "binary"
    binary = ""
    version_args: Sequence[str] = ("--version",)
    interval = 900.0

    def __init__(
        self,
        binary: str | None = None,
        *,
        version_args: Sequence[str] | None = None,
        **kwargs: Any,
    ) -> None:
        if binary is not None:
            self.binary = binary
        if version_args is not None:
            self.version_args = tuple(version_args)
        if not self.binary:
            raise ValueError(f"{type(self).__name__} has no binary to look for")
        kwargs.setdefault("name", self.binary)
        super().__init__(**kwargs)

    async def perform_check(self) -> Any:
        path = shutil.which(self.binary)
        if path is None:
            return HealthCheckResult(self.failure_status, f"{self.binary} is not on PATH")
        code, output = await run_command(path, *self.version_args)
        if code != 0:
            return HealthCheckResult(self.failure_status, f"{self.binary} {' '.join(self.version_args)} exited {code}")
        return HealthCheckResult.healthy(f"{self.binary} {first_line(output) or 'answered'}")


async def run_command(*argv: str) -> tuple[int, str]:
    process = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await process.communicate()
    return process.returncode or 0, stdout.decode(errors="replace")


def first_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


__all__ = [
    "BinaryHealthCheck",
    "CallableHealthCheck",
    "HttpHealthCheck",
    "TcpHealthCheck",
    "first_line",
    "run_command",
]
