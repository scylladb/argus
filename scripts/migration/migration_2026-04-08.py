from collections import defaultdict
import logging

from argus.backend.db import ScyllaCluster
from argus.backend.plugins.sct.testrun import SCTNemesis, SCTTestRun
from argus.backend.util.logsetup import setup_application_logging


setup_application_logging(log_level=logging.INFO)
LOGGER = logging.getLogger(__name__)
DB = ScyllaCluster.get()


def migrate():
    run_count = DB.session.execute("SELECT count(*) FROM sct_test_run", timeout=30.0).one()["count"]
    runs = SCTTestRun.filter().limit(None).only(["id", "nemesis_data", "build_id", "start_time"]).all()
    for idx, run in enumerate(runs):
        nemesis_stats = defaultdict(lambda: 0)
        LOGGER.info("[%s/%s] Migrating nemeses from run %s...", idx + 1, run_count, run.id)
        for nemesis in run.nemesis_data:
            nemesis_stats["total"] += 1
            nem = SCTNemesis()
            nem.run_id = run.id
            nem.start_time = nemesis.start_time
            nem.end_time = nemesis.end_time
            nem.status = nemesis.status
            nem.class_name = nemesis.class_name
            nem.name = nemesis.name
            nem.duration = nemesis.duration
            nem.target_node = nemesis.target_node
            nem.stack_trace = nemesis.stack_trace
            nemesis_stats[nem.status] += 1
            nem.save()

        SCTTestRun.objects(build_id=run.build_id, start_time=run.start_time).update(nemesis_stats=nemesis_stats)
        LOGGER.info("[%s/%s] Migrated nemeses for run %s.", idx + 1, run_count, run.id)


if __name__ == "__main__":
    migrate()
