import logging
from contextvars import ContextVar
from logging.config import dictConfig

LOG_FORMAT_REQUEST = "[%(levelcolor)s%(levelname)s%(colorreset)s] %(grey)s<%(remote_addr)s - %(url)s - %(endpoint)s>%(colorreset)s - %(module)s::%(funcName)s - %(message)s"

# The live ASGI scope of the request being handled, set by
# RequestLogContextMiddleware — the ASGI counterpart of Flask's request
# context. Stored as the scope dict so route/endpoint (assigned during
# routing, after the middleware ran) resolve lazily at format time; anyio
# copies the context into worker threads, so sync endpoint code logs with
# the same request attached.
REQUEST_SCOPE: ContextVar[dict | None] = ContextVar("argus_request_scope", default=None)


class RequestLogContextMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        token = REQUEST_SCOPE.set(scope)
        try:
            await self.app(scope, receive, send)
        finally:
            REQUEST_SCOPE.reset(token)


class ArgusRequestLogFormatter(logging.Formatter):
    yellow = "\x1b[33;20m"
    red = "\x1b[31;20m"
    blue = "\x1b[34;20m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    grey = "\x1b[38;2;200;200;200m"
    color_map = {
        logging.DEBUG: grey,
        logging.INFO: blue,
        logging.WARNING: yellow,
        logging.ERROR: red,
        logging.CRITICAL: bold_red
    }

    def format(self, record: logging.LogRecord) -> str:
        record.grey = self.grey
        record.colorreset = self.reset
        record.levelcolor = self.color_map.get(record.levelno, self.grey)
        scope = REQUEST_SCOPE.get()
        if scope is not None:
            query = scope.get("query_string", b"").decode("latin-1")
            record.url = scope.get("path", "") + (f"?{query}" if query else "")
            client = scope.get("client")
            record.remote_addr = client[0] if client else ""
            record.endpoint = getattr(scope.get("route"), "name", "") or ""
        else:
            record.url = ""
            record.remote_addr = ""
            record.endpoint = ""
        return super().format(record)


def setup_application_logging(log_level=logging.INFO):
    dictConfig({
        'version': 1,
        'formatters': {
            'request': {
                'class': f"{__name__}.{ArgusRequestLogFormatter.__name__}",
                'format': LOG_FORMAT_REQUEST,
            }
        },
        'handlers': {
            'main': {
                'class': 'logging.StreamHandler',
                'stream': 'ext://sys.stderr',
                'formatter': 'request'
            }
        },
        'loggers': {
            'cassandra': {
                'level': log_level,
                'handlers': ['main']
            },
            'argus': {
                'level': log_level,
                'handlers': ['main']
            },
            'argus_backend': {
                'level': log_level,
                'handlers': ['main']
            },
            'uvicorn': {
                'level': log_level,
                'handlers': ['main']
            },
            'gunicorn': {
                'level': log_level,
                'handlers': ['main']
            },
            '__main__': {
                'level': log_level,
                'handlers': ['main']
            },
            'argusAI': {
                'level': log_level,
                'handlers': ['main']
            },
        }
    })
