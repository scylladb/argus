"""
Migration: copy nemesis_data UDT list from sct_test_run into the new sct_nemesis table,
and populate the nemesis_stats static column on sct_nemesis.

This migration must be run AFTER `flask sync-models` has created the sct_nemesis table
(including the nemesis_stats static column).

The migration:
  1. Scans all rows in sct_test_run that have a non-empty nemesis_data list, using paged
     fetches so the full table is never loaded into memory at once.
  2. For each NemesisRunInfo UDT entry, inserts a corresponding row into sct_nemesis.
  3. Handles duplicates gracefully via ScyllaDB upserts on the same primary key
     (run_id, start_time), making the migration fully idempotent.
  4. After all nemesis rows for a run are written, aggregates status counts for all
     finalized statuses (succeeded, failed, skipped, terminated) and writes them to the
     nemesis_stats static column. Matches exactly what the live finalize_nemesis path
     records going forward.

Usage:
    uv run scripts/migration/migration_2026-03-03.py
"""

import logging
from collections import defaultdict

from cassandra.query import SimpleStatement, ConsistencyLevel

from argus.backend.db import ScyllaCluster
from argus.backend.plugins.sct.testrun import SCTNemesis
from argus.backend.util.logsetup import setup_application_logging


setup_application_logging(log_level=logging.INFO)
LOGGER = logging.getLogger(__name__)
DB = ScyllaCluster.get()

PAGE_SIZE = 500

# Statuses that represent a completed (finalized) nemesis run.
# Matches what finalize_nemesis records at runtime – all statuses except the
# transient "running" / "started" ones that were never finalised.
FINALIZED_STATUSES = {"succeeded", "failed", "skipped", "terminated"}


def get_runs_with_nemesis_data():
    """Yield (id, nemesis_data) for every sct_test_run row that has nemesis entries, using paging."""
    stmt = SimpleStatement(
        "SELECT id, nemesis_data FROM sct_test_run",
        consistency_level=ConsistencyLevel.ONE,
        fetch_size=PAGE_SIZE,
    )
    for row in DB.session.execute(stmt):
        if row["nemesis_data"]:
            yield row["id"], row["nemesis_data"]


def migrate():
    LOGGER.warning("Starting migration: copying nemesis_data → sct_nemesis table and populating nemesis_stats...")

    write_stats_stmt = DB.prepare(f"UPDATE {SCTNemesis.__table_name__} SET nemesis_stats = ? WHERE run_id = ?")

    total_runs = 0
    total_nemeses = 0

    for run_id, nemesis_list in get_runs_with_nemesis_data():
        total_runs += 1
        LOGGER.info("Processing run_id=%s (%d nemesis entries)", run_id, len(nemesis_list))

        status_counts: dict[str, int] = defaultdict(int)

        for nem in nemesis_list:
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
                continue

            if nem.status in FINALIZED_STATUSES:
                status_counts[nem.status] += 1

        # Write aggregated stats for this run after all its nemeses are processed.
        if status_counts:
            try:
                DB.session.execute(write_stats_stmt, (dict(status_counts), run_id))
                LOGGER.debug("Saved nemesis_stats for run_id=%s: %s", run_id, dict(status_counts))
            except Exception:  # noqa: BLE001
                LOGGER.exception("Failed to save nemesis_stats for run_id=%s", run_id)

    LOGGER.warning("Migration complete!")
    LOGGER.warning("Processed %d runs, migrated %d nemesis records into sct_nemesis.", total_runs, total_nemeses)


if __name__ == "__main__":
    migrate()
