"""Gunicorn configuration replacing uwsgi.ini.

uwsgi.ini mapping:
- socket + umask         -> bind + umask
- processes = 4          -> workers = 4 (uvicorn worker: event loop +
-                            threadpool replaces `threads = 100`)
- max-requests = 65535   -> max_requests (+ jitter so workers don't recycle
-                            in lockstep; also covers max-worker-lifetime)
- worker-reload-mercy    -> graceful_timeout
- touch-chain-reload     -> send SIGHUP to the master for a rolling reload
- env PROMETHEUS_...     -> raw_env + child_exit hook for multiproc cleanup
"""

import os
from prometheus_client import multiprocess

bind = "unix:/var/lib/argus/argus.sock"
umask = 0o007
workers = 4
worker_class = "uvicorn.workers.UvicornWorker"

max_requests = 65535
max_requests_jitter = 4096
graceful_timeout = 60
timeout = 120

accesslog = None
errorlog = "/var/log/argus/argus.log"

raw_env = [
    f"PROMETHEUS_MULTIPROC_DIR={os.environ.get('PROMETHEUS_MULTIPROC_DIR', '/tmp/promdb-argus-metrics')}",
]


def child_exit(server, worker):
    multiprocess.mark_process_dead(worker.pid)
