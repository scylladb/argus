import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from argus.backend.models.replay_build import RESERVATION_GRACE, ReplayBuildNumber


async def test_reserve_takes_a_free_number(argus_db):
    build_id = f"local-runs/jdoe/{uuid.uuid4()}"

    assert await ReplayBuildNumber.reserve(build_id, 1, uuid.uuid4())


async def test_reserve_refuses_a_taken_number(argus_db):
    build_id = f"local-runs/jdoe/{uuid.uuid4()}"
    first, second = uuid.uuid4(), uuid.uuid4()

    assert await ReplayBuildNumber.reserve(build_id, 1, first)
    assert not await ReplayBuildNumber.reserve(build_id, 1, second)
    stored = await ReplayBuildNumber.get(build_id=build_id, build_number=1)
    assert stored.run_id == first


async def test_concurrent_reservations_of_one_number_have_one_winner(argus_db):
    build_id = f"local-runs/jdoe/{uuid.uuid4()}"

    results = await asyncio.gather(*(ReplayBuildNumber.reserve(build_id, 1, uuid.uuid4()) for _ in range(8)))

    assert results.count(True) == 1


async def test_take_over_reuses_a_reservation_past_its_grace_period(argus_db):
    build_id = f"local-runs/jdoe/{uuid.uuid4()}"
    failed, retry = uuid.uuid4(), uuid.uuid4()
    await ReplayBuildNumber(build_id=build_id, build_number=1, run_id=failed,
                            reserved_at=datetime.now(UTC) - RESERVATION_GRACE - timedelta(minutes=1)).save()

    assert await ReplayBuildNumber.take_over(build_id, 1, retry)
    stored = await ReplayBuildNumber.get(build_id=build_id, build_number=1)
    assert stored.run_id == retry


async def test_take_over_leaves_a_recent_reservation(argus_db):
    build_id = f"local-runs/jdoe/{uuid.uuid4()}"
    in_flight = uuid.uuid4()
    assert await ReplayBuildNumber.reserve(build_id, 1, in_flight)

    assert not await ReplayBuildNumber.take_over(build_id, 1, uuid.uuid4())
    stored = await ReplayBuildNumber.get(build_id=build_id, build_number=1)
    assert stored.run_id == in_flight


async def test_concurrent_take_overs_have_one_winner(argus_db):
    build_id = f"local-runs/jdoe/{uuid.uuid4()}"
    await ReplayBuildNumber(build_id=build_id, build_number=1, run_id=uuid.uuid4(),
                            reserved_at=datetime.now(UTC) - RESERVATION_GRACE - timedelta(minutes=1)).save()

    results = await asyncio.gather(*(ReplayBuildNumber.take_over(build_id, 1, uuid.uuid4()) for _ in range(8)))

    assert results.count(True) == 1
