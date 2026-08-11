"""Drop the legacy-named vector indexes on the SCT event embedding tables.

The indexes were created by ``_sync_additional_rules`` under hand-picked
names (``error_event_index``/``critical_event_index``). With the coodie
port the models declare the index via the ``VectorIndex`` marker, which
derives ``<table>_<column>_idx`` names — running ``sync-models`` after
this migration recreates the indexes under the new names (a vector-store
rebuild of the index, not of the data).
"""

import logging

from argus.backend.db import ScyllaCluster
from argus.backend.models.argus_ai import SCTErrorEventEmbedding, SCTCriticalEventEmbedding
from argus.backend.util.logsetup import setup_application_logging


setup_application_logging(log_level=logging.INFO)
LOGGER = logging.getLogger(__name__)
DB = ScyllaCluster.get()

LEGACY_INDEXES = {
    SCTErrorEventEmbedding: "error_event_index",
    SCTCriticalEventEmbedding: "critical_event_index",
}


def migrate():
    for model, index_name in LEGACY_INDEXES.items():
        keyspace = model.Settings.keyspace
        LOGGER.info("Dropping legacy vector index %s.%s...", keyspace, index_name)
        DB.session.execute(f"DROP INDEX IF EXISTS {keyspace}.{index_name}")
    LOGGER.info("Legacy vector indexes dropped. Run sync-models to recreate them under coodie-derived names.")


if __name__ == "__main__":
    migrate()
