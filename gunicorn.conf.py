"""Gunicorn configuration.

Launch: gunicorn -c gunicorn.conf.py 'argus_backend:create_app()'
Rolling reload: send SIGHUP to the master.
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
