import logging
from logging.config import dictConfig
from flask import has_request_context, request

# pylint: disable=line-too-long
LOG_FORMAT_REQUEST = "[%(levelcolor)s%(levelname)s%(colorreset)s] %(grey)s<%(remote_addr)s - %(url)s - %(endpoint)s>%(colorreset)s - %(module)s::%(funcName)s - %(message)s"


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
        if has_request_context():
            record.url = request.url
            record.remote_addr = request.remote_addr
            record.endpoint = request.endpoint
        else:
            record.url = ''
            record.remote_addr = ''
            record.endpoint = ''
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
            'werkzeug': {
                'level': log_level,
                'handlers': ['main']
            },
            'uwsgi': {
                'level': log_level,
                'handlers': ['main']
            },
            '__main__': {
                'level': log_level,
                'handlers': ['main']
            },
        }
    })
