import sys
from functools import wraps
from typing import Callable


def is_filter(filter_name: str) -> Callable:
    def outer_wrapper(func):
        func.is_filter = True
        func.filter_name = filter_name

        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        return wrapper

    return outer_wrapper


def export_functions(module_name: str, attr: str) -> list[Callable]:
    module = sys.modules[module_name]
    funcs = []

    for member in dir(module):
        export = getattr(module, member)
        applicable_export = getattr(export, attr, False)
        if applicable_export:
            funcs.append(export)

    return funcs
