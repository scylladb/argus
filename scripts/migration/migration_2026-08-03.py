import logging
from datetime import UTC, datetime

from argus.backend.db import ScyllaCluster
from argus.backend.models.ssh_key import SSHTunnelKey, SSHTunnelKeyByFingerprint
from argus.backend.util.logsetup import setup_application_logging


setup_application_logging(log_level=logging.INFO)
LOGGER = logging.getLogger(__name__)
DB = ScyllaCluster.get()


def migrate():
    """Backfill `ssh_tunnel_key_by_fingerprint` from existing `ssh_tunnel_key` rows.

    The proxy host reads the lookup table on every SSH authentication attempt.
    A key registered before this table existed has no lookup row, so it stops
    authenticating until its client re-registers. Run this after
    `flask cli sync-models` and before the new backend takes traffic.

    Each row carries a TTL derived from `expires_at`, so the copy expires with
    the key it points at. The migration is safe to re-run.
    """
    now = datetime.now(tz=UTC).replace(tzinfo=None)
    copied = 0
    skipped = 0

    for key in SSHTunnelKey.objects.all():
        ttl = int((key.expires_at - now).total_seconds())
        if ttl <= 0:
            LOGGER.info("Key %s expired at %s — skipping.", key.id, key.expires_at)
            skipped += 1
            continue

        SSHTunnelKeyByFingerprint.objects.ttl(ttl).create(
            fingerprint=key.fingerprint,
            key_id=key.id,
            user_id=key.user_id,
            tunnel_id=key.tunnel_id,
            public_key=key.public_key,
            created_at=key.created_at,
            expires_at=key.expires_at,
        )
        copied += 1
        LOGGER.info("Indexed key %s (%s) for %ds.", key.id, key.fingerprint, ttl)

    LOGGER.info("Migration complete. Indexed %d key(s), skipped %d expired.", copied, skipped)
    LOGGER.info(
        "Nothing reads the secondary index on ssh_tunnel_key.fingerprint now. "
        "Find it with DESCRIBE TABLE ssh_tunnel_key and drop it."
    )


if __name__ == "__main__":
    migrate()
