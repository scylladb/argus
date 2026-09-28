import asyncio
import os
from unittest.mock import patch

import pytest

from argus.backend.service.health import __main__ as health_main


@pytest.fixture
def config():
    with (
        patch.object(health_main.Config, "load_yaml_config", return_value={}),
        patch.object(health_main, "configure_logging"),
    ):
        yield


@pytest.mark.parametrize("error", [RuntimeError("boom"), SystemExit(3), KeyboardInterrupt()])
def test_main_exits_with_1_on_any_error(config, error):
    with patch.object(health_main, "serve", side_effect=error):
        assert health_main.main(["health"]) == 1


def test_main_exits_with_1_on_a_bad_pipe_argument(config):
    with patch.object(health_main, "serve") as serve:
        assert health_main.main(["health", "not-a-number"]) == 1
    serve.assert_not_called()


@pytest.mark.parametrize(("argv", "life_fd"), [(["health", "7"], 7), (["health"], None)])
def test_main_passes_the_pipe_from_the_arguments(config, argv, life_fd):
    received = []

    async def record(config, fd):
        received.append(fd)

    with patch.object(health_main, "serve", side_effect=record):
        assert health_main.main(argv) == 0
    assert received == [life_fd]


async def test_a_closed_pipe_stops_the_process():
    life_read, life_write = os.pipe()
    shutdown = asyncio.Event()
    try:
        health_main._stop_when_closed(asyncio.get_running_loop(), shutdown, life_read)
        assert not shutdown.is_set()
        os.close(life_write)
        await asyncio.wait_for(shutdown.wait(), timeout=5)
    finally:
        os.close(life_read)


async def test_the_stop_arms_a_forced_exit():
    shutdown = asyncio.Event()
    shutdown.set()
    with patch.object(health_main.threading, "Timer") as timer:
        await health_main._exit_after_deadline(shutdown)
    timer.assert_called_once_with(health_main.SHUTDOWN_DEADLINE_SECONDS, os._exit, (1,))
    timer.return_value.start.assert_called_once_with()
