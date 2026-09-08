"""Move user API tokens from ``user.api_token`` into ``user_oauth_token_v2``.

``User.api_token`` stored each user's API token in plaintext. API tokens now
live in ``user_oauth_token_v2`` under ``kind = "api"``, keyed by
``(user_id, token)``, and only the HMAC-SHA256 digest of the token is stored
(see ``argus.backend.service.user.hash_api_token``). The digest is
deterministic, so tokens issued before this change keep working once migrated.

Run ``migration_2026-09-08.py`` first so the v2 table exists.

Steps:

1. Insert ``(user_id, hash_api_token(api_token), "api")`` for every user with a
   non-empty ``api_token``. Migrated tokens are non-expiring (``expiration_date``
   unset, no TTL). Idempotent: re-running rewrites the same rows.
2. Only with ``--drop-legacy-column``: drop ``user_api_token_idx`` and the
   ``api_token`` column. Do this once the deployment has been verified, since
   after the drop the plaintext tokens are gone for good.

The digest is keyed with ``SECRET_KEY``, so run this with the same
argus_web.yaml the web application uses.
"""

import argparse
import logging

from argus.backend.db import ScyllaCluster
from argus.backend.models.web import User, UserOauthToken
from argus.backend.service.user import API_TOKEN_KIND, hash_api_token
from argus.backend.util.logsetup import setup_application_logging


setup_application_logging(log_level=logging.INFO)
LOGGER = logging.getLogger(__name__)
DB = ScyllaCluster.get()

LEGACY_COLUMN = "api_token"
LEGACY_INDEX = "user_api_token_idx"


def _keyspace_and_table() -> tuple[str, str]:
    keyspace = getattr(User.Settings, "keyspace", None) or DB.config["SCYLLA_KEYSPACE_NAME"]
    return keyspace, User.Settings.name


def _column_exists(keyspace: str, table: str, column: str) -> bool:
    rows = DB.session.execute(
        "SELECT column_name FROM system_schema.columns WHERE keyspace_name = %s AND table_name = %s AND column_name = %s",
        (keyspace, table, column),
    )
    return rows.one() is not None


def migrate_api_tokens(keyspace: str, table: str) -> int:
    if not _column_exists(keyspace, table, LEGACY_COLUMN):
        LOGGER.warning(
            "Column %s.%s.%s does not exist (already dropped?); nothing to migrate.", keyspace, table, LEGACY_COLUMN
        )
        return 0

    rows = DB.session.execute(f"SELECT id, {LEGACY_COLUMN} FROM {keyspace}.{table}")
    migrated = 0
    for row in rows:
        plaintext = row[LEGACY_COLUMN]
        if not plaintext:
            continue
        UserOauthToken(
            user_id=row["id"], token=hash_api_token(plaintext), kind=API_TOKEN_KIND, expiration_date=None
        ).save()
        migrated += 1
    LOGGER.info("Migrated API tokens for %s users into %s.", migrated, UserOauthToken.Settings.name)
    return migrated


def drop_legacy_column(keyspace: str, table: str) -> None:
    if not _column_exists(keyspace, table, LEGACY_COLUMN):
        LOGGER.info("Column %s.%s.%s already dropped.", keyspace, table, LEGACY_COLUMN)
        return
    LOGGER.warning(
        "Dropping index %s and column %s.%s.%s (plaintext tokens)...", LEGACY_INDEX, keyspace, table, LEGACY_COLUMN
    )
    DB.session.execute(f"DROP INDEX IF EXISTS {keyspace}.{LEGACY_INDEX}")
    DB.session.execute(f"ALTER TABLE {keyspace}.{table} DROP {LEGACY_COLUMN}")
    LOGGER.warning("Dropped %s.%s.%s.", keyspace, table, LEGACY_COLUMN)


def migrate(drop_legacy: bool = False) -> None:
    keyspace, table = _keyspace_and_table()
    migrate_api_tokens(keyspace, table)
    if drop_legacy:
        drop_legacy_column(keyspace, table)
    else:
        LOGGER.info(
            "Plaintext column %s kept. Re-run with --drop-legacy-column once the migrated tokens are verified.",
            LEGACY_COLUMN,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--drop-legacy-column",
        action="store_true",
        help=f"drop the plaintext {LEGACY_COLUMN} column and its index after migrating",
    )
    args = parser.parse_args()
    migrate(drop_legacy=args.drop_legacy_column)
