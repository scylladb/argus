import os
from http import HTTPStatus
from importlib.metadata import version
from typing import Callable

from fastapi import APIRouter, Depends
from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_fastapi_instrumentator.metrics import Info
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    REGISTRY,
    generate_latest,
    multiprocess,
)
from starlette.responses import Response

from argus.backend import metrics_labels

# The former prometheus_flask_exporter default series (export_defaults with
# NO_PREFIX): numeric status label ("200"), unlike the by_* counters below
# which keep werkzeug's response.status format ("200 OK").
REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint", "status"],
)
REQUEST_TOTAL = Counter(
    "http_request_total",
    "Total number of HTTP requests",
    ["method", "status"],
)
REQUEST_EXCEPTIONS = Counter(
    "http_request_exceptions_total",
    "Total number of HTTP requests which resulted in an exception",
    ["method", "status"],
)
EXPORTER_INFO = Gauge(
    "exporter_info",
    "Information about the Prometheus exporter",
    ["version"],
    multiprocess_mode="max",
)
EXPORTER_INFO.labels(version=version("prometheus-fastapi-instrumentator")).set(1)
REQUESTS_BY_ENDPOINT = Counter(
    "http_request_by_endpoint_total",
    "Total Requests made",
    ["endpoint", "method", "status"],
)
REQUESTS_BY_IP = Counter(
    "http_request_by_ip_total",
    "Total requests by source IP",
    ["ip", "endpoint"],
)
REQUESTS_SSH_TUNNEL = Counter(
    "http_request_ssh_tunnel_total",
    "Total requests by SSH tunnel presence",
    ["ssh_tunnel", "tunnel_established", "endpoint"],
)
# The metric that answers "which jobs are not using the tunnel". The per-build
# counter cannot: it mints a series per build, which rules out keeping the
# long ranges that adoption has to be measured over.
REQUESTS_JOB_TUNNEL = Counter(
    "http_request_job_tunnel_total",
    "Requests by Jenkins job, release line, client version and SSH tunnel state",
    ["job_name", "branch", "client_version", "ssh_tunnel"],
)
REQUESTS_BY_USER_AGENT = Counter(
    "http_request_by_user_agent_total",
    "Total requests by user agent category and client version",
    ["user_agent_category", "client_version", "endpoint"],
)
REQUESTS_TUNNEL_BUILD = Counter(
    "http_request_tunnel_build_total",
    "Requests by Jenkins build id (X-Argus-Build-Id) and SSH tunnel state",
    ["build_id", "build_url", "ssh_tunnel"],
)


def status_line(status_code: int) -> str:
    """Match werkzeug's Response.status format ("200 OK", "404 NOT FOUND")."""
    try:
        return f"{status_code} {HTTPStatus(status_code).phrase.upper()}"
    except ValueError:
        return f"{status_code} UNKNOWN"


def record_request(endpoint: str, method: str, status_code: int, remote_addr: str | None,
                   headers, duration: float | None = None) -> None:
    """Increment every request series; headers is any case-insensitive mapping."""
    endpoint = endpoint or "unknown"
    ssh_tunnel = metrics_labels.ssh_tunnel(headers)
    client_version = metrics_labels.client_version(headers)
    status = str(status_code)

    REQUEST_TOTAL.labels(method=method, status=status).inc()
    if duration is not None:
        REQUEST_DURATION.labels(method=method, endpoint=endpoint, status=status).observe(duration)
    REQUESTS_BY_ENDPOINT.labels(endpoint=endpoint, method=method, status=status_line(status_code)).inc()
    REQUESTS_BY_IP.labels(ip=remote_addr or "unknown", endpoint=endpoint).inc()
    REQUESTS_SSH_TUNNEL.labels(
        ssh_tunnel=ssh_tunnel,
        tunnel_established="yes" if headers.get("X-Tunnel-Established-At") else "no",
        endpoint=endpoint,
    ).inc()
    REQUESTS_JOB_TUNNEL.labels(
        job_name=metrics_labels.job_name(headers),
        branch=metrics_labels.branch(headers),
        client_version=client_version,
        ssh_tunnel=ssh_tunnel,
    ).inc()
    REQUESTS_BY_USER_AGENT.labels(
        user_agent_category=metrics_labels.categorize_user_agent(headers.get("User-Agent", "")),
        client_version=client_version,
        endpoint=endpoint,
    ).inc()
    REQUESTS_TUNNEL_BUILD.labels(
        build_id=metrics_labels.build_id(headers),
        build_url=headers.get("X-Argus-Build-Url") or "",
        ssh_tunnel=ssh_tunnel,
    ).inc()


def render_metrics() -> tuple[bytes, str]:
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
    else:
        registry = REGISTRY
    return generate_latest(registry), CONTENT_TYPE_LATEST


METRICS_ENDPOINT_NAME = "prometheus_metrics"


def record_exception(method: str, status_code: int = 500) -> None:
    """Count an unhandled exception, like the flask exporter's default series
    did for exceptions that escaped the views."""
    REQUEST_EXCEPTIONS.labels(method=method, status=str(status_code)).inc()


def build_metrics_router(current_user_dependency: Callable) -> APIRouter:
    """The /metrics endpoint: requires auth in production (multiproc) mode
    and is open in development, matching the original exporter setup.

    The auth dependency is injected by create_app — importing it here would
    close an import cycle (service.user imports error_handlers, which uses
    the exception counter above).
    """
    dependencies = [Depends(current_user_dependency)] if os.environ.get("PROMETHEUS_MULTIPROC_DIR") else []
    router = APIRouter()

    @router.get("/metrics", name=METRICS_ENDPOINT_NAME, dependencies=dependencies)
    def metrics_view():
        payload, content_type = render_metrics()
        return Response(payload, media_type=content_type)

    return router


def build_instrumentator() -> Instrumentator:
    """Request metrics via prometheus-fastapi-instrumentator.

    One custom instrumentation function increments the shared series above —
    no default library metrics, so the series stay exactly the ones the
    dashboards already use. /metrics itself is not recorded.

    The endpoint label uses the matched route's name; migrated routes are
    named after their Flask endpoints (e.g. "api.client_api.submit_run") to
    keep the label values, and thus the dashboards, stable.
    """
    instrumentator = Instrumentator(
        should_group_status_codes=False,
        should_ignore_untemplated=False,
        excluded_handlers=["^/metrics$"],
    )

    def argus_request_metrics(info: Info) -> None:
        scope = info.request.scope
        route = scope.get("route")
        endpoint = getattr(route, "name", None) or info.modified_handler
        client = scope.get("client")
        record_request(
            endpoint=endpoint,
            method=info.request.method,
            status_code=info.response.status_code if info.response else 500,
            remote_addr=client[0] if client else None,
            headers=info.request.headers,
            duration=info.modified_duration,
        )

    instrumentator.add(argus_request_metrics)
    return instrumentator
