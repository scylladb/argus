import logging
from collections import namedtuple

from cassandra.cluster import Session

from argus.db.testrun import TestRun
from argus.backend.db import ScyllaCluster

logging.basicConfig()
LOGGER = logging.getLogger()
LOGGER.setLevel(logging.DEBUG)


db = ScyllaCluster.get()

session: Session = db.session
OLD_TABLE_NAME = "test_runs_v7"
stmt = db.prepare(f"INSERT INTO {TestRun.table_name()} JSON ?")

rows: list[dict] = list(session.execute(f"SELECT * FROM {OLD_TABLE_NAME}").all())
total_rows = len(rows)
MigratedRow = namedtuple("MigratedRow", [*rows[0].keys(), "scylla_version"])

for idx, row in enumerate(rows):
    LOGGER.info("[%s/%s] Migrating %s to the new table...", idx + 1, total_rows, row["id"])
    try:
        scylla_package = next(p for p in row["packages"] if p.name == "scylla-server")
        version = scylla_package.version.replace("~", ".")
    except TypeError:
        version = None
    except StopIteration:
        version = None
    migrated_row = MigratedRow(**row, scylla_version=version)
    tr = TestRun.from_db_row(migrated_row)
    tr.save()
