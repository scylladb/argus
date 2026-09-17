"""Bounded-concurrency helper for the per-test fan-outs the view widgets do.

Generic results and run rows are partitioned by ``test_id``, so any widget that
aggregates across a view has to issue at least one query per test.  Every such
widget did that sequentially, which makes the endpoint's latency the *sum* of
the per-test queries instead of roughly the slowest one.

Measured on a 3-node cluster (ARGUS-213, ``dev-db/bench_result_queries.py``),
50 tests returning 12,500 rows: 0.949s sequential against 0.252s concurrent.
The gap widens with cluster size, because the per-test reads land on different
replicas and so genuinely parallelise.

The executor is module-level on purpose.  A per-request pool would let N
concurrent requests open N x max_workers database requests; one shared pool
caps the fan-out this process can generate no matter how many requests are in
flight, and avoids re-creating threads per request.  Widget endpoints are sync
(`def`, not `async def`), so they already run in Starlette's threadpool and may
block on this one safely.

The cassandra driver's Session is thread-safe, so the service objects these
tasks call into can be shared.  Do not submit work that itself calls
``map_concurrently`` -- nested submission into a bounded pool can deadlock.
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Iterable, TypeVar

T = TypeVar("T")
R = TypeVar("R")

LOGGER = logging.getLogger(__name__)

# Enough to hide per-query latency without letting one request flood the
# cluster.  Each worker holds one in-flight database request.
MAX_FANOUT_WORKERS = 16

_EXECUTOR = ThreadPoolExecutor(max_workers=MAX_FANOUT_WORKERS,
                               thread_name_prefix="argus-fanout")


def map_concurrently(fn: Callable[[T], R], items: Iterable[T]) -> list[R]:
    """Apply ``fn`` to every item concurrently, returning results in input order.

    Order is preserved so callers that concatenate the results keep producing
    the same payload they did sequentially.

    Exceptions propagate exactly as they would from a sequential loop: the
    first failing item re-raises here, on iteration.  That is deliberate -- a
    widget that silently dropped the tests whose queries failed would render a
    chart with missing data and no indication of it.
    """
    items = list(items)
    if len(items) <= 1:
        # Nothing to overlap; skip the executor round-trip entirely.
        return [fn(item) for item in items]
    return list(_EXECUTOR.map(fn, items))
