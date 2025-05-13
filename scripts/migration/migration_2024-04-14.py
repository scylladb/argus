import logging

from argus.backend.db import ScyllaCluster
from argus.backend.models.web import ArgusGithubIssue
from argus.backend.models.github_issue import GithubIssue, IssueLink
from argus.backend.util.logsetup import setup_application_logging

LOGGER = logging.getLogger(__name__)
DB = ScyllaCluster.get()

setup_application_logging(log_level=logging.INFO)


def migrate():
    old_issues: list[ArgusGithubIssue] = list(ArgusGithubIssue.all())
    total = len(old_issues)
    inserted = {}
    done = 0
    for idx, old_issue in enumerate(old_issues):
        LOGGER.info(
            "[%s/%s] Migrating %s/%s#%s attached to %s...",
            idx + 1,
            total,
            old_issue.owner,
            old_issue.repo,
            old_issue.issue_number,
            old_issue.run_id,
        )
        key = f"{old_issue.owner}/{old_issue.repo}#{old_issue.issue_number}"
        if not (i := inserted.get(key)):
            i = GithubIssue()
            i.id = old_issue.id
            i.user_id = old_issue.user_id
            i.title = old_issue.title
            i.type = old_issue.type
            i.owner = old_issue.owner
            i.repo = old_issue.repo
            i.number = old_issue.issue_number
            i.state = old_issue.last_status
            i.labels = []
            i.url = old_issue.url
            i.added_on = old_issue.added_on
            i.save()
            inserted[key] = i
            done += 1

        l = IssueLink()

        l.run_id = old_issue.run_id
        l.issue_id = i.id
        l.release_id = old_issue.release_id
        l.group_id = old_issue.group_id
        l.test_id = old_issue.test_id

        l.save()
        LOGGER.info("[%s/%s] Migrated", idx + 1, total)

    LOGGER.info("Migration complete. Consolidated %s issues into %s.", total, done)


if __name__ == "__main__":
    migrate()
