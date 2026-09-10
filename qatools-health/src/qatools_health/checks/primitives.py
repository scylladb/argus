"""The checks that probe a resource by shape: an HTTP endpoint, a port, a binary."""

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
    """Probe one HTTP endpoint and grade the answer.

    A status outside expect is unhealthy. A response slower than
    latency_budget is degraded. The check builds its own client when it gets
    none, and closes only a client it built. Subclass it to probe one named
    service, and override perform_check to read the body.

    The resolved URL, the headers and `credential` name the dependency, so two
    checks over one URL with different tokens each run their own loop and report
    their own series. Give each of them a name, because the runner refuses to
    publish two dependencies under one name. A credential that travels in `auth`
    rather than in a header must also be passed as `credential`, because two
    `auth` objects that carry one password still compare unequal.
    """

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
        credential: Sequence[object] | None = None,
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
        self._auth = auth
        self.credential = tuple(credential) if credential is not None else ()
        self._client = client
        self._owns_client = client is None

    def build_client(self) -> httpx.AsyncClient:
        """Build the client this check owns. Override to change the transport."""
        return httpx.AsyncClient(timeout=self.timeout, follow_redirects=True)

    def client(self) -> httpx.AsyncClient:
        """Return the client, building one on first use when none was given."""
        if self._client is None:
            self._client = self.build_client()
        return self._client

    async def request(self, url: str, *, method: str | None = None, **kwargs: Any) -> httpx.Response:
        """Send one request with the headers and the credentials of this check."""
        options: dict[str, Any] = {"headers": self.headers, "auth": self._auth}
        options.update(kwargs)
        return await self.client().request(method or self.method, url, **options)

    async def perform_check(self) -> Any:
        """Send the request, then grade the status code and the latency."""
        started = time.monotonic()
        response = await self.request(self.url)
        elapsed = time.monotonic() - started
        if response.status_code not in self.expect:
            return HealthCheckResult.unhealthy(f"{self.url} answered {response.status_code}")
        if self.latency_budget is not None and elapsed > self.latency_budget:
            return HealthCheckResult.degraded(f"{elapsed:.2f}s over the budget of {self.latency_budget:g}s")
        return HealthCheckResult.healthy(f"{response.status_code} in {elapsed:.2f}s")

    async def aclose(self) -> None:
        """Close the client, but only when this check built it."""
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None


class TcpHealthCheck(HealthCheck):
    """Open a TCP connection to one host and port, then close it.

    Use this for a dependency that speaks no HTTP, such as a tunnel or a broker.
    """

    name = "tcp"

    def __init__(self, host: str, port: int, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.host = host
        self.port = port

    async def perform_check(self) -> Any:
        """Open the connection, then close it, and time how long that took."""
        started = time.monotonic()
        _, writer = await asyncio.open_connection(self.host, self.port)
        try:
            elapsed = time.monotonic() - started
        finally:
            writer.close()
            await writer.wait_closed()
        return HealthCheckResult.healthy(f"{self.host}:{self.port} accepted a connection in {elapsed:.2f}s")


class BinaryHealthCheck(HealthCheck):
    """Resolve one executable on PATH and read the version it reports.

    The check proves that the tool is installed and runs. It proves nothing
    about credentials, which belong to the API check of the same service.
    """

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
        """Resolve the binary on PATH, then read the version it reports."""
        path = shutil.which(self.binary)
        if path is None:
            return HealthCheckResult.unhealthy(f"{self.binary} is not on PATH")
        code, output = await run_command(path, *self.version_args)
        if code != 0:
            return HealthCheckResult.unhealthy(f"{self.binary} {' '.join(self.version_args)} exited {code}")
        return HealthCheckResult.healthy(f"{self.binary} {first_line(output) or 'answered'}")


async def run_command(*argv: str) -> tuple[int, str]:
    """Run one command and return its exit code and its merged output."""
    process = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await process.communicate()
    return process.returncode or 0, stdout.decode(errors="replace")


def first_line(text: str) -> str:
    """Return the first line that holds something, or an empty string."""
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
