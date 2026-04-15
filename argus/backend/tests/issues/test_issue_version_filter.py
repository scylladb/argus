from dataclasses import asdict
import itertools
import logging
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

from argus.backend.models.github_issue import GithubIssue
from argus.backend.models.jira import JiraIssue
from argus.backend.plugins.sct.testrun import SCTTestRun
from argus.backend.service.client_service import ClientService
from argus.backend.service.issue_service import IssueService
from argus.backend.service.testrun import TestRunService
from argus.backend.tests.conftest import get_fake_test_run

if TYPE_CHECKING:
    from argus.backend.models.web import ArgusRelease, ArgusTest

LOGGER = logging.getLogger(__name__)

# Unique issue numbers across parametrized cases (session-scoped DB).
issue_counter = itertools.count(1000)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def submit_run_with_version(
    client_service: ClientService,
    testrun_service: TestRunService,
    fake_test: "ArgusTest",
    scylla_version: str | None = None,
) -> SCTTestRun:
    """Submit a test run and optionally set its scylla_version."""
    run_type, run_request = get_fake_test_run(fake_test)
    client_service.submit_run(run_type, asdict(run_request))
    run: SCTTestRun = testrun_service.get_run(run_type, run_request.run_id)
    if scylla_version is not None:
        run.scylla_version = scylla_version
        run.save()
    return run


def create_github_issue(
    owner: str = "scylladb", repo: str = "argus", number: int | None = None, title: str = "Test Issue",
) -> GithubIssue:
    """Create and persist a GithubIssue."""
    if number is None:
        number = next(issue_counter)
    return GithubIssue.create(
        user_id=uuid4(),
        type="issues",
        owner=owner,
        repo=repo,
        number=number,
        state="open",
        title=title,
        url=f"https://github.com/{owner}/{repo}/issues/{number}",
    )


def create_jira_issue(
    key: str | None = None, summary: str = "Test Jira Issue", project: str = "SCYLLA",
) -> JiraIssue:
    """Create and persist a JiraIssue."""
    if key is None:
        key = f"SCYLLA-{next(issue_counter)}"
    return JiraIssue.create(
        user_id=uuid4(),
        key=key,
        state="todo",
        summary=summary,
        project=project,
        permalink=f"https://scylladb.atlassian.net/browse/{key}",
    )


DYNAMIC_FIELDS = {"links", "added_on"}


def strip_dynamic(record: dict) -> dict:
    """Remove dynamic fields (links, added_on) that can't be compared statically."""
    return {k: v for k, v in record.items() if k not in DYNAMIC_FIELDS}


def expected_github_issue(issue: GithubIssue) -> dict:
    """Static shape of a service-level GitHub issue result (without links/added_on)."""
    return {
        "id": issue.id,
        "user_id": issue.user_id,
        "type": "issues",
        "owner": "scylladb",
        "repo": "argus",
        "number": issue.number,
        "state": "open",
        "title": issue.title,
        "labels": [],
        "assignees": [],
        "url": issue.url,
        "subtype": "github",
    }


def expected_jira_issue(issue: JiraIssue) -> dict:
    """Static shape of a service-level Jira issue result (without links/added_on)."""
    return {
        "id": issue.id,
        "user_id": issue.user_id,
        "summary": issue.summary,
        "key": issue.key,
        "state": "todo",
        "project": "SCYLLA",
        "permalink": issue.permalink,
        "labels": [],
        "assignees": [],
        "subtype": "jira",
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def linked_github_issue(client_service, testrun_service, fake_test, issue_service):
    """Factory fixture: call with (scylla_version, title) to get (run, issue) with a linked GitHub issue."""

    def factory(scylla_version: str | None, title: str) -> tuple[SCTTestRun, GithubIssue]:
        run = submit_run_with_version(client_service, testrun_service, fake_test, scylla_version=scylla_version)
        issue = create_github_issue(title=title)
        issue_service.submit(issue_url=issue.url, test_id=run.test_id, run_id=run.id)
        return run, issue

    return factory


@pytest.fixture
def linked_jira_issue(client_service, testrun_service, fake_test, issue_service):
    """Factory fixture: call with (scylla_version, summary) to get (run, issue) with a linked Jira issue."""

    def factory(scylla_version: str | None, summary: str) -> tuple[SCTTestRun, JiraIssue]:
        run = submit_run_with_version(client_service, testrun_service, fake_test, scylla_version=scylla_version)
        issue = create_jira_issue(summary=summary)
        issue_service.submit(issue_url=issue.permalink, test_id=run.test_id, run_id=run.id)
        return run, issue

    return factory


# ---------------------------------------------------------------------------
# Service-level tests: IssueService.get() with product_version
# ---------------------------------------------------------------------------

EXPECTED_BUILDERS = {
    "github": expected_github_issue,
    "jira": expected_jira_issue,
}


@pytest.mark.parametrize("issue_type", ["github", "jira"])
@pytest.mark.parametrize(
    "scylla_version, product_version, include_no_version, expects_match",
    [
        pytest.param("2025.1.12", "2025.1.12", False, True, id="exact_match"),
        pytest.param("2025.1.12", "2025.1", False, True, id="prefix_match"),
        pytest.param("2024.2.5", "2025.1", False, False, id="non_matching"),
        pytest.param("2024.2.5", None, False, True, id="no_filter"),
        pytest.param(None, "!noVersion", False, True, id="no_version_special"),
        pytest.param("2025.1.12", "!noVersion", False, False, id="no_version_excludes_versioned"),
        pytest.param(None, "2025.1", True, True, id="include_no_version_true"),
        pytest.param(None, "2025.1", False, False, id="include_no_version_false"),
    ],
)
def test_get_issues_version_filter(
    request: pytest.FixtureRequest,
    issue_service: IssueService,
    issue_type: str,
    scylla_version: str | None,
    product_version: str | None,
    include_no_version: bool,
    expects_match: bool,
):
    """Issues are filtered (or not) based on run version, product_version param, and include_no_version flag."""
    fixture_name = f"linked_{issue_type}_issue"
    factory = request.getfixturevalue(fixture_name)
    run, issue = factory(scylla_version, f"{issue_type}: {scylla_version}")

    results = issue_service.get(
        filter_key="run_id",
        filter_id=run.id,
        aggregate_by_issue=True,
        product_version=product_version,
        include_no_version=include_no_version,
    )

    comparable = [strip_dynamic(r) for r in results]
    link_run_ids = [link.run_id for r in results for link in r["links"]]
    expected = [EXPECTED_BUILDERS[issue_type](issue)] if expects_match else []
    expected_link_run_ids = [run.id] if expects_match else []

    assert comparable == expected
    assert link_run_ids == expected_link_run_ids


# ---------------------------------------------------------------------------
# Service-level test: release_id filter key (multi-run, stays standalone)
# ---------------------------------------------------------------------------


def test_get_issues_version_filter_with_release_filter_key(
    issue_service: IssueService,
    linked_github_issue,
    release: "ArgusRelease",
):
    """Version filtering should work with filter_key='release_id' (the primary dashboard use case)."""
    linked_github_issue("2025.2.1", "Release filter match")
    linked_github_issue("2024.1.0", "Release filter no match")

    results = issue_service.get(
        filter_key="release_id",
        filter_id=release.id,
        aggregate_by_issue=True,
        product_version="2025.2",
    )

    returned_titles = {r["title"] for r in results}
    assert "Release filter match" in returned_titles
    assert "Release filter no match" not in returned_titles
