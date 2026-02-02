import base64
from hashlib import sha256
import logging
import os
from threading import Lock
from traceback import format_exception
from flask import flash, redirect, request, url_for

from argus.backend.db import ScyllaCluster

LOGGER = logging.getLogger(__name__)


class APIException(Exception):
    pass


class DataValidationError(APIException):
    pass


class DBErrorHandler():
    DB_ERROR_COUNTER = 0
    DB_ERROR_THRESHOLD = 10
    RESTART_LOCK = Lock()

    @classmethod
    def handle_db_errors(cls, exception: Exception):
        with cls.RESTART_LOCK:
            cls.DB_ERROR_COUNTER +=1
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


def handle_api_exception(exception: Exception):
    trace_id = base64.encodebytes(sha256(os.urandom(64)).digest()).decode(encoding="utf-8").strip()
    response_code = 200
    if issubclass(exception.__class__, APIException):
        LOGGER.info("[TraceId: %s] Endpoint %s responded with error %s: %s", trace_id,
                    request.endpoint, exception.__class__.__name__, str(exception))
        LOGGER.info("[TraceId: %s] Headers\n%s", trace_id, request.headers)
        LOGGER.info("[TraceId: %s] Request Data Start\n%s\nRequest Data End", trace_id,
                    request.json if request.is_json else request.get_data(as_text=True))
    else:
        LOGGER.error("[TraceId: %s] Exception in %s\n%s", trace_id,
                     request.endpoint, "".join(format_exception(exception)))
        LOGGER.error("[TraceId: %s] Headers\n%s", trace_id, request.headers)
        LOGGER.error("[TraceId: %s] Request Data Start\n%s\nRequest Data End", trace_id,
                     request.json if request.is_json else request.get_data(as_text=True))

    return ({
        "status": "error",
        "response": {
            "trace_id": trace_id,
            "exception": exception.__class__.__name__,
            "message": str(exception),
            "arguments": exception.args
        }
    }, response_code)

def handle_profile_exception(exception: Exception):
    flash(message=" ".join(exception.args), category="error")
    return redirect(url_for("main.profile"))
