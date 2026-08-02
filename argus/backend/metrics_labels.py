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
# A release line, not a git branch: the first Jenkins folder is `scylla-master`,
# `scylla-2026.3`, `manager-master`. One value per release line keeps this label
# small enough to group a whole dashboard by.
_BRANCH_SEGMENT = re.compile(r"^[\w.\-]{1,64}$")
# PEP 440 covers what setuptools-scm builds: 0.16.1, 0.16.1.dev3+g1a2b3c4.
_CLIENT_VERSION = re.compile(r"^\d{1,4}(\.\d{1,5}){0,3}([.\-+][\w.\-+]{1,32})?$")


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


def branch() -> str:
    """The release line a job belongs to: the first segment of the job path.

    SCT and dtest pin their own copy of this client per release line, so the
    branch is what decides whether a job can tunnel at all. Grouping by it turns
    "adoption is low" into "these release lines still run a client without
    tunnel support".
    """
    segment = job_name().split("/", 1)[0]
    if not _BRANCH_SEGMENT.match(segment):
        return "unknown"
    return segment


def client_version() -> str:
    """The argus-alm version behind the request.

    Tunnel support starts at 0.16.0, so a job that reports an older version, or
    that reports none at all, cannot tunnel no matter how the proxy behaves.
    Telling those two cases apart is the difference between "backport the
    client" and "debug the tunnel".
    """
    value = request.headers.get("X-Argus-Client-Version", "").strip()
    if not _CLIENT_VERSION.match(value):
        return "unknown"
    return value
