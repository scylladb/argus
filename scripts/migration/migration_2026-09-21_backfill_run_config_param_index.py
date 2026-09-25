"""Backfill the ARGUS-157 config parameter indexes from ``run_configuration``.

Fills three tables for every config already submitted:

- ``run_config_param_by_run_v1`` — every parameter of one run, in one partition.
- ``run_config_param_value_index_v1`` — the distinct values of one parameter.
- ``run_config_param_name_v1`` — the catalogue of parameter names.

It pages ``run_configuration``, which holds the raw config keyed by ``run_id``,
and replays ``ClientService.parse_config_values`` over each row. A run whose
config predates the parser gets its parameters for the first time.

Every write is an upsert, so re-running is safe, and the scan is resumable per
run. A config whose content is not JSON is logged and skipped, as the parser
does.

Run it after ``sync-models`` has created the three tables, and before deploying
anything that reads them.

    uv run python scripts/migration/migration_2026-09-21_backfill_run_config_param_index.py
    uv run python scripts/migration/migration_2026-09-21_backfill_run_config_param_index.py --run-id <uuid>
"""

import argparse
import logging
from uuid import UUID

from argus.backend.db import ScyllaCluster
from argus.backend.service.client_service import ClientService
from argus.backend.util.logsetup import setup_application_logging


setup_application_logging(log_level=logging.INFO)
LOGGER = logging.getLogger(__name__)
DB = ScyllaCluster.get()

PROGRESS_EVERY = 500


def _iter_configs(run_id: UUID | None):
    if run_id:
        query = DB.prepare("SELECT run_id, name, content FROM run_configuration WHERE run_id = ?")
        return DB.session.execute(query, parameters=(run_id,))
    return DB.session.execute("SELECT run_id, name, content FROM run_configuration")


def backfill(run_id: UUID | None = None) -> tuple[int, int]:
    parsed = 0
    skipped = 0
    for row in _iter_configs(run_id):
        content = row["content"]
        if not content:
            skipped += 1
            continue
        try:
            ClientService.parse_config_values(row["name"], content, str(row["run_id"]))
        except Exception:
            LOGGER.exception("Failed to parse config %s of run %s", row["name"], row["run_id"])
            skipped += 1
            continue
        parsed += 1
        if parsed % PROGRESS_EVERY == 0:
            LOGGER.info("Replayed %s configs so far...", parsed)
    return parsed, skipped


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", type=UUID, default=None, help="replay one run instead of every run")
    args = parser.parse_args()

    parsed, skipped = backfill(args.run_id)
    LOGGER.info("Done. Replayed %s configs, skipped %s.", parsed, skipped)


if __name__ == "__main__":
    main()
