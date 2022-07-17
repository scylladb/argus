from functools import partial
from datetime import datetime

from argus.backend.models.web import User
from argus.backend.util.module_loaders import is_filter, export_functions


export_filters = partial(export_functions, module_name=__name__, attr="is_filter")


@is_filter("from_timestamp")
def from_timestamp_filter(timestamp: int):
    return datetime.utcfromtimestamp(timestamp)


@is_filter("safe_user")
def safe_user(user: User):
    user_dict = dict(user.items())
    del user_dict["password"]
    return user_dict
