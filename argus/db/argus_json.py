from datetime import datetime
import json
from uuid import UUID


class ArgusJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        match obj:
            case UUID():
                return str(obj)
            case datetime():
                return obj.isoformat(sep=' ', timespec='milliseconds')
            case _:
                return json.JSONEncoder.default(self, obj)
