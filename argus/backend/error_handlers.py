import base64
from hashlib import sha256
import logging
import os
from threading import Lock
from traceback import format_exception
from fastapi import Request
from starlette.responses import JSONResponse, RedirectResponse

from argus.backend.db import ScyllaCluster
from argus.backend.rendering import flash as asgi_flash, url_for as asgi_url_for
from argus.backend.util.encoders import APIResponse

LOGGER = logging.getLogger(__name__)


class APIException(Exception):
    pass


class DataValidationError(APIException):
    pass


class UIRedirect(Exception):
    """Raised by the FastAPI UI auth dependencies: redirect to *endpoint*,
    optionally flashing a message first — the counterpart of the
    flash-and-redirect branches in the Flask login_required decorator."""

    def __init__(self, endpoint: str, flash_message: tuple[str, str] | None = None, **values):
        self.endpoint = endpoint
        self.flash_message = flash_message
        self.values = values
        super().__init__(endpoint)


def ui_redirect_handler(asgi_request: Request, exc: UIRedirect) -> RedirectResponse:
    if exc.flash_message:
        category, message = exc.flash_message
        asgi_flash(asgi_request, message, category=category)
    return RedirectResponse(
        asgi_url_for(asgi_request, exc.endpoint, **exc.values), status_code=302)


def redirecting_exception_handler(endpoint: str):
    """FastAPI counterpart of handle_profile_exception/handle_view_not_found:
    flash the exception message and redirect to *endpoint*.

    Flask registered these handlers on the UI blueprints only, while the API
    blueprints kept the JSON contract — mirror that split by path: API routes
    get the api_exception_handler response instead of a redirect."""

    async def handler(asgi_request: Request, exc: Exception):
        if asgi_request.url.path.startswith(("/api/", "/admin/api/")):
            return await api_exception_handler(asgi_request, exc)
        asgi_flash(asgi_request, " ".join(str(arg) for arg in exc.args), category="error")
        return RedirectResponse(asgi_url_for(asgi_request, endpoint), status_code=302)

    return handler


class AuthorizationError(Exception):
    """Raised by the FastAPI auth dependencies; rendered by
    authorization_error_handler with the same shape and status code the
    Flask login_required decorator responds with."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def authorization_error_handler(_: Request, exc: AuthorizationError) -> JSONResponse:
    return JSONResponse({"status": "error", "message": exc.message}, status_code=403)


async def api_exception_handler(asgi_request: Request, exception: Exception) -> APIResponse:
    """FastAPI counterpart of handle_api_exception below: same logging split
    and the exact {"status": "error", "response": {...}} / HTTP 200 contract."""
    trace_id = base64.encodebytes(sha256(os.urandom(64)).digest()).decode(encoding="utf-8").strip()
    endpoint = f"{asgi_request.method} {asgi_request.url.path}"
    try:
        body = (await asgi_request.body()).decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        body = "<unavailable>"

    if issubclass(exception.__class__, APIException):
        LOGGER.info("[TraceId: %s] Endpoint %s responded with error %s: %s", trace_id,
                    endpoint, exception.__class__.__name__, str(exception))
        LOGGER.info("[TraceId: %s] Headers\n%s", trace_id, dict(asgi_request.headers))
        LOGGER.info("[TraceId: %s] Request Data Start\n%s\nRequest Data End", trace_id, body)
    else:
        LOGGER.error("[TraceId: %s] Exception in %s\n%s", trace_id,
                     endpoint, "".join(format_exception(exception)))
        LOGGER.error("[TraceId: %s] Headers\n%s", trace_id, dict(asgi_request.headers))
        LOGGER.error("[TraceId: %s] Request Data Start\n%s\nRequest Data End", trace_id, body)

    return APIResponse(
        {
            "status": "error",
            "response": {
                "trace_id": trace_id,
                "exception": exception.__class__.__name__,
                "message": str(exception),
                "arguments": exception.args,
            },
        },
        status_code=200,
    )


class DBErrorHandler():
    DB_ERROR_COUNTER = 0
    DB_ERROR_THRESHOLD = 10
    RESTART_LOCK = Lock()

    @classmethod
    def handle_db_errors(cls, exception: Exception):
        with cls.RESTART_LOCK:
            cls.DB_ERROR_COUNTER += 1
            LOGGER.error("Received error from db cluster.", exc_info=True)
            if cls.DB_ERROR_COUNTER > cls.DB_ERROR_THRESHOLD:
                LOGGER.warning("Reconnecting the cluster as we've exceeded cassandra error counter...")
                ScyllaCluster.get().reconnect()
                cls.DB_ERROR_COUNTER = 0
                return {
                    "status": "success",
                    "response": f"Cluster seems down. Reconnect successful. Please attempt the request again."
                }

            return {
                "status": "error",
                "response": f"Cluster seems down. Attempting reconnect in {cls.DB_ERROR_THRESHOLD - cls.DB_ERROR_COUNTER} tries."
            }


async def db_error_handler(_: Request, exception: Exception) -> JSONResponse:
    return JSONResponse(DBErrorHandler.handle_db_errors(exception))
