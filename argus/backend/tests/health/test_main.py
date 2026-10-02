import asyncio
import logging
import os
from unittest.mock import MagicMock, patch

import pytest

from argus.backend.service.health import __main__ as health_main


@pytest.fixture
def config():
    with (
        patch.object(health_main.Config, "load_yaml_config", return_value={}),
        patch.object(health_main, "configure_logging"),
    ):
        yield


@pytest.mark.parametrize("error", [RuntimeError("boom"), OSError("port in use")])
def test_main_exits_with_1_on_an_error(config, error):
    with patch.object(health_main, "serve", side_effect=error), pytest.raises(SystemExit) as stopped:
        health_main.main(["health"])
    assert stopped.value.code == 1
    assert stopped.value.__cause__ is error


def test_main_exits_with_1_on_a_bad_pipe_argument(config):
    with patch.object(health_main, "serve") as serve, pytest.raises(SystemExit) as stopped:
        health_main.main(["health", "not-a-number"])
    assert stopped.value.code == 1
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


async def serve_without_a_bind(config):
    async def no_listener(host, port, shutdown):
        return None

    with (
        patch.object(health_main, "build_runner", return_value=MagicMock()),
        patch.object(health_main, "bind_listener", side_effect=no_listener),
    ):
        await health_main.serve(config, None)


@pytest.mark.parametrize(
    ("config", "warned"),
    [
        ({"HEALTH_HOST": "10.0.0.5"}, True),
        ({"HEALTH_HOST": "10.0.0.5", "HEALTH_TOKEN": "s3cret"}, False),
        ({"HEALTH_HOST": "127.0.0.1"}, False),
        ({"HEALTH_HOST": "::1"}, False),
        ({"HEALTH_HOST": "localhost"}, False),
    ],
)
async def test_an_open_listener_off_loopback_is_logged(caplog, config, warned):
    with caplog.at_level(logging.INFO, logger=health_main.LOGGER.name):
        await serve_without_a_bind(config)
    warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert bool(warnings) is warned


async def test_a_stop_before_the_bind_is_logged(caplog):
    with caplog.at_level(logging.INFO, logger=health_main.LOGGER.name):
        await serve_without_a_bind({})
    assert any("before it could bind" in record.getMessage() for record in caplog.records)
