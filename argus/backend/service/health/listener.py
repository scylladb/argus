"""The listening socket of the health process."""

import asyncio
import socket

BIND_WAIT_SECONDS = 30.0
BIND_RETRY_SECONDS = 0.2


async def bind_listener(
    host: str, port: int, shutdown: asyncio.Event, wait: float = BIND_WAIT_SECONDS
) -> socket.socket | None:
    """Bind the health port, and wait while another process still holds it.

    A SIGHUP starts the new health process before the old one has let the
    port go. The new one retries the bind until the old one exits, and gives
    up after the wait.
    """
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    deadline = asyncio.get_running_loop().time() + wait
    while True:
        listener = socket.socket(family, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            listener.bind((host, port))
            listener.listen()
        except OSError:
            listener.close()
            if asyncio.get_running_loop().time() >= deadline:
                raise
            try:
                await asyncio.wait_for(shutdown.wait(), timeout=BIND_RETRY_SECONDS)
            except TimeoutError:
                continue
            return None
        return listener
