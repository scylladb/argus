"""The HTTP surface of the health process.

Every route reads the last results the runner holds. No request starts a
probe, so any number of requests adds no load to a dependency.
"""

from fastapi import FastAPI
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest
from qatools_health import CheckSnapshot, HealthCheckRunner, HealthCheckStatus, worse_of

PENDING = "pending"


def status_label(status: HealthCheckStatus) -> str:
    """Return the lower-case status name the JSON answers use."""
    return str(status).lower()


def effective_status(check: CheckSnapshot) -> HealthCheckStatus:
    """Return the status the aggregate counts: a stale check reads at least DEGRADED."""
    return worse_of(check.status, HealthCheckStatus.DEGRADED if check.stale else HealthCheckStatus.HEALTHY)


def check_label(check: CheckSnapshot) -> str:
    if check.last_run_timestamp == 0:
        return PENDING
    return status_label(effective_status(check))


def _check_payload(check: CheckSnapshot) -> dict:
    return {
        "name": check.name,
        "severity": str(check.severity),
        "status": check_label(check),
        "message": check.message or check.error or "",
        "stale": check.stale,
        "last_run_timestamp": check.last_run_timestamp,
        "last_success_timestamp": check.last_success_timestamp,
    }


def build_app(runner: HealthCheckRunner, registry: CollectorRegistry) -> FastAPI:
    """Serve /health, /health/ready and /metrics from the runner state."""
    app = FastAPI(title="Argus health", openapi_url=None, docs_url=None, redoc_url=None)

    @app.get("/health")
    def health() -> dict:
        snapshot = runner.snapshot()
        return {
            "service": snapshot.service,
            "version": snapshot.version,
            "status": status_label(snapshot.aggregate),
            "runner_up": snapshot.runner_up,
            "checks": [_check_payload(check) for check in snapshot.checks],
        }

    @app.get("/health/ready")
    def ready() -> JSONResponse:
        status = runner.status
        code = 503 if status is HealthCheckStatus.UNHEALTHY else 200
        return JSONResponse({"status": status_label(status)}, status_code=code)

    @app.get("/metrics")
    def metrics() -> Response:
        return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)

    return app
