import logging
from collections import defaultdict

from argus.backend.db import ScyllaCluster
from argus.backend.models.plan import ArgusReleasePlan
from argus.backend.models.web import ArgusRelease
from argus.backend.util.logsetup import setup_application_logging


setup_application_logging(log_level=logging.INFO)
LOGGER = logging.getLogger(__name__)
DB = ScyllaCluster.get()


def migrate():
    """Backfill the `key` (releaseName#planNumber) field on existing release plans.

    Plans are grouped by release and numbered by creation order (the TimeUUID `id`),
    assigning `releaseName#1, #2, ...`. Plans that already have a key are skipped, so
    the migration is safe to re-run.
    """
    plans_by_release: dict = defaultdict(list)
    for plan in ArgusReleasePlan.objects.all():
        plans_by_release[plan.release_id].append(plan)

    LOGGER.info("Backfilling plan keys across %d release(s)...", len(plans_by_release))

    release_names: dict = {}
    total_assigned = 0

    for release_id, plans in plans_by_release.items():
        if release_id not in release_names:
            try:
                release_names[release_id] = ArgusRelease.get(id=release_id).name
            except ArgusRelease.DoesNotExist:
                LOGGER.warning("Release %s not found — skipping %d plan(s).", release_id, len(plans))
                continue
        release_name = release_names[release_id]

        # TimeUUID id ~ creation order
        plans.sort(key=lambda p: p.id)

        number = 0
        for plan in plans:
            number += 1
            if plan.key:
                LOGGER.info("Plan %s already has key %s — skipping.", plan.id, plan.key)
                continue
            plan.key = f"{release_name}#{number}"
            plan.save()
            total_assigned += 1
            LOGGER.info("Assigned key %s to plan %s", plan.key, plan.id)

    LOGGER.info("Migration complete. Assigned %d plan key(s).", total_assigned)


if __name__ == "__main__":
    migrate()
