"""
Migration script to backfill all ERROR and CRITICAL events into sct_unprocessed_events.

This migration is needed before fully deploying the Event Similarity Processor V2.
It ensures that all existing ERROR/CRITICAL events are queued for processing.

The migration:
  1. Scans all SCT events with severity ERROR or CRITICAL
  2. Inserts them into sct_unprocessed_events table
  3. Handles duplicates gracefully (Scylla upserts on same primary key)

Usage:
  uv run scripts/migration/migration_2026-01-20.py
"""

import logging
from typing import Iterable

from cassandra.query import SimpleStatement, ConsistencyLevel
from cassandra.cqlengine.query import BatchQuery

from argus.backend.db import ScyllaCluster
from argus.backend.plugins.sct.testrun import SCTEvent, SCTUnprocessedEvent, SCTEventSeverity
from argus.backend.util.logsetup import setup_application_logging
from argus.backend.util.common import chunk


setup_application_logging(log_level=logging.INFO)
LOGGER = logging.getLogger(__name__)
DB = ScyllaCluster.get()


def get_all_run_ids() -> Iterable:
    """Get all unique run_ids from sct_event table that have ERROR or CRITICAL events."""
    # Must include all partition key columns in DISTINCT query
    stmt = SimpleStatement("SELECT DISTINCT run_id, severity FROM sct_event")
    result = DB.session.execute(stmt)

    seen_run_ids = set()
    for row in result:
        run_id = row["run_id"]
        severity = row["severity"]
        # Only yield each run_id once, and only if it has ERROR or CRITICAL events
        if severity in (SCTEventSeverity.ERROR.value, SCTEventSeverity.CRITICAL.value) and run_id not in seen_run_ids:
            seen_run_ids.add(run_id)
            yield run_id


def migrate():
    LOGGER.warning("Starting migration: backfilling unprocessed events...")

    # Get all unique run_ids
    LOGGER.info("Fetching all unique run_ids...")
    run_ids = list(get_all_run_ids())
    total_runs = len(run_ids)
    LOGGER.info("Found %d unique run_ids to process", total_runs)

    total_events_migrated = 0

    # Process each run_id, fetching both ERROR and CRITICAL events in one query
    for idx, run_id in enumerate(run_ids, 1):
        LOGGER.info("[%d/%d] Processing run_id=%s", idx, total_runs, run_id)

        # Fetch all ERROR and CRITICAL events for this run_id using IN clause
        events = list(
            SCTEvent.consistency(ConsistencyLevel.ONE)
            .filter(run_id=run_id, severity__in=[SCTEventSeverity.ERROR.value, SCTEventSeverity.CRITICAL.value])
            .all()
        )

        if not events:
            LOGGER.info("No ERROR/CRITICAL events found for run_id=%s", run_id)
            continue

        LOGGER.info("Found %d ERROR/CRITICAL events to migrate for run_id=%s", len(events), run_id)

        # Insert events into unprocessed queue in batches
        batch_count = 0
        for event_batch in chunk(events, 100):
            batch_count += 1
            with BatchQuery() as b:
                for event in event_batch:
                    unprocessed_event = SCTUnprocessedEvent()
                    unprocessed_event.run_id = event.run_id
                    unprocessed_event.severity = event.severity
                    unprocessed_event.ts = event.ts
                    unprocessed_event.batch(b).save()

            total_events_migrated += len(event_batch)
            LOGGER.debug("Batch %d completed (%d events)", batch_count, len(event_batch))

        LOGGER.info(
            "[%d/%d] Completed run_id=%s - migrated %d events",
            idx,
            total_runs,
            run_id,
            len(events),
        )

    LOGGER.warning("Migration complete!")
    LOGGER.warning("Total events migrated to unprocessed queue: %d", total_events_migrated)
    LOGGER.warning("The Event Similarity Processor V2 can now process these events.")


if __name__ == "__main__":
    migrate()
