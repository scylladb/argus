"""JSON response class sharing the Flask app's encoder semantics."""
import json
from typing import Any

from starlette.responses import JSONResponse

from argus.backend.util.encoders import ArgusJSONProvider


class ArgusJSONResponse(JSONResponse):
    def render(self, content: Any) -> bytes:
        return json.dumps(
            content,
            default=ArgusJSONProvider.default,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
