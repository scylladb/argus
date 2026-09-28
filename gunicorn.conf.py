"""Gunicorn configuration.

Launch: gunicorn -c gunicorn.conf.py 'argus_backend:create_app()'
Rolling reload: send SIGHUP to the master.
"""

import os
import select
import subprocess
import sys

os.environ.setdefault("PROMETHEUS_MULTIPROC_DIR", "/tmp/promdb-argus-metrics")
os.makedirs(os.environ["PROMETHEUS_MULTIPROC_DIR"], exist_ok=True)

import yaml
from prometheus_client import multiprocess

from argus.backend.util.config import Config

bind = "unix:/var/lib/argus/argus.sock"
umask = 0o007
workers = 4
worker_class = "uvicorn.workers.UvicornWorker"
# Over a unix socket there is no peer address, so uvicorn's proxy-headers
# middleware never trusts X-Forwarded-For without this — request.client
# (metrics by ip, the zeus proxy) collapses to None. The only ingress is
# the local nginx, which overwrites X-Forwarded-For with the real peer.
forwarded_allow_ips = "*"

max_requests = 65535
max_requests_jitter = 4096
graceful_timeout = 60
timeout = 120

accesslog = None
errorlog = "/var/log/argus/argus.log"


def child_exit(server, worker):
    multiprocess.mark_process_dead(worker.pid)


def health_enabled() -> bool:
    """Read HEALTH_ENABLED from the file, and leave the Config cache empty.

    The workers fork from the master. A config cached in the master would
    reach every worker a SIGHUP starts, and hide an edit to argus_web.yaml.
    """
    with open(Config.locate_argus_web_config(), encoding="utf-8") as file:
        return bool((yaml.safe_load(file) or {}).get("HEALTH_ENABLED"))


HEALTH_COMMAND = [sys.executable, "-m", "argus.backend.service.health"]
DETACH = ["/bin/sh", "-c", '"$@" &', "sh"]


def when_ready(server):
    if not health_enabled():
        return
    life_read, life_write = os.pipe()
    done_read, done_write = os.pipe()
    try:
        subprocess.Popen(
            [*DETACH, *HEALTH_COMMAND, str(life_read)],
            pass_fds=(life_read, done_write),
            start_new_session=True,
        ).wait()
    except BaseException:
        os.close(life_write)
        os.close(done_read)
        raise
    finally:
        os.close(life_read)
        os.close(done_write)
    server.health_pipes = (life_write, done_read)
    server.log.info("Started the health process")


def post_fork(server, worker):
    for fd in getattr(server, "health_pipes", None) or ():
        os.close(fd)
    server.health_pipes = None


def _stop(server, timeout: float) -> None:
    pipes = getattr(server, "health_pipes", None)
    server.health_pipes = None
    if pipes is None:
        return
    life_write, done_read = pipes
    os.close(life_write)
    try:
        if timeout and not select.select([done_read], [], [], timeout)[0]:
            server.log.warning("The health process did not exit within %s seconds", timeout)
    finally:
        os.close(done_read)


def on_exit(server):
    _stop(server, server.cfg.graceful_timeout)


def on_reload(server):
    """Restart the health process on SIGHUP without making the master wait.

    gunicorn starts the new workers only after this hook returns. The old
    process sees its pipe close and stops, and the new one waits for the port.
    gunicorn stops the master on an exception from this hook, so an error in
    the optional health process is logged and the reload goes on.
    """
    try:
        _stop(server, 0)
        when_ready(server)
    except Exception:  # noqa: BLE001
        server.log.exception("Could not restart the health process")
