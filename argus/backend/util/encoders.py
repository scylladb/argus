from datetime import datetime
import logging
from json.encoder import JSONEncoder
from uuid import UUID

from flask.json.provider import DefaultJSONProvider
import cassandra.cqlengine.usertype as ut
import cassandra.cqlengine.models as m


LOGGER = logging.getLogger(__name__)


class ArgusJSONEncoder(JSONEncoder):
    def default(self, o):
        match o:
            case UUID():
                return str(o)
            case ut.UserType():
                return dict(o.items())
            case m.Model():
                return dict(o.items())
            case datetime():
                return o.strftime("%Y-%m-%dT%H:%M:%SZ")
            case _:
                return super().default(o)


class ArgusJSONProvider(DefaultJSONProvider):

    @staticmethod
    def process_nested_dicts(o: dict):
        for k, v in o.items():
            if isinstance(v, dict):
                o[k] = {str(key): val for key, val in v.items()}
        return o

    @classmethod
    def default(cls, o):
        match o:
            case UUID():
                return str(o)
            case ut.UserType():
                o = {str(k): v for k, v in o.items()}
                o = cls.process_nested_dicts(o)
                return o
            case m.Model():
                o = {str(k): v for k, v in o.items()}
                o = cls.process_nested_dicts(o)
                return o
            case dict():
                return {str(k): v for k, v in o.items()}
            case datetime():
                return o.strftime("%Y-%m-%dT%H:%M:%SZ")
            case _:
                return super().default(o)
