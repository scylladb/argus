import logging

from argus.backend.db import ScyllaCluster
from argus.backend.models.ssh_key import SSHTunnelKey
from argus.backend.util.logsetup import setup_application_logging


setup_application_logging(log_level=logging.INFO)
LOGGER = logging.getLogger(__name__)
DB = ScyllaCluster.get()

_LEGACY_LOOKUP_TABLE = "sshtunnel_key_by_fingerprint"


def migrate():
    """Drop the hand-written fingerprint lookup table.

    `ssh_tunnel_key_by_fingerprint` is a materialized view now. ScyllaDB builds
    it from the existing `sshtunnel_key` rows and keeps the TTL of each row, so
    no backfill is necessary.

    Run this before `flask cli sync-models`. An earlier build of this branch
    created a plain table with the same purpose. The table is not read any more.
    The migration is safe to re-run.
    """
    session = DB.session
    base_table = SSHTunnelKey.column_family_name(include_keyspace=False)

    session.execute(f"DROP TABLE IF EXISTS {_LEGACY_LOOKUP_TABLE}")
    LOGGER.info("Dropped legacy lookup table %s.", _LEGACY_LOOKUP_TABLE)
    LOGGER.info(
        "Run `flask cli sync-models` next. It creates the materialized view over %s.",
        base_table,
    )
    LOGGER.info(
        "Nothing reads the secondary index on %s.fingerprint now. Find it with DESCRIBE TABLE %s and drop it.",
        base_table,
        base_table,
    )


if __name__ == "__main__":
    migrate()
