import asyncio
import logging
from collections.abc import Coroutine

LOGGER = logging.getLogger(__name__)
_RUNNING: set[asyncio.Task] = set()


def _finished(task: asyncio.Task) -> None:
    _RUNNING.discard(task)
    if not task.cancelled() and task.exception() is not None:
        LOGGER.error("Chat task %s failed", task.get_name(), exc_info=task.exception())


def spawn(coro: Coroutine, *, name: str) -> asyncio.Task:
    """Run work that outlives the request which started it."""
    task = asyncio.create_task(coro, name=name)
    _RUNNING.add(task)
    task.add_done_callback(_finished)
    return task


async def drain() -> None:
    while _RUNNING:
        await asyncio.gather(*list(_RUNNING), return_exceptions=True)


async def shutdown() -> None:
    running = list(_RUNNING)
    for task in running:
        task.cancel()
    await asyncio.gather(*running, return_exceptions=True)
