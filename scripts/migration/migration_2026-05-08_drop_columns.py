import logging

from argus.backend.db import ScyllaCluster
from argus.backend.plugins.sct.testrun import SCTEvent, SCTTestRun
from argus.backend.util.logsetup import setup_application_logging


setup_application_logging(log_level=logging.INFO)
LOGGER = logging.getLogger(__name__)
DB = ScyllaCluster.get()

COLUMNS_TO_DROP = ["allocated_resources", "nemesis_data", "events"]


def existing_columns(keyspace: str, table: str) -> set[str]:
    """The columns the table carries right now."""
    rows = DB.session.execute(
        "SELECT column_name FROM system_schema.columns WHERE keyspace_name = %s AND table_name = %s",
        (keyspace, table),
        execution_profile="read_fast",
    )
    return {row["column_name"] for row in rows}


def events_backfilled() -> bool:
    """True once the event backfill has written at least one row."""
    row = DB.session.execute(
        f"SELECT run_id FROM {SCTEvent.table_name()} LIMIT 1",
        execution_profile="read_fast",
    ).one()
    return row is not None


def migrate():
    keyspace = DB.config["SCYLLA_KEYSPACE_NAME"]
    table = SCTTestRun.table_name()

    targets = [column for column in COLUMNS_TO_DROP if column in existing_columns(keyspace, table)]
    if not targets:
        LOGGER.warning("Nothing to do: %s.%s carries none of %s", keyspace, table, COLUMNS_TO_DROP)
        return

    if "events" in targets and not events_backfilled():
        raise SystemExit(
            f"Refusing to drop 'events': {SCTEvent.table_name()} is empty. Run migration_2026-05-08.py first."
        )

    LOGGER.warning("Starting migration: dropping columns %s from %s.%s...", targets, keyspace, table)
    for column in targets:
        query = f"ALTER TABLE {keyspace}.{table} DROP {column}"
        LOGGER.info("Executing: %s", query)
        DB.session.execute(query)
        LOGGER.info("Dropped column %s", column)

    LOGGER.warning("Migration complete. Dropped columns %s from %s.%s", targets, keyspace, table)


if __name__ == "__main__":
    migrate()
