from typing import Callable
from uuid import UUID


def first(iterable, value, key: Callable = None, predicate: Callable = None):
    for elem in iterable:
        if predicate and predicate(elem, value):
            return elem
        elif key and key(elem) == value:
            return elem
        elif elem == value:
            return elem
    return None


def check_scheduled_test(test, group, testname):
    return testname == f"{group}/{test}" or testname == test


def strip_html_tags(text: str):
    return text.replace("<", "&lt;").replace(">", "&gt;")


def convert_str_list_to_uuid(lst: list[str]) -> list[UUID]:
    return [UUID(s) for s in lst]
