import logging
from traceback import format_exception
from flask import request

LOGGER = logging.getLogger(__name__)


class APIException(Exception):
    pass


def handle_api_exception(exception: Exception):
    LOGGER.error("Exception in %s\n%s", request.endpoint, "".join(format_exception(exception)))

    return {
        "status": "error",
        "response": {
            "exception": exception.__class__.__name__,
            "arguments": exception.args
        }
    }
