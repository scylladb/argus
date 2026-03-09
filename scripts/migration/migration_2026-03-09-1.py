import logging

from argus.backend.db import ScyllaCluster
from argus.backend.plugins.loader import all_plugin_models
from argus.backend.util.common import get_build_number
from argus.backend.util.logsetup import setup_application_logging


setup_application_logging(log_level=logging.INFO)
LOGGER = logging.getLogger(__name__)
DB = ScyllaCluster.get()


def migrate():
    models = all_plugin_models()

    for model in models:
        table = model.table_name()
        LOGGER.info("Processing table: %s", table)
        updated = 0
        skipped = 0

        for run in model.filter().limit(None).only(["build_id", "start_time", "build_job_url", "build_number"]).all():
            if run.build_number is not None:
                skipped += 1
                continue

            build_number = get_build_number(run.build_job_url)
            if build_number is None:
                LOGGER.warning(
                    "Could not derive build_number for %s build_id=%s start_time=%s build_job_url=%r — skipping",
                    table,
                    run.build_id,
                    run.start_time,
                    run.build_job_url,
                )
                skipped += 1
                continue

            model.objects(build_id=run.build_id, start_time=run.start_time).update(build_number=build_number)
            updated += 1
            LOGGER.info(
                "Updated %s build_id=%s start_time=%s build_number=%s",
                table,
                run.build_id,
                run.start_time,
                build_number,
            )

        LOGGER.warning("Table %s: updated=%d skipped=%d", table, updated, skipped)

    LOGGER.warning("Migration complete.")


if __name__ == "__main__":
    migrate()
