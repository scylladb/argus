from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from coodie import ClusteringKey, PrimaryKey
from coodie.aio import Document
from coodie.cql_builder import build_insert
from coodie.drivers import get_driver
from coodie.exceptions import DocumentNotFound
from pydantic import Field

from argus.backend.util.config import Config

# A replay creates its run seconds after it reserves the number. A reservation
# older than this whose number no run holds belongs to a replay that failed.
RESERVATION_GRACE = timedelta(minutes=10)

# Reservations only guard the time until the run exists. The run then holds
# the number, so a reservation can expire.
RESERVATION_TTL_SECONDS = int(timedelta(days=7).total_seconds())


class ReplayBuildNumber(Document):
    """A build number that a replay took under a build path.

    A replay reserves the number with a conditional insert before it creates
    the run, so two replays into one path never take the same number.
    """

    build_id: Annotated[str, PrimaryKey()]
    build_number: Annotated[int, ClusteringKey()]
    run_id: UUID
    reserved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "replay_build_number_v1"

    @classmethod
    async def reserve(cls, build_id: str, build_number: int, run_id: UUID) -> bool:
        """Take ``build_number`` under ``build_id`` for ``run_id``. Return False
        when another replay holds it."""
        cql, params = build_insert(
            cls.Settings.name,
            Config.load_yaml_config()["SCYLLA_KEYSPACE_NAME"],
            {"build_id": build_id, "build_number": build_number, "run_id": run_id,
             "reserved_at": datetime.now(UTC)},
            ttl=RESERVATION_TTL_SECONDS,
            if_not_exists=True,
        )
        rows = await get_driver().execute_async(cql, params)
        return not rows or bool(rows[0].get("[applied]", True))

    @classmethod
    async def take_over(cls, build_id: str, build_number: int, run_id: UUID) -> bool:
        """Take a reservation that a failed replay left: one older than
        ``RESERVATION_GRACE``. The caller checks that no run holds the number.
        Return False when the reservation is recent or another replay took it
        first."""
        try:
            held = await cls.get(build_id=build_id, build_number=build_number)
        except DocumentNotFound:
            return await cls.reserve(build_id, build_number, run_id)
        reserved_at = held.reserved_at if held.reserved_at.tzinfo else held.reserved_at.replace(tzinfo=UTC)
        if datetime.now(UTC) - reserved_at < RESERVATION_GRACE:
            return False
        result = await held.update(
            run_id=run_id, reserved_at=datetime.now(UTC), ttl=RESERVATION_TTL_SECONDS,
            if_conditions={"run_id": held.run_id},
        )
        return bool(result and result.applied)
