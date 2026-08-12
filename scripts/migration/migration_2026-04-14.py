import logging

from coodie.sync import BatchQuery

from argus.backend.db import ScyllaCluster
from argus.backend.plugins.sct.testrun import SCTResource, SCTTestRun
from argus.backend.util.logsetup import setup_application_logging


setup_application_logging(log_level=logging.INFO)
LOGGER = logging.getLogger(__name__)
DB = ScyllaCluster.get()


def migrate():
    LOGGER.warning("Starting migration: copying allocated_resources to sct_resource table...")

    total_runs = 0
    total_resources = 0
    skipped_runs = 0

    for run in SCTTestRun.find().only("id", "allocated_resources").all():
        total_runs += 1
        resources = run.allocated_resources
        if not resources:
            skipped_runs += 1
            continue

        with BatchQuery() as b:
            for res in resources:
                SCTResource(
                    run_id=run.id,
                    name=res.name,
                    state=res.state,
                    resource_type=res.resource_type,
                    instance_info=res.instance_info,
                ).save(batch=b)
                total_resources += 1

        LOGGER.info(
            "Migrated %d resources for run_id=%s",
            len(resources),
            run.id,
        )

    LOGGER.warning(
        "Migration complete. runs_processed=%d skipped=%d resources_migrated=%d",
        total_runs,
        skipped_runs,
        total_resources,
    )


if __name__ == "__main__":
    migrate()
