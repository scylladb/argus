"""Add Scylla Cloud (xcloud) descriptors to the ``cloudsetupdetails`` UDT.

coodie's ``UserType.sync_type()`` only issues ``CREATE TYPE IF NOT EXISTS``, so fields added to an
existing UDT have to be applied by hand. Safe to re-run: fields already present are skipped.
"""

import logging

from argus.backend.db import ScyllaCluster
from argus.backend.plugins.sct.udt import CloudSetupDetails
from argus.backend.util.logsetup import setup_application_logging


setup_application_logging(log_level=logging.INFO)
LOGGER = logging.getLogger(__name__)
DB = ScyllaCluster.get()

FIELDS_TO_ADD = {
    "cluster_type": "text",
    "network_type": "text",
}


def migrate():
    type_name = CloudSetupDetails.type_name()
    keyspace = DB.config["SCYLLA_KEYSPACE_NAME"]
    LOGGER.warning("Starting migration: adding fields %s to type %s.%s...", list(FIELDS_TO_ADD), keyspace, type_name)

    row = DB.session.execute(
        "SELECT field_names FROM system_schema.types WHERE keyspace_name = %s AND type_name = %s",
        (keyspace, type_name),
    ).one()
    existing_fields = set(row["field_names"]) if row else set()

    for field_name, cql_type in FIELDS_TO_ADD.items():
        if field_name in existing_fields:
            LOGGER.info("Field %s already present, skipping", field_name)
            continue
        query = f"ALTER TYPE {keyspace}.{type_name} ADD {field_name} {cql_type}"
        LOGGER.info("Executing: %s", query)
        DB.session.execute(query)

    LOGGER.warning("Migration complete.")


if __name__ == "__main__":
    migrate()
