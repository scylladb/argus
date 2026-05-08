import logging

from argus.backend.db import ScyllaCluster
from argus.backend.plugins.sct.testrun import SCTTestRun
from argus.backend.util.logsetup import setup_application_logging


setup_application_logging(log_level=logging.INFO)
LOGGER = logging.getLogger(__name__)
DB = ScyllaCluster.get()

COLUMNS_TO_DROP = ["allocated_resources", "nemesis_data", "events"]


def migrate():
    table_name = SCTTestRun.table_name()
    LOGGER.warning("Starting migration: dropping columns %s from %s...", COLUMNS_TO_DROP, table_name)

    for column in COLUMNS_TO_DROP:
        query = f"ALTER TABLE {table_name} DROP {column}"
        LOGGER.info("Executing: %s", query)
        DB.session.execute(query)
        LOGGER.info("Dropped column %s", column)

    LOGGER.warning("Migration complete. Dropped columns %s from %s", COLUMNS_TO_DROP, table_name)


if __name__ == "__main__":
    migrate()
