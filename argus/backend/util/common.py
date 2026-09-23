import base64
from itertools import islice
import logging
import os
from typing import Callable, Iterable, TypeVar
from uuid import UUID

from coodie.sync import BatchQuery, Document
from pydantic import BeforeValidator

T = TypeVar('T')

LOGGER = logging.getLogger(__name__)

# Frontends serialize unset optional query params as bare keys (?planId=),
# which arrive as "" — treat that as absent, like Flask's request.args did.
NoneIfEmpty = BeforeValidator(lambda value: None if value == "" else value)

# Rows written pre-coodie store NULL for empty collections; coodie coerces
# those to empty containers on Document reads but not inside UDTs, where the
# cassandra driver decodes NULL fields as None.
NoneAsEmptyList = BeforeValidator(lambda value: [] if value is None else value)


def first(iterable, value, key: Callable = None, predicate: Callable = None):
    for elem in iterable:
        if predicate and predicate(elem, value):
            return elem
        elif key and key(elem) == value:
            return elem
        elif elem == value:
            return elem
    return None


def chunk(iterable: Iterable[T], slice_size=90) -> list[list[T]]:
    it = iter(iterable)
    return iter(lambda: list(islice(it, slice_size)), [])


def check_scheduled_test(test, group, testname):
    return testname in (f"{group}/{test}", test)


def strip_html_tags(text: str):
    return text.replace("<", "&lt;").replace(">", "&gt;")


def convert_str_list_to_uuid(lst: list[str]) -> list[UUID]:
    return [UUID(s) for s in lst]


def gen_pass() -> str:
    return base64.encodebytes(os.urandom(48)).decode("ascii").strip()


def get_build_number(build_job_url: str) -> int | None:
    build_number = build_job_url.rstrip("/").split("/")[-1] if build_job_url else -1
    if build_number:
        try:
            return int(build_number)
        except ValueError:
            LOGGER.error("Error parsing build number from %s: got %s as build_number", build_job_url, build_number)
    return None


def check_version(filter_string: str, version: str) -> bool:
    if not version:
        return False
    if version.startswith(filter_string):
        return True

    return False


# Scylla rejects a batch over 64 KiB by default, so flush well below that.
BATCH_MAX_BYTES = 48 * 1024
BATCH_MAX_STATEMENTS = 200


class SizedBatchQuery(BatchQuery):
    """An unlogged BatchQuery that flushes itself before it outgrows the server limit."""

    def __init__(self, max_statements: int = BATCH_MAX_STATEMENTS, max_bytes: int = BATCH_MAX_BYTES) -> None:
        super().__init__(logged=False)
        self.max_statements = max_statements
        self.max_bytes = max_bytes
        self.pending = 0
        self.pending_bytes = 0
        self.batches = 0

    def add(self, stmt: str, params: list) -> None:
        cost = len(stmt) + sum(len(str(param)) for param in params if param is not None)
        if self.pending and (self.pending >= self.max_statements or self.pending_bytes + cost > self.max_bytes):
            self.flush()
        super().add(stmt, params)
        self.pending += 1
        self.pending_bytes += cost

    def flush(self) -> None:
        if not self.pending:
            return
        self.execute()
        self.batches += 1
        self.pending = 0
        self.pending_bytes = 0


def save_in_batches(items: Iterable[T], to_documents: Callable[[T], Iterable[Document]],
                    max_statements: int = BATCH_MAX_STATEMENTS, max_bytes: int = BATCH_MAX_BYTES) -> int:
    """Save every document ``to_documents`` yields, in batches bounded by count and size.

    Returns the number of documents written.
    """
    batch = SizedBatchQuery(max_statements, max_bytes)
    saved = 0
    for item in items:
        for document in to_documents(item):
            document.save(batch=batch)
            saved += 1
    batch.flush()
    return saved
