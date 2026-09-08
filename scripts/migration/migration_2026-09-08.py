"""Move OAuth tokens from ``user_oauth_token`` to ``user_oauth_token_v2``.

The v1 table was keyed by a synthetic ``id`` with secondary indexes on
``user_id`` and ``kind``. The v2 table is keyed by ``(user_id, token)`` with
``user_id`` as the partition key and ``token`` as the clustering key, so all
tokens of a user live in one partition; ``kind`` stays indexed.

Steps:

1. Create ``user_oauth_token_v2`` and its ``kind`` index (same DDL as
   ``sync-models``).
2. Copy every v1 row with a non-null ``user_id``, ``token`` and ``kind`` into
   v2 as non-expiring tokens (``expiration_date`` unset, no TTL). Rows missing
   any of them are logged and skipped. Idempotent: re-running rewrites the same
   rows.

The v1 table is left in place; drop it by hand once v2 is verified.

``token`` is a CQL reserved word: quote it (``"token"``) in any hand-written CQL.
"""

import logging

from argus.backend.db import ScyllaCluster
from argus.backend.models.web import UserOauthToken
from argus.backend.util.logsetup import setup_application_logging


setup_application_logging(log_level=logging.INFO)
LOGGER = logging.getLogger(__name__)
DB = ScyllaCluster.get()

LEGACY_TABLE = "user_oauth_token"


def _keyspace() -> str:
    return getattr(UserOauthToken.Settings, "keyspace", None) or DB.config["SCYLLA_KEYSPACE_NAME"]


def _table_exists(keyspace: str, table: str) -> bool:
    rows = DB.session.execute(
        "SELECT table_name FROM system_schema.tables WHERE keyspace_name = %s AND table_name = %s",
        (keyspace, table),
    )
    return rows.one() is not None


def copy_tokens(keyspace: str) -> int:
    if not _table_exists(keyspace, LEGACY_TABLE):
        LOGGER.warning("Table %s.%s does not exist; nothing to copy.", keyspace, LEGACY_TABLE)
        return 0

    rows = DB.session.execute(f'SELECT id, user_id, kind, "token" FROM {keyspace}.{LEGACY_TABLE}')
    copied = 0
    for row in rows:
        if not row["user_id"] or not row["token"] or not row["kind"]:
            LOGGER.warning("Skipping %s row %s: missing user_id, token or kind.", LEGACY_TABLE, row["id"])
            continue
        UserOauthToken(user_id=row["user_id"], token=row["token"], kind=row["kind"], expiration_date=None).save()
        copied += 1
    LOGGER.info("Copied %s tokens into %s.", copied, UserOauthToken.Settings.name)
    return copied


def migrate() -> None:
    keyspace = _keyspace()
    LOGGER.info("Syncing %s.%s...", keyspace, UserOauthToken.Settings.name)
    UserOauthToken.sync_table()
    copy_tokens(keyspace)
    LOGGER.info("Table %s.%s kept; drop it by hand once v2 is verified.", keyspace, LEGACY_TABLE)


if __name__ == "__main__":
    migrate()
