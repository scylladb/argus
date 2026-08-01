"""Label callbacks for the Prometheus counters registered in ``argus_backend``.

They live here rather than next to ``start_server()`` so a test can import them
without opening a Scylla connection. Every function reads the live request and
returns a label value, so each one must return a bounded set of strings: an
unbounded label value is a new time series per request.
"""

import re

from flask import request

# The client caps this too, but the header is client-controlled and a label
# value that long is a memory problem in Prometheus, not a display problem.
MAX_BUILD_ID_LEN = 256

_BUILD_NUMBER_SUFFIX = re.compile(r"#\d+$")


def categorize_user_agent(ua: str) -> str:  # noqa: PLR0911
    if not ua:
        return "unknown"
    if "argus-client-ssh-tunnel" in ua:
        return "argus-client-tunnel"
    if ua.startswith(("python-requests", "python-urllib")):
        return "argus-client"
    if ua.startswith("Go-http-client"):
        return "argus-cli-go"
    if "Mozilla" in ua:
        return "browser"
    if "curl" in ua:
        return "curl"
    return "other"


def ssh_tunnel() -> str:
    return "yes" if request.headers.get("X-SSH-Tunnel-Origin") else "no"


def build_id() -> str:
    value = request.headers.get("X-Argus-Build-Id", "").strip()
    if not value or len(value) > MAX_BUILD_ID_LEN:
        return "unknown"
    return value


def job_name() -> str:
    """The Jenkins job path with the build number removed.

    ``http_request_tunnel_build_total`` mints a series per build and grows
    without bound. This label is bounded by the number of jobs, which is what
    makes per-job tunnel adoption cheap enough to keep on a dashboard.
    """
    return _BUILD_NUMBER_SUFFIX.sub("", build_id())
