"""
Migration: copy nemesis_data UDT list from sct_test_run into the new sct_nemesis table.

This migration must be run AFTER `flask sync-models` has created the sct_nemesis table.

The migration:
  1. Scans all rows in sct_test_run that have a non-empty nemesis_data list.
  2. For each NemesisRunInfo UDT entry, inserts a corresponding row into sct_nemesis.
  3. Handles duplicates gracefully via ScyllaDB upserts on the same primary key
     (run_id, start_time), making the migration fully idempotent.

Usage:
    uv run scripts/migration/migration_2026-03-03.py
"""

import logging
from cassandra.query import SimpleStatement, ConsistencyLevel

from argus.backend.db import ScyllaCluster
from argus.backend.plugins.sct.testrun import SCTNemesis
from argus.backend.util.logsetup import setup_application_logging
from argus.backend.util.common import chunk


setup_application_logging(log_level=logging.INFO)
LOGGER = logging.getLogger(__name__)
DB = ScyllaCluster.get()


def get_runs_with_nemesis_data():
    """Yield (id, nemesis_data) for every sct_test_run row that has nemesis entries."""
    stmt = SimpleStatement(
        "SELECT id, nemesis_data FROM sct_test_run",
        consistency_level=ConsistencyLevel.ONE,
    )
    rows = DB.session.execute(stmt)
    for row in rows:
        if row["nemesis_data"]:
            yield row["id"], row["nemesis_data"]


def migrate():
    LOGGER.warning("Starting migration: copying nemesis_data → sct_nemesis table...")

    total_runs = 0
    total_nemeses = 0

    for run_id, nemesis_list in get_runs_with_nemesis_data():
        total_runs += 1
        LOGGER.info("Processing run_id=%s (%d nemesis entries)", run_id, len(nemesis_list))

        for batch in chunk(nemesis_list, 100):
            for nem in batch:
                try:
                    SCTNemesis(
                        run_id=run_id,
                        start_time=nem.start_time,
                        class_name=nem.class_name,
                        name=nem.name,
                        duration=nem.duration,
                        target_node=nem.target_node,
                        status=nem.status,
                        end_time=nem.end_time,
                        stack_trace=nem.stack_trace,
                    ).save()
                    total_nemeses += 1
                except Exception:  # noqa: BLE001
                    LOGGER.exception(
                        "Failed to migrate nemesis %s (start_time=%s) for run_id=%s",
                        nem.name,
                        nem.start_time,
                        run_id,
                    )

    LOGGER.warning("Migration complete!")
    LOGGER.warning("Processed %d runs, migrated %d nemesis records into sct_nemesis.", total_runs, total_nemeses)


if __name__ == "__main__":
    migrate()
