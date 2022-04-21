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


def setup_argus_logging():
    dictConfig({
        'version': 1,
        'formatters': {
            'request': {
                'class': 'argus.backend.logsetup.ArgusRequestLogFormatter',
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
                'level': 'INFO',
                'handlers': ['main']
            },
            'argus': {
                'level': 'INFO',
                'handlers': ['main']
            },
            'argus_backend': {
                'level': 'INFO',
                'handlers': ['main']
            },
            'werkzeug': {
                'level': 'INFO',
                'handlers': ['main']
            },
            'uwsgi': {
                'level': 'INFO',
                'handlers': ['main']
            }
        }
    })
