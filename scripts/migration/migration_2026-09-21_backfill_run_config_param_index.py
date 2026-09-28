"""Backfill the ARGUS-157 config parameter indexes from ``run_configuration``.

Fills three tables for every config already submitted:

- ``run_config_param_by_run_v1`` — every parameter of one run, in one partition.
- ``run_config_param_value_index_v1`` — the distinct values of one parameter.
- ``run_config_param_name_v1`` — the catalogue of parameter names.

It lists the run ids in ``run_configuration``, then replays
``ClientService.parse_config_values`` over each run's configs. A run whose config
predates the parser gets its parameters for the first time.

Every write is an upsert, so re-running is safe. A run that cannot be read is
logged and the scan continues; the summary reports how many failed, and a second
run retries them. A config whose content is not JSON counts as skipped.

Run it after ``sync-models`` has created the three tables, and before deploying
anything that reads them.

    uv run python scripts/migration/migration_2026-09-21_backfill_run_config_param_index.py
    uv run python scripts/migration/migration_2026-09-21_backfill_run_config_param_index.py --run-id <uuid>
"""

import argparse
import asyncio
import json
import logging
from uuid import UUID

from argus.backend.db import ScyllaCluster
from argus.backend.models.run_config import RunConfiguration
from argus.backend.service.client_service import ClientService
from argus.backend.util.logsetup import setup_application_logging


setup_application_logging(log_level=logging.INFO)
LOGGER = logging.getLogger(__name__)
DB = ScyllaCluster.get()

PROGRESS_EVERY = 250
LIST_ATTEMPTS = 3


def list_run_ids(run_id: UUID | None = None) -> list[UUID]:
    if run_id:
        return [run_id]
    for attempt in range(1, LIST_ATTEMPTS + 1):
        try:
            return [row["run_id"] for row in DB.session.execute("SELECT DISTINCT run_id FROM run_configuration")]
        except Exception:
            LOGGER.exception("Listing the runs failed on attempt %s of %s", attempt, LIST_ATTEMPTS)
    raise RuntimeError("Could not list the runs to backfill; re-run the script")


async def configs_for(run_id: UUID) -> list[RunConfiguration]:
    return await RunConfiguration.find(run_id=run_id).all()


def is_json_object(content: str) -> bool:
    try:
        return isinstance(json.loads(content), dict)
    except json.JSONDecodeError:
        return False


async def backfill(run_id: UUID | None = None) -> dict[str, int]:
    counts = {"runs": 0, "parsed": 0, "skipped": 0, "failed": 0}
    run_ids = list_run_ids(run_id)
    LOGGER.info("Backfilling %s runs...", len(run_ids))

    for index, current in enumerate(run_ids, start=1):
        try:
            for row in await configs_for(current):
                content = row.content
                if not content or not is_json_object(content):
                    counts["skipped"] += 1
                    continue
                await ClientService.parse_config_values(row.name, content, str(row.run_id))
                counts["parsed"] += 1
            counts["runs"] += 1
        except Exception:
            # One unreadable run must not end the scan; the writes are upserts, so
            # re-running the script picks it up again.
            LOGGER.exception("Failed to backfill run %s, continuing", current)
            counts["failed"] += 1
        if index % PROGRESS_EVERY == 0:
            LOGGER.info("Processed %s of %s runs...", index, len(run_ids))
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", type=UUID, default=None, help="replay one run instead of every run")
    args = parser.parse_args()

    counts = asyncio.run(backfill(args.run_id))
    LOGGER.info("Done. %(runs)s runs, %(parsed)s configs replayed, %(skipped)s skipped, %(failed)s failed.", counts)
    if counts["failed"]:
        LOGGER.warning("Re-run the script to retry the %s failed runs.", counts["failed"])


if __name__ == "__main__":
    main()
