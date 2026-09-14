"""A local HTTP dependency that the examples take down and bring back."""

import asyncio

from qatools_health import Severity
from qatools_health.checks import HttpHealthCheck


class FlakyUpstream:
    """An HTTP server on 127.0.0.1 that answers 204, or 503 while it is down."""

    def __init__(self) -> None:
        self.healthy = True
        self._server: asyncio.Server | None = None

    async def start(self) -> "FlakyUpstream":
        """Listen on a free port and return the server."""
        self._server = await asyncio.start_server(self._answer, "127.0.0.1", 0)
        return self

    @property
    def host(self) -> str:
        """The address the server listens on."""
        return self._server.sockets[0].getsockname()[0]

    @property
    def port(self) -> int:
        """The port the server listens on."""
        return self._server.sockets[0].getsockname()[1]

    @property
    def url(self) -> str:
        """The base URL of the server."""
        return f"http://{self.host}:{self.port}"

    async def close(self) -> None:
        """Stop listening."""
        self._server.close()
        await self._server.wait_closed()

    async def _answer(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            await reader.readuntil(b"\r\n\r\n")
            status = b"204 No Content" if self.healthy else b"503 Service Unavailable"
            writer.write(b"HTTP/1.1 " + status + b"\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
            await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            writer.close()


class UpstreamHealthCheck(HttpHealthCheck):
    """The upstream answers its ping route.

    A dedicated check subclasses a primitive and fills in the probe and the
    policy, so a caller passes the base URL and nothing else.
    """

    name = "upstream_api"
    severity = Severity.CRITICAL
    interval = 0.25
    timeout = 2.0

    def __init__(self, base_url: str, **kwargs: object) -> None:
        super().__init__(f"{base_url}/ping", **kwargs)
