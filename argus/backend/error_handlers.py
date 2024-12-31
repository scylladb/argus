import base64
from hashlib import sha256
import logging
import os
from traceback import format_exception
from flask import request

LOGGER = logging.getLogger(__name__)


class APIException(Exception):
    pass

class DataValidationError(APIException):
    pass

def handle_api_exception(exception: Exception):
    trace_id = base64.encodebytes(sha256(os.urandom(64)).digest()).decode(encoding="utf-8").strip()
    if issubclass(exception.__class__, APIException):
        LOGGER.info("TraceId: %s", trace_id)
        LOGGER.info("Endpoint %s responded with error %s: %s", request.endpoint, exception.__class__.__name__, str(exception))
        LOGGER.info("Headers\n%s", request.headers)
        LOGGER.info("Request Data Start\n%s\nRequest Data End", request.json if request.is_json else request.get_data(as_text=True))
        LOGGER.info("TraceId: %s", trace_id)
    else:
        LOGGER.error("TraceId: %s", trace_id)
        LOGGER.error("Exception in %s\n%s", request.endpoint, "".join(format_exception(exception)))
        LOGGER.error("Headers\n%s", request.headers)
        LOGGER.error("Request Data Start\n%s\nRequest Data End", request.json if request.is_json else request.get_data(as_text=True))
        LOGGER.error("TraceId: %s", trace_id)

    return {
        "status": "error",
        "response": {
            "trace_id": trace_id,
            "exception": exception.__class__.__name__,
            "arguments": exception.args
        }
    }
