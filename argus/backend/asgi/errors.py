"""Exception handler replicating error_handlers.handle_api_exception.

Same contract as the Flask blueprints' catch-all: APIExceptions log at INFO,
everything else at ERROR with a traceback; the response body keeps the exact
``{"status": "error", "response": {...}}`` shape and the 200 status code the
frontend expects.
"""
import base64
import logging
import os
from hashlib import sha256
from traceback import format_exception

from fastapi import Request

from argus.backend.error_handlers import APIException
from argus.backend.asgi.responses import ArgusJSONResponse

LOGGER = logging.getLogger(__name__)


async def api_exception_handler(request: Request, exception: Exception) -> ArgusJSONResponse:
    trace_id = base64.encodebytes(sha256(os.urandom(64)).digest()).decode(encoding="utf-8").strip()
    endpoint = f"{request.method} {request.url.path}"
    try:
        body = (await request.body()).decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        body = "<unavailable>"

    if issubclass(exception.__class__, APIException):
        LOGGER.info("[TraceId: %s] Endpoint %s responded with error %s: %s", trace_id,
                    endpoint, exception.__class__.__name__, str(exception))
        LOGGER.info("[TraceId: %s] Headers\n%s", trace_id, dict(request.headers))
        LOGGER.info("[TraceId: %s] Request Data Start\n%s\nRequest Data End", trace_id, body)
    else:
        LOGGER.error("[TraceId: %s] Exception in %s\n%s", trace_id,
                     endpoint, "".join(format_exception(exception)))
        LOGGER.error("[TraceId: %s] Headers\n%s", trace_id, dict(request.headers))
        LOGGER.error("[TraceId: %s] Request Data Start\n%s\nRequest Data End", trace_id, body)

    return ArgusJSONResponse(
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
