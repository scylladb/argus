from typing import TypeVar

T = TypeVar("T")


def is_list_homogeneous(list_to_check: list[T]) -> bool:
    first, *_ = list_to_check
    first_type = type(first)

    filtered_list = list(filter(lambda val: type(val) != first_type, list_to_check))

    return len(filtered_list) == 0
