from datetime import datetime
import logging
from json.encoder import JSONEncoder
from uuid import UUID

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
