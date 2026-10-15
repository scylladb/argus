"""Backfill the ARGUS-178 ``priority`` column of ``jira_issue`` from Jira.

Reads every row without a priority, asks Jira for those keys in batches, and
writes the ``priority`` column alone.

A row that already holds a priority is skipped, so re-running is safe. A batch
that Jira refuses is logged and the scan continues; the summary reports how many
keys failed, and a second run retries them. A key that Jira does not return, or
returns without a priority, counts as missing.

Run it after ``sync-models`` has added the column.

    uv run python scripts/migration/migration_2026-10-15_backfill_jira_issue_priority.py
    uv run python scripts/migration/migration_2026-10-15_backfill_jira_issue_priority.py --key SCT-1234
"""

import argparse
import asyncio
import logging
from collections import defaultdict

from jira.exceptions import JIRAError
from requests import RequestException

from argus.backend.db import ScyllaCluster
from argus.backend.models.jira import JiraIssue
from argus.backend.service.jira_service import JiraService
from argus.backend.util.common import chunk
from argus.backend.util.logsetup import setup_application_logging


setup_application_logging(log_level=logging.INFO)
LOGGER = logging.getLogger(__name__)
DB = ScyllaCluster.get()

BATCH_SIZE = 100


async def rows_without_priority(key: str | None = None) -> list[JiraIssue]:
    rows = await (JiraIssue.find(key=key) if key else JiraIssue.find()).all()
    return [row for row in rows if row.priority is None]


async def backfill(key: str | None = None) -> dict[str, int]:
    counts = {"updated": 0, "missing": 0, "failed": 0}
    rows_by_key: dict[str, list[JiraIssue]] = defaultdict(list)
    for row in await rows_without_priority(key):
        rows_by_key[row.key].append(row)
    LOGGER.info("Backfilling %s issues without a priority...", len(rows_by_key))

    jira = JiraService().jira
    for batch in chunk(sorted(rows_by_key), BATCH_SIZE):
        try:
            remote_issues = await asyncio.to_thread(
                jira.search_issues, f"key in ({', '.join(batch)})", fields="priority", maxResults=0
            )
        except (JIRAError, RequestException):
            LOGGER.exception("Jira refused a batch of %s keys starting at %s, continuing", len(batch), batch[0])
            counts["failed"] += len(batch)
            continue

        priorities = {issue.key: JiraService.priority_name(issue.fields) for issue in remote_issues}
        for issue_key in batch:
            if not (priority := priorities.get(issue_key)):
                LOGGER.info("Jira returned no priority for %s", issue_key)
                counts["missing"] += 1
                continue
            for row in rows_by_key[issue_key]:
                await row.update(priority=priority)
            counts["updated"] += 1
        LOGGER.info("Processed %s keys...", counts["updated"] + counts["missing"] + counts["failed"])
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--key", default=None, help="backfill one issue key instead of every issue")
    args = parser.parse_args()

    counts = asyncio.run(backfill(args.key))
    LOGGER.info("Done. %(updated)s keys updated, %(missing)s missing, %(failed)s failed.", counts)
    if counts["failed"]:
        LOGGER.warning("Re-run the script to retry the %s failed keys.", counts["failed"])


if __name__ == "__main__":
    main()
