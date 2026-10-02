import os

os.environ.pop("PROMETHEUS_MULTIPROC_DIR", None)

import asyncio
import logging
import signal
import socket
import sys
import threading
from typing import Any

import uvicorn
from prometheus_client import CollectorRegistry

from argus.backend.service.health.app import build_app
from argus.backend.service.health.config import configured_address, configured_token, is_loopback
from argus.backend.service.health.listener import bind_listener
from argus.backend.service.health.logs import configure_logging
from argus.backend.service.health.runner import build_runner
from argus.backend.util.config import Config

LOGGER = logging.getLogger("argus.backend.service.health")

SHUTDOWN_DEADLINE_SECONDS = 20.0


def _stop_when_closed(loop: asyncio.AbstractEventLoop, shutdown: asyncio.Event, life_fd: int) -> None:
    def closed() -> None:
        loop.remove_reader(life_fd)
        LOGGER.info("The gunicorn master closed the health pipe, stopping the health process")
        shutdown.set()

    loop.add_reader(life_fd, closed)


async def _exit_after_deadline(shutdown: asyncio.Event) -> None:
    await shutdown.wait()
    timer = threading.Timer(SHUTDOWN_DEADLINE_SECONDS, os._exit, (1,))
    timer.daemon = True
    timer.start()


async def _serve_http(server: uvicorn.Server, listener: socket.socket, shutdown: asyncio.Event) -> None:
    stopper = asyncio.create_task(shutdown.wait())
    serving = asyncio.create_task(server.serve(sockets=[listener]))
    await asyncio.wait({stopper, serving}, return_when=asyncio.FIRST_COMPLETED)
    server.should_exit = True
    await serving
    stopper.cancel()
    shutdown.set()


async def serve(config: dict[str, Any], life_fd: int | None) -> None:
    registry = CollectorRegistry()
    runner = build_runner(config)
    runner.register_collector(registry)
    host, port = configured_address(config)
    if not is_loopback(host) and configured_token(config) is None:
        LOGGER.warning("Health serves %s:%s with no HEALTH_TOKEN, so /health and /metrics are open", host, port)
    app = build_app(runner, registry, configured_token(config))
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_config=None, access_log=False))

    shutdown = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signum, shutdown.set)
    if life_fd is not None:
        _stop_when_closed(loop, shutdown, life_fd)

    listener = await bind_listener(host, port, shutdown)
    if listener is None:
        LOGGER.info("The health process stopped before it could bind %s:%s", host, port)
        return
    LOGGER.info("Serving health on %s:%s", host, port)
    await asyncio.gather(
        runner.run(shutdown),
        _serve_http(server, listener, shutdown),
        _exit_after_deadline(shutdown),
    )


def main(argv: list[str]) -> int:
    try:
        life_fd = int(argv[1]) if len(argv) > 1 else None
        config = Config.load_yaml_config()
        configure_logging(config.get("APP_LOG_LEVEL", logging.INFO))
        asyncio.run(serve(config, life_fd))
    except Exception as exc:
        LOGGER.exception("The health process stopped on an error")
        raise SystemExit(1) from exc
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
