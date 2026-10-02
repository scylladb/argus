"""The HTTP surface of the health process.

Every route reads the last results the runner holds. No request starts a
probe, so any number of requests adds no load to a dependency.
"""

import hmac

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest
from qatools_health import CheckSnapshot, HealthCheckRunner, HealthCheckStatus

from argus.backend.service.health.config import TOKEN_SCHEME

PENDING = "pending"


def status_label(status: HealthCheckStatus) -> str:
    """Return the lower-case status name the JSON answers use."""
    return str(status).lower()


def check_label(check: CheckSnapshot) -> str:
    if check.last_run_timestamp == 0:
        return PENDING
    return status_label(check.effective_status)


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


def token_guard(token: str | None):
    expected = f"{TOKEN_SCHEME} {token}".encode()

    def require_token(authorization: str = Header(default="")) -> None:
        if token is not None and not hmac.compare_digest(authorization.encode(), expected):
            raise HTTPException(status_code=401, detail="Authorization required")

    return require_token


def build_app(runner: HealthCheckRunner, registry: CollectorRegistry, token: str | None = None) -> FastAPI:
    """Serve /health, /health/ready and /metrics from the runner state."""
    app = FastAPI(title="Argus health", openapi_url=None, docs_url=None, redoc_url=None)
    guarded = [Depends(token_guard(token))]

    @app.get("/health", dependencies=guarded)
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

    @app.get("/metrics", dependencies=guarded)
    def metrics() -> Response:
        return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)

    return app
