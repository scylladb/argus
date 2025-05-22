import logging

from cassandra.util import datetime_from_uuid1
from cassandra.query import ConsistencyLevel

from argus.backend.db import ScyllaCluster
from argus.backend.models.pytest import PytestResultTable, PytestResultTableOld, PytestUserField
from cassandra.cqlengine.query import BatchQuery
from argus.backend.models.web import ArgusTest
from argus.backend.util.common import chunk
from argus.backend.util.logsetup import setup_application_logging


setup_application_logging(log_level=logging.INFO)
LOGGER = logging.getLogger(__name__)
DB = ScyllaCluster.get()


def migrate():
    LOGGER.warning("Fetching old data...")
    rows: list[PytestResultTableOld] = (
        PytestResultTableOld.consistency(ConsistencyLevel.ONE).filter().fetch_size(5000).limit(None).all()
    )
    placeholder_test = ArgusTest.get(build_system_id="scylla-staging/artsiom_mishuta/dtest-release")
    LOGGER.warning("Migrating results...")

    for batch in chunk(rows, 100):
        print("Batch", end="")
        user_fields_to_write: list[PytestUserField] = []
        with BatchQuery() as b:
            for row in batch:
                old = dict(row)
                uf = old.pop("user_fields", {})
                ts = datetime_from_uuid1(old.pop("id"))
                new = PytestResultTable(**old)
                new.id = ts
                for key, value in uf.items():
                    f = PytestUserField()
                    f.name = new.name
                    f.id = new.id
                    f.field_name = key
                    f.field_value = value
                    if key == "failure_message" and not new.message:
                        new.message = value
                    user_fields_to_write.append(f)
                if not new.test_id:
                    new.test_id = placeholder_test.id
                    new.release_id = placeholder_test.release_id
                print(".", end="")
                new.batch(b).save()
        LOGGER.warning("Migrating user fields... Total to migrate: %s", len(user_fields_to_write))
        for uf_batch in chunk(user_fields_to_write, 100):
            print("Batch", end="")
            with BatchQuery() as b:
                for uf in uf_batch:
                    uf.batch(b).save()
                    print(".", end="")

    LOGGER.warning("Results migrated.")


if __name__ == "__main__":
    migrate()
