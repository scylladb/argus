import threading
import time

import pytest

from argus.backend.util.concurrency import MAX_FANOUT_WORKERS, map_concurrently


def test_preserves_input_order():
    """Callers concatenate these results, so a reordered payload would be a
    silent behaviour change from the sequential loops this replaced."""
    # Reverse-proportional sleeps: finishing order is the opposite of input order.
    items = [0.03, 0.02, 0.01, 0.0]

    def slow_identity(delay: float) -> float:
        time.sleep(delay)
        return delay

    assert map_concurrently(slow_identity, items) == items


def test_actually_runs_concurrently():
    """Guards the point of the change -- a regression to sequential execution
    would still pass every other test here."""
    barrier = threading.Barrier(4, timeout=10)

    def wait_for_others(_):
        # Only returns if at least 4 tasks are in flight at once.
        barrier.wait()
        return True

    assert map_concurrently(wait_for_others, range(4)) == [True] * 4


def test_empty_and_single_item():
    assert map_concurrently(lambda x: x * 2, []) == []
    assert map_concurrently(lambda x: x * 2, [21]) == [42]


def test_accepts_any_iterable_not_just_sequences():
    assert map_concurrently(lambda x: x + 1, (n for n in range(3))) == [1, 2, 3]


def test_exception_propagates():
    """A widget that silently dropped the tests whose queries failed would
    render a chart with missing data and no indication of it."""
    def fail_on_two(value: int) -> int:
        if value == 2:
            raise ValueError("boom")
        return value

    with pytest.raises(ValueError, match="boom"):
        map_concurrently(fail_on_two, [1, 2, 3])


def test_more_items_than_workers_all_complete():
    count = MAX_FANOUT_WORKERS * 3
    assert map_concurrently(lambda x: x, range(count)) == list(range(count))
