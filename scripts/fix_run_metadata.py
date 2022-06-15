import logging
from argus.backend.db import ScyllaCluster
from argus.db.testrun import TestRun

logging.basicConfig()
LOGGER = logging.getLogger()
LOGGER.setLevel(logging.DEBUG)


DB = ScyllaCluster.get()

ALL_RUNS = list(DB.session.execute(f"SELECT id FROM {TestRun.table_name()}").all())
TOTAL_RUNS = len(ALL_RUNS)

for idx, row in enumerate(ALL_RUNS):
    LOGGER.info("[%s/%s] Fixing %s...", idx+1, TOTAL_RUNS, row["id"])
    tr = TestRun.from_id(test_id=row["id"])
    LOGGER.info("Loaded %s:%s/%s/%s", tr.build_id, tr.test_id, tr.group_id, tr.release_id)
    tr._assign_categories()
    tr.save()
