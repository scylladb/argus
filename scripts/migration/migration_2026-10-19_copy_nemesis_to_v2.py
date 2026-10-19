"""Copy the nemesis rows from ``sct_nemesis`` into ``sct_nemesis_v2``.

``sct_nemesis`` is keyed by the run and a whole-second start time, so two
nemeses that started in one second shared a row. ``sct_nemesis_v2`` adds the
nemesis name to the key (ARGUS-150).

Every row of the old table goes into the new one:

- a ``running`` row with ``INSERT ... IF NOT EXISTS``, one statement at a time,
  so a re-run never overwrites a row the new release already finalized in v2;
- any other row with a plain upsert, in unlogged batches of up to 64 KB, so a
  status the old release wrote after an earlier pass reaches v2.

A row without a name is logged and skipped. A row or a batch that fails is
logged and the copy continues; the summary reports how many rows failed, and a
re-run retries them.

Run it twice per deploy: once after ``sync-models`` has created
``sct_nemesis_v2``, right before the release flip, and once right after the
flip for the rows the old release wrote in between. A third run is harmless.
``sct_nemesis`` stays in place; drop it by hand once v2 is verified.

    uv run python scripts/migration/migration_2026-10-19_copy_nemesis_to_v2.py
    uv run python scripts/migration/migration_2026-10-19_copy_nemesis_to_v2.py --run-id <uuid>
"""

import argparse
import asyncio
import logging
from uuid import UUID

from coodie.batch import AsyncBatchQuery

from argus.backend.db import ScyllaCluster
from argus.backend.plugins.sct.testrun import SCTNemesis
from argus.backend.util.logsetup import setup_application_logging
from argus.common.enums import NemesisStatus


setup_application_logging(log_level=logging.INFO)
LOGGER = logging.getLogger(__name__)
DB = ScyllaCluster.get()

LEGACY_TABLE = "sct_nemesis"
BATCH_BYTES = 64 * 1024
ROW_OVERHEAD_BYTES = 384
PROGRESS_EVERY = 5000


def legacy_rows(run_id: UUID | None):
    table = f"{DB.config['SCYLLA_KEYSPACE_NAME']}.{LEGACY_TABLE}"
    if run_id:
        return DB.session.execute(f"SELECT * FROM {table} WHERE run_id = %s", (run_id,))
    return DB.session.execute(f"SELECT * FROM {table}")


def row_bytes(row: dict) -> int:
    """The size Scylla charges a row against its batch thresholds: the values plus the mutation bookkeeping."""
    return ROW_OVERHEAD_BYTES + sum(len(str(value)) for value in row.values() if value is not None)


class FinishedRowBatch:
    """Finished rows, written as unlogged batches of up to ``BATCH_BYTES``."""

    def __init__(self, counts: dict[str, int]):
        self.counts = counts
        self.batch = AsyncBatchQuery(logged=False)
        self.size = 0
        self.rows = 0

    async def add(self, nemesis: SCTNemesis, size: int) -> None:
        if self.rows and self.size + size > BATCH_BYTES:
            await self.flush()
        await nemesis.save(batch=self.batch)
        self.size += size
        self.rows += 1

    async def flush(self) -> None:
        if not self.rows:
            return
        try:
            await self.batch.execute()
            self.counts["upserted"] += self.rows
            self.counts["batches"] += 1
        except Exception:
            LOGGER.exception("Failed to write a batch of %s finished rows, continuing", self.rows)
            self.counts["failed"] += self.rows
            self.batch = AsyncBatchQuery(logged=False)
        self.size = 0
        self.rows = 0


async def copy_rows(run_id: UUID | None = None) -> dict[str, int]:
    counts = {"inserted": 0, "upserted": 0, "batches": 0, "skipped": 0, "failed": 0}
    finished = FinishedRowBatch(counts)
    for index, row in enumerate(legacy_rows(run_id), start=1):
        if not row["name"]:
            LOGGER.warning("Skipping run %s start_time %s: no name.", row["run_id"], row["start_time"])
            counts["skipped"] += 1
            continue
        nemesis = SCTNemesis.model_construct(**row)
        if row["status"] == NemesisStatus.RUNNING.value:
            try:
                await nemesis.insert()
                counts["inserted"] += 1
            except Exception:
                LOGGER.exception(
                    "Failed to copy run %s nemesis %s (%s), continuing", row["run_id"], row["name"], row["start_time"]
                )
                counts["failed"] += 1
        else:
            await finished.add(nemesis, row_bytes(row))
        if index % PROGRESS_EVERY == 0:
            LOGGER.info("Processed %s rows...", index)
    await finished.flush()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", type=UUID, default=None, help="copy the nemeses of one run instead of every run")
    args = parser.parse_args()

    counts = asyncio.run(copy_rows(args.run_id))
    LOGGER.info(
        "Done. %(inserted)s running rows offered, %(upserted)s finished rows written in %(batches)s batches, "
        "%(skipped)s skipped, %(failed)s failed.",
        counts,
    )
    if counts["failed"]:
        LOGGER.warning("Re-run the script to retry the %s failed rows.", counts["failed"])


if __name__ == "__main__":
    main()
