import asyncio

import pytest

from argus.backend.util.common import gather_limited


async def _sleep_then(delay: float, value: int) -> int:
    await asyncio.sleep(delay)
    return value


async def test_gather_limited_preserves_order_when_tasks_finish_out_of_order():
    delays = [0.03, 0.001, 0.02, 0.0, 0.01]

    results = await gather_limited(_sleep_then(delay, index) for index, delay in enumerate(delays))

    assert results == list(range(len(delays)))


async def test_gather_limited_never_runs_more_than_limit_at_once():
    limit = 3
    in_flight = 0
    peak = 0

    async def tracked(index: int) -> int:
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.005)
        in_flight -= 1
        return index

    results = await gather_limited((tracked(index) for index in range(20)), limit=limit)

    assert results == list(range(20))
    assert peak == limit


async def test_gather_limited_propagates_the_first_exception():
    async def fail_after(delay: float) -> None:
        await asyncio.sleep(delay)
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        await gather_limited([_sleep_then(0.02, 1), fail_after(0.001), _sleep_then(0.03, 2)], limit=2)
