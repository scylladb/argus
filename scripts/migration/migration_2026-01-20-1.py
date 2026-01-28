import logging
from uuid import uuid4


from argus.backend.db import ScyllaCluster
from argus.backend.plugins.sct.testrun import SCTEvent
from argus.backend.util.logsetup import setup_application_logging


setup_application_logging(log_level=logging.INFO)
LOGGER = logging.getLogger(__name__)
DB = ScyllaCluster.get()


def migrate():
    LOGGER.warning("Getting events...")

    for event in SCTEvent.all():
        event.event_id = uuid4()
        LOGGER.info(
            "Added UUID('%s') for event ('%s', %s, %s).", event.event_id, event.run_id, event.severity, event.ts
        )
        event.save()

    LOGGER.warning("SCT Events updated with new index column.")


if __name__ == "__main__":
    migrate()
