import logging
from cassandra.cqlengine.management import sync_table

from argus.backend.db import ScyllaCluster
from argus.backend.util.logsetup import setup_application_logging
from argus.backend.plugins.sct.testrun import SCTTestRun

setup_application_logging()
LOGGER = logging.getLogger(__name__)


def up():
    db = ScyllaCluster.get()
    db.session.default_timeout = 3600
    old_table_name = "test_runs_v8"
    new_table_name = SCTTestRun.__table_name__
    sync_table(SCTTestRun)

    all_ids = [row["id"] for row in list(db.session.execute(f"SELECT id FROM {old_table_name}").all())]
    total_ids = len(all_ids)

    broken_runs = []
    for idx, run_id in enumerate(all_ids):
        LOGGER.info("[%s/%s] Migrating %s...", idx + 1, total_ids, run_id)
        SCTTestRun._table_name = old_table_name
        run: SCTTestRun = SCTTestRun.get(id=run_id)
        if not run.build_id:
            broken_runs.append(run_id)
            LOGGER.warning("Broken run: %s", run_id)
        run._is_persisted = False
        SCTTestRun._table_name = new_table_name
        run.save()

    LOGGER.warning("Broken runs: %s (missing build_id PK)", broken_runs)
    new_ids = [row["id"] for row in list(db.session.execute(f"SELECT id FROM {new_table_name}").all())]
    total_new_ids = len(new_ids)
    if total_ids - total_new_ids - len(broken_runs) != 0:
        LOGGER.critical(
            "Mismatch detected when comparing updated tables, %s != %s", total_ids, total_new_ids + len(broken_runs)
        )


if __name__ == "__main__":
    up()
