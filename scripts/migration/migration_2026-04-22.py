import logging

from argus.backend.db import ScyllaCluster
from argus.backend.models.web import ArgusRelease, ReleaseDistinctVersions, ReleaseDistinctImages
from argus.backend.plugins.loader import AVAILABLE_PLUGINS
from argus.backend.util.logsetup import setup_application_logging


setup_application_logging(log_level=logging.INFO)
LOGGER = logging.getLogger(__name__)
DB = ScyllaCluster.get()


def migrate():
    # Idempotency check: if any row exists in ReleaseDistinctVersions the
    # backfill has already run — skip entirely.
    existing = ReleaseDistinctVersions.objects.limit(1).all()
    if list(existing):
        LOGGER.info("ReleaseDistinctVersions already populated — skipping migration.")
        return

    sct_model = AVAILABLE_PLUGINS["scylla-cluster-tests"].model
    table = sct_model.table_name()
    releases = list(ArgusRelease.objects.all())
    LOGGER.info("Backfilling release indexes for %d release(s)...", len(releases))

    for release in releases:
        LOGGER.info("Processing release: %s (%s)", release.name, release.id)

        # --- Versions ---
        version_stmt = DB.prepare(f"SELECT scylla_version FROM {table} WHERE release_id = ?")
        version_stmt.fetch_size = 2000
        seen_versions = set()
        for row in DB.session.execute(version_stmt, (release.id,)):
            v = row["scylla_version"]
            if v and v not in seen_versions:
                ReleaseDistinctVersions.create(release_id=release.id, version=v)
                seen_versions.add(v)
        LOGGER.info("  versions: %d distinct", len(seen_versions))

        # --- Images ---
        image_stmt = DB.prepare(f"SELECT cloud_setup FROM {table} WHERE release_id = ?")
        image_stmt.fetch_size = 2000
        seen_images = set()
        for row in DB.session.execute(image_stmt, (release.id,)):
            image_id = sct_model.get_image(row)
            if image_id and image_id not in seen_images:
                ReleaseDistinctImages.create(release_id=release.id, image_id=image_id)
                seen_images.add(image_id)
        LOGGER.info("  images:   %d distinct", len(seen_images))

    LOGGER.info("Migration complete.")


if __name__ == "__main__":
    migrate()
