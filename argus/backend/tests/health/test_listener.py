import asyncio
import socket

import pytest

from argus.backend.service.health.listener import bind_listener


def hold_port() -> socket.socket:
    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    holder.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    holder.bind(("127.0.0.1", 0))
    holder.listen()
    return holder


async def test_bind_waits_for_the_old_process_to_release_the_port():
    holder = hold_port()
    port = holder.getsockname()[1]
    asyncio.get_running_loop().call_later(0.3, holder.close)
    listener = await bind_listener("127.0.0.1", port, wait=5)
    try:
        assert listener.getsockname()[1] == port
    finally:
        listener.close()


async def test_bind_gives_up_after_the_wait():
    holder = hold_port()
    try:
        with pytest.raises(OSError):
            await bind_listener("127.0.0.1", holder.getsockname()[1], wait=0.3)
    finally:
        holder.close()
