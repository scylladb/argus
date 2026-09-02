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

raw_env = [
    f"PROMETHEUS_MULTIPROC_DIR={os.environ.get('PROMETHEUS_MULTIPROC_DIR', '/tmp/promdb-argus-metrics')}",
]


def child_exit(server, worker):
    multiprocess.mark_process_dead(worker.pid)
