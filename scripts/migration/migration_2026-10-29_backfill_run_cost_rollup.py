"""Backfill the ARGUS-218 cost rollup, ``run_cost_by_month_v1``, from the runs that exist.

Writes one row per run for:

- every run that holds a ``run_cost_v1`` partition, whatever its plugin;
- every SCT run, so a run that reported no cost is counted as "no data" rather
  than left invisible.

Every write rebuilds the whole row, so re-running is safe. A run that cannot be
read is logged and the scan continues; the summary reports how many failed, and
a second run retries them. A cost partition whose run exists in no plugin is
counted as missing.

Run it after ``sync-models`` has created the table, and before deploying
anything that reads the rollup.

    uv run python scripts/migration/migration_2026-10-29_backfill_run_cost_rollup.py
    uv run python scripts/migration/migration_2026-10-29_backfill_run_cost_rollup.py --run-id <uuid>
"""

import argparse
import asyncio
import logging
from uuid import UUID

from argus.backend.db import ScyllaCluster
from argus.backend.models.web import ArgusTest
from argus.backend.plugins.sct.testrun import SCTTestRun
from argus.backend.service.cost_rollup_service import CostRollupService
from argus.backend.service.run_cost_service import RunCostService
from argus.backend.util.common import gather_limited
from argus.backend.util.logsetup import setup_application_logging


setup_application_logging(log_level=logging.INFO)
LOGGER = logging.getLogger(__name__)
DB = ScyllaCluster.get()

PROGRESS_EVERY = 250
LIST_ATTEMPTS = 3
REFRESH_CONCURRENCY = 20


def list_cost_run_ids() -> set[UUID]:
    for attempt in range(1, LIST_ATTEMPTS + 1):
        try:
            return {row["run_id"] for row in DB.session.execute("SELECT DISTINCT run_id FROM run_cost_v1")}
        except Exception:
            LOGGER.exception("Listing the cost partitions failed on attempt %s of %s", attempt, LIST_ATTEMPTS)
    raise RuntimeError("Could not list the cost partitions to backfill; re-run the script")


async def list_sct_run_ids() -> set[UUID]:
    tests = [
        test
        for test in await ArgusTest.find().only("id", "build_system_id", "plugin_name").all()
        if test.plugin_name == SCTTestRun._plugin_name
    ]
    LOGGER.info("Listing the SCT runs of %s tests...", len(tests))
    per_test = await gather_limited(
        SCTTestRun.find(build_id=test.build_system_id).only("id").values_list("id").all() for test in tests
    )
    return {run_id for rows in per_test for (run_id,) in rows}


async def refresh_sct_run(run_id: UUID) -> bool:
    run = await SCTTestRun.find(id=run_id).only(*SCTTestRun.cost_rollup_columns()).first()
    if run is None:
        return False
    await CostRollupService().refresh(run)
    return True


async def refresh_one(run_id: UUID, sct: bool, counts: dict[str, int]) -> None:
    try:
        written = await refresh_sct_run(run_id) if sct else await RunCostService().refresh_rollup(run_id) is not None
        counts["written" if written else "missing"] += 1
    except Exception:
        LOGGER.exception("Failed to roll up run %s, continuing", run_id)
        counts["failed"] += 1
    counts["runs"] += 1
    if counts["runs"] % PROGRESS_EVERY == 0:
        LOGGER.info("Processed %s runs...", counts["runs"])


async def backfill(run_id: UUID | None) -> dict[str, int]:
    counts = {"runs": 0, "written": 0, "missing": 0, "failed": 0}
    if run_id:
        await refresh_one(run_id, sct=False, counts=counts)
        return counts

    cost_ids = list_cost_run_ids()
    sct_ids = await list_sct_run_ids()
    LOGGER.info("Backfilling %s runs with cost and %s SCT runs without one...", len(cost_ids), len(sct_ids - cost_ids))
    await gather_limited(
        (refresh_one(current, sct=current in sct_ids, counts=counts) for current in cost_ids | sct_ids),
        limit=REFRESH_CONCURRENCY,
    )
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", type=UUID, default=None, help="roll up one run instead of every run")
    args = parser.parse_args()

    counts = asyncio.run(backfill(args.run_id))
    LOGGER.info("Done. %(runs)s runs, %(written)s written, %(missing)s missing, %(failed)s failed.", counts)
    if counts["failed"]:
        LOGGER.warning("Re-run the script to retry the %s failed runs.", counts["failed"])


if __name__ == "__main__":
    main()
