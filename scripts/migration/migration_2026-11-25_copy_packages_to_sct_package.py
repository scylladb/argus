"""Copy the package lists from ``sct_test_run.packages`` into ``sct_package``.

``sct_package`` holds one row per run and package name (ARGUS-8). Every entry
of every run's list goes into it with a plain upsert, in unlogged batches of up
to 64 KB. When a list holds one name more than once, the first entry is copied;
the stored lists repeat a name only with identical values.

A batch that fails is logged and the copy continues; the summary reports how
many rows failed, and a re-run retries them.

Run it twice per deploy: once after ``sync-models`` has created
``sct_package``, right before the release flip, and once right after the flip
for the packages the old release wrote in between. A third run is harmless.
``sct_test_run.packages`` stays in place until a later script drops it.

    uv run python scripts/migration/migration_2026-11-25_copy_packages_to_sct_package.py
    uv run python scripts/migration/migration_2026-11-25_copy_packages_to_sct_package.py --run-id <uuid>
"""

import argparse
import asyncio
import logging
from uuid import UUID

from coodie.batch import AsyncBatchQuery

from argus.backend.db import ScyllaCluster
from argus.backend.plugins.sct.testrun import SCTPackage
from argus.backend.util.logsetup import setup_application_logging


setup_application_logging(log_level=logging.INFO)
LOGGER = logging.getLogger(__name__)
DB = ScyllaCluster.get()

LEGACY_TABLE = "sct_test_run"
PACKAGE_FIELDS = ("version", "date", "revision_id", "build_id")
BATCH_BYTES = 64 * 1024
ROW_OVERHEAD_BYTES = 384
PROGRESS_EVERY = 5000


def legacy_rows(run_id: UUID | None):
    table = f"{DB.config['SCYLLA_KEYSPACE_NAME']}.{LEGACY_TABLE}"
    if run_id:
        return DB.session.execute(f"SELECT id, packages FROM {table} WHERE id = %s", (run_id,))
    return DB.session.execute(f"SELECT id, packages FROM {table}")


def package_rows(run_id: UUID, packages) -> list[SCTPackage]:
    rows = {}
    for package in packages:
        if package.name and package.name not in rows:
            rows[package.name] = SCTPackage.model_construct(
                run_id=run_id, name=package.name, **{field: getattr(package, field) for field in PACKAGE_FIELDS}
            )
    return list(rows.values())


def row_bytes(package: SCTPackage) -> int:
    """The size Scylla charges a row against its batch thresholds: the values plus the mutation bookkeeping."""
    values = (package.name, *(getattr(package, field) for field in PACKAGE_FIELDS))
    return ROW_OVERHEAD_BYTES + sum(len(value) for value in values if value is not None)


class PackageBatch:
    """Package rows, written as unlogged batches of up to ``BATCH_BYTES``."""

    def __init__(self, counts: dict[str, int]):
        self.counts = counts
        self.batch = AsyncBatchQuery(logged=False)
        self.size = 0
        self.rows = 0

    async def add(self, package: SCTPackage) -> None:
        size = row_bytes(package)
        if self.rows and self.size + size > BATCH_BYTES:
            await self.flush()
        await package.save(batch=self.batch)
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
            LOGGER.exception("Failed to write a batch of %s package rows, continuing", self.rows)
            self.counts["failed"] += self.rows
            self.batch = AsyncBatchQuery(logged=False)
        self.size = 0
        self.rows = 0


async def copy_rows(run_id: UUID | None = None) -> dict[str, int]:
    counts = {"runs": 0, "upserted": 0, "batches": 0, "failed": 0}
    batch = PackageBatch(counts)
    for index, row in enumerate(legacy_rows(run_id), start=1):
        if row["packages"]:
            counts["runs"] += 1
            for package in package_rows(row["id"], row["packages"]):
                await batch.add(package)
        if index % PROGRESS_EVERY == 0:
            LOGGER.info("Processed %s runs...", index)
    await batch.flush()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", type=UUID, default=None, help="copy the packages of one run instead of every run")
    args = parser.parse_args()

    counts = asyncio.run(copy_rows(args.run_id))
    LOGGER.info(
        "Done. %(upserted)s package rows of %(runs)s runs written in %(batches)s batches, %(failed)s failed.",
        counts,
    )
    if counts["failed"]:
        LOGGER.warning("Re-run the script to retry the %s failed rows.", counts["failed"])


if __name__ == "__main__":
    main()
