"""Hash user API tokens: backfill ``user.token`` from the plaintext ``user.api_token``.

``User.api_token`` stored the API token in plaintext. The model now has a
``token`` column holding an HMAC-SHA256 digest instead (see
``argus.backend.service.user.hash_api_token``), so tokens are never stored
server-side. Because the digest is deterministic, tokens issued before this
change keep working once their digest is backfilled: this script does that.

Steps:

1. Ensure the ``token`` column and its ``user_token_idx`` index exist (the same
   DDL ``sync-models`` would run, so the order does not matter).
2. Copy ``hash_api_token(api_token)`` into ``token`` for every user with a
   non-empty ``api_token``. Idempotent: re-running recomputes the same digest.
3. Only with ``--drop-legacy-column``: drop ``user_api_token_idx`` and the
   ``api_token`` column. Do this once the deployment has been verified with the
   hashed tokens, since after the drop the plaintext tokens are gone for good.

The digest is keyed with ``SECRET_KEY``, so run this with the same
argus_web.yaml the web application uses.

``token`` is a CQL reserved word: quote it (``"token"``) in any hand-written CQL.
"""

import argparse
import logging

from argus.backend.db import ScyllaCluster
from argus.backend.models.web import User
from argus.backend.service.user import hash_api_token
from argus.backend.util.logsetup import setup_application_logging


setup_application_logging(log_level=logging.INFO)
LOGGER = logging.getLogger(__name__)
DB = ScyllaCluster.get()

LEGACY_COLUMN = "api_token"
LEGACY_INDEX = "user_api_token_idx"
NEW_COLUMN = "token"
NEW_INDEX = "user_token_idx"


def _keyspace_and_table() -> tuple[str, str]:
    keyspace = getattr(User.Settings, "keyspace", None) or DB.config["SCYLLA_KEYSPACE_NAME"]
    return keyspace, User.Settings.name


def _column_exists(keyspace: str, table: str, column: str) -> bool:
    rows = DB.session.execute(
        "SELECT column_name FROM system_schema.columns WHERE keyspace_name = %s AND table_name = %s AND column_name = %s",
        (keyspace, table, column),
    )
    return rows.one() is not None


def ensure_token_column(keyspace: str, table: str) -> None:
    if _column_exists(keyspace, table, NEW_COLUMN):
        LOGGER.info('Column %s.%s."%s" already exists.', keyspace, table, NEW_COLUMN)
    else:
        LOGGER.info('Adding column %s.%s."%s"...', keyspace, table, NEW_COLUMN)
        DB.session.execute(f'ALTER TABLE {keyspace}.{table} ADD "{NEW_COLUMN}" text')
    DB.session.execute(f'CREATE INDEX IF NOT EXISTS {NEW_INDEX} ON {keyspace}.{table} ("{NEW_COLUMN}")')


def backfill_token_digests(keyspace: str, table: str) -> int:
    if not _column_exists(keyspace, table, LEGACY_COLUMN):
        LOGGER.warning(
            "Column %s.%s.%s does not exist (already dropped?); nothing to backfill.", keyspace, table, LEGACY_COLUMN
        )
        return 0

    update = DB.session.prepare(f'UPDATE {keyspace}.{table} SET "{NEW_COLUMN}" = ? WHERE id = ?')
    rows = DB.session.execute(f"SELECT id, {LEGACY_COLUMN} FROM {keyspace}.{table}")
    migrated = 0
    for row in rows:
        plaintext = row["api_token"]
        if not plaintext:
            continue
        DB.session.execute(update, (hash_api_token(plaintext), row["id"]))
        migrated += 1
    LOGGER.info("Backfilled token digests for %s users.", migrated)
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
    ensure_token_column(keyspace, table)
    backfill_token_digests(keyspace, table)
    if drop_legacy:
        drop_legacy_column(keyspace, table)
    else:
        LOGGER.info(
            "Plaintext column %s kept. Re-run with --drop-legacy-column once the hashed tokens are verified.",
            LEGACY_COLUMN,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--drop-legacy-column",
        action="store_true",
        help=f"drop the plaintext {LEGACY_COLUMN} column and its index after backfilling",
    )
    args = parser.parse_args()
    migrate(drop_legacy=args.drop_legacy_column)
