"""Add the cost reporting fields to the SCT cloud instance UDT (ARGUS-205).

``CloudInstanceDetails`` grows ``price_per_hour``, ``cost`` and ``is_spot`` so SCT can
report what a resource costs. coodie's ``sync_type`` only issues ``CREATE TYPE IF NOT
EXISTS``, so an existing type is never widened by ``sync-models`` - this migration does
it with ``ALTER TYPE ... ADD``.

The type name deliberately stays ``cloudinstancedetails_v3``. Bumping it to ``_v4`` would
leave every column already declared as ``cloudinstancedetails_v3``
(``sct_resource.instance_info``, ``sct_test_run.sct_runner_host``,
``sct_test_run.allocated_resources`` and the nested ``cloudresource_v3.instance_info``)
pointing at the old type, and Scylla cannot retype a column in place - that would mean new
columns plus a full data rewrite. ``ALTER TYPE ... ADD`` is non-destructive and leaves
existing rows readable with the new fields as null.

The run-level ``sct_test_run.estimated_cost`` column needs no migration: ``sync_table``
already emits ``ALTER TABLE ... ADD`` for new model fields.

Safe to re-run - each ``ALTER TYPE`` is guarded by a check against the live schema.
"""

import logging

from argus.backend.db import ScyllaCluster
from argus.backend.plugins.sct.udt import CloudInstanceDetails
from argus.backend.util.logsetup import setup_application_logging


setup_application_logging(log_level=logging.INFO)
LOGGER = logging.getLogger(__name__)
DB = ScyllaCluster.get()

NEW_FIELDS = {
    "price_per_hour": "double",
    "cost": "double",
    "is_spot": "boolean",
}


def migrate():
    keyspace = DB.config["SCYLLA_KEYSPACE_NAME"]
    type_name = CloudInstanceDetails.type_name()

    rows = DB.session.execute(
        "SELECT field_names FROM system_schema.types WHERE keyspace_name = %s AND type_name = %s",
        (keyspace, type_name),
    )
    row = rows.one()
    if row is None:
        LOGGER.info(
            "Type %s.%s does not exist yet - run sync-models first, it will be created "
            "with the new fields already in place.",
            keyspace,
            type_name,
        )
        return

    existing = set(row["field_names"])
    for field, cql_type in NEW_FIELDS.items():
        if field in existing:
            LOGGER.info("Field %s already present on %s.%s - skipping.", field, keyspace, type_name)
            continue
        LOGGER.info("Adding field %s %s to %s.%s...", field, cql_type, keyspace, type_name)
        DB.session.execute(f"ALTER TYPE {keyspace}.{type_name} ADD {field} {cql_type}")

    LOGGER.info("Cost fields added. Run sync-models to pick up sct_test_run.estimated_cost.")


if __name__ == "__main__":
    migrate()
