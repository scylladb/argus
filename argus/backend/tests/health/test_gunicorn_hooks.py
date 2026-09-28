import os
import runpy
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from argus.backend.util.config import Config

CONF_PATH = Path(__file__).parents[4] / "gunicorn.conf.py"


@pytest.fixture
def hooks(monkeypatch, tmp_path):
    monkeypatch.setenv("PROMETHEUS_MULTIPROC_DIR", str(tmp_path / "prometheus"))
    return runpy.run_path(str(CONF_PATH))


@pytest.fixture
def server():
    state = SimpleNamespace(cfg=SimpleNamespace(graceful_timeout=5), log=MagicMock(), health_pipes=None)
    yield state
    for fd in state.health_pipes or ():
        os.close(fd)


def is_open(fd: int) -> bool:
    try:
        os.fstat(fd)
    except OSError:
        return False
    return True


class FakeHealthProcess:
    def __init__(self, server):
        self.life_read, life_write = os.pipe()
        done_read, self.done_write = os.pipe()
        server.health_pipes = (life_write, done_read)

    def pipe_closed(self) -> bool:
        return os.read(self.life_read, 1) == b""

    def exit(self) -> None:
        os.close(self.done_write)
        self.done_write = None

    def close(self) -> None:
        os.close(self.life_read)
        if self.done_write is not None:
            os.close(self.done_write)


@pytest.fixture
def health_process(server):
    process = FakeHealthProcess(server)
    yield process
    process.close()


@pytest.fixture
def config_file(tmp_path):
    def write(text: str) -> Path:
        path = tmp_path / "argus_web.yaml"
        path.write_text(text, encoding="utf-8")
        return path

    return write


@pytest.mark.parametrize("text", ["", "HEALTH_ENABLED: false\n", "APP_LOG_LEVEL: INFO\n"])
def test_when_ready_starts_nothing_while_health_is_off(hooks, server, config_file, text):
    with (
        patch.object(Config, "locate_argus_web_config", return_value=config_file(text)),
        patch.object(subprocess, "Popen") as popen,
    ):
        hooks["when_ready"](server)
    popen.assert_not_called()


def test_when_ready_starts_the_health_module_detached(hooks, server, config_file):
    with (
        patch.object(Config, "locate_argus_web_config", return_value=config_file("HEALTH_ENABLED: true\n")),
        patch.object(subprocess, "Popen") as popen,
    ):
        hooks["when_ready"](server)
    (command,), options = popen.call_args
    life_read, done_write = options["pass_fds"]
    assert command == ["/bin/sh", "-c", '"$@" &', "sh", sys.executable, "-m", "argus.backend.service.health", str(life_read)]
    assert options["start_new_session"] is True
    popen.return_value.wait.assert_called_once_with()
    assert not is_open(life_read)
    assert not is_open(done_write)
    assert all(is_open(fd) for fd in server.health_pipes)


def test_when_ready_leaves_the_config_cache_to_the_workers(hooks, server, config_file):
    with (
        patch.object(Config, "locate_argus_web_config", return_value=config_file("HEALTH_ENABLED: true\n")),
        patch.object(Config, "load_yaml_config") as load,
        patch.object(subprocess, "Popen"),
    ):
        hooks["when_ready"](server)
    load.assert_not_called()


def test_health_process_is_not_a_child_and_stops_with_the_master(hooks, server, config_file, tmp_path, monkeypatch):
    report = tmp_path / "parent"
    script = (
        "import os, sys, pathlib;"
        f"pathlib.Path({str(report)!r}).write_text(str(os.getppid()));"
        "os.read(int(sys.argv[1]), 1)"
    )
    monkeypatch.setitem(hooks["when_ready"].__globals__, "HEALTH_COMMAND", [sys.executable, "-c", script])
    with patch.object(Config, "locate_argus_web_config", return_value=config_file("HEALTH_ENABLED: true\n")):
        hooks["when_ready"](server)
    deadline = time.monotonic() + 10
    while not report.exists() or not report.read_text():
        assert time.monotonic() < deadline
        time.sleep(0.05)
    assert int(report.read_text()) != os.getpid()
    hooks["on_exit"](server)
    server.log.warning.assert_not_called()
    assert server.health_pipes is None


def test_on_exit_closes_the_pipe_and_waits_for_the_exit(hooks, server, health_process):
    health_process.exit()
    hooks["on_exit"](server)
    assert health_process.pipe_closed()
    server.log.warning.assert_not_called()
    assert server.health_pipes is None


def test_on_exit_warns_about_a_process_past_the_graceful_timeout(hooks, server, health_process):
    server.cfg.graceful_timeout = 0.05
    hooks["on_exit"](server)
    assert health_process.pipe_closed()
    server.log.warning.assert_called_once()


def test_on_exit_without_a_process_does_nothing(hooks, server):
    hooks["on_exit"](server)


def test_post_fork_closes_the_pipes_in_the_worker(hooks, server, health_process):
    pipes = server.health_pipes
    hooks["post_fork"](server, MagicMock())
    assert not any(is_open(fd) for fd in pipes)
    assert server.health_pipes is None
    assert health_process.pipe_closed()


def test_on_reload_starts_the_new_process_without_waiting(hooks, server, config_file, health_process):
    with (
        patch.object(Config, "locate_argus_web_config", return_value=config_file("HEALTH_ENABLED: true\n")),
        patch.object(subprocess, "Popen") as popen,
    ):
        hooks["on_reload"](server)
    assert health_process.pipe_closed()
    server.log.warning.assert_not_called()
    popen.assert_called_once()
    assert all(is_open(fd) for fd in server.health_pipes)


def test_on_reload_stops_the_health_process_when_it_is_turned_off(hooks, server, config_file, health_process):
    with (
        patch.object(Config, "locate_argus_web_config", return_value=config_file("HEALTH_ENABLED: false\n")),
        patch.object(subprocess, "Popen") as popen,
    ):
        hooks["on_reload"](server)
    assert health_process.pipe_closed()
    popen.assert_not_called()
    assert server.health_pipes is None


@pytest.mark.parametrize("error", [OSError("fork failed"), AttributeError("'list' object has no attribute 'get'")])
def test_on_reload_logs_a_failed_restart_and_keeps_the_master(hooks, server, config_file, error):
    with (
        patch.object(Config, "locate_argus_web_config", return_value=config_file("HEALTH_ENABLED: true\n")),
        patch.object(subprocess, "Popen", side_effect=error),
    ):
        hooks["on_reload"](server)
    server.log.exception.assert_called_once()
    assert server.health_pipes is None
