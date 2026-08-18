from collections.abc import Mapping
from datetime import datetime
import json
import logging
from json.encoder import JSONEncoder
from typing import Any
from uuid import UUID

from flask.json.provider import DefaultJSONProvider
from pydantic import BaseModel
from starlette.responses import JSONResponse
from cassandra.util import OrderedMapSerializedKey


LOGGER = logging.getLogger(__name__)


class ArgusJSONEncoder(JSONEncoder):
    def default(self, o):
        match o:
            case UUID():
                return str(o)
            case BaseModel():
                return o.model_dump()
            case datetime():
                return o.strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-4] + "Z"  # Include milliseconds, trim to 3 decimal places
            case bytes():
                return o.decode("utf-8", errors="replace")
            case _:
                return super().default(o)


class ArgusJSONProvider(DefaultJSONProvider):

    @staticmethod
    def process_nested_dicts(o: dict):
        for k, v in o.items():
            if isinstance(v, Mapping):
                o[k] = {str(key): val for key, val in v.items()}
        return o

    @classmethod
    def default(cls, o):
        match o:
            case UUID():
                return str(o)
            case OrderedMapSerializedKey():
                return {str(k): v for k, v in o.items()}
            case BaseModel():
                o = {str(k): v for k, v in o.model_dump().items()}
                o = cls.process_nested_dicts(o)
                return o
            case dict():
                return {str(k): v for k, v in o.items()}
            case datetime():
                return o.strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-4] + "Z"  # Include milliseconds, trim to 3 decimal places
            case bytes():
                return o.decode("utf-8", errors="replace")
            case _:
                return super().default(o)


class ArgusJSONResponse(JSONResponse):
    """FastAPI/starlette response class sharing the Flask app's encoder semantics."""

    def render(self, content: Any) -> bytes:
        return json.dumps(
            content,
            default=ArgusJSONProvider.default,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
