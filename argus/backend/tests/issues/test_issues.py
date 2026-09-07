"""
Tests for issue submission and state tracking through IssueService.

The remote GitHub (PyGithub) and Jira clients are replaced with MagicMocks
attached to a dry-run IssueService, so the fetch-on-submit and stale-issue
refresh paths are exercised without touching the network.
"""
from dataclasses import asdict
from datetime import UTC, datetime
import json
import logging
import time
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from coodie.exceptions import DocumentNotFound

from argus.backend.models.github_issue import GithubIssue, IssueLink
from argus.backend.models.jira import JiraIssue
from argus.backend.models.runtime_store import RuntimeStore
from argus.backend.models.web import ArgusEvent, ArgusEventTypes, ArgusTest, User
from argus.backend.plugins.sct.testrun import SCTTestRun
from argus.backend.service.client_service import ClientService
from argus.backend.service.github_service import GithubService
from argus.backend.service.issue_service import IssueService
from argus.backend.service.jira_service import JiraService
from argus.backend.service.testrun import TestRunService
from argus.backend.tests.conftest import get_fake_test_run

LOGGER = logging.getLogger(__name__)

JIRA_SERVER = "https://zxqtesting.atlassian.net"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def unique_suffix() -> str:
    """The test DB is session-scoped, so every test needs its own issue identity."""
    return uuid4().hex[:8]


def submit_run(client_service: ClientService, testrun_service: TestRunService, fake_test: ArgusTest) -> SCTTestRun:
    run_type, run_req = get_fake_test_run(fake_test)
    client_service.submit_run(run_type, asdict(run_req))
    return testrun_service.get_run(run_type, run_req.run_id)


def issue_added_events(run_id) -> list[dict]:
    events = ArgusEvent.find(run_id=run_id).allow_filtering().all()
    return [json.loads(e.body) for e in events if e.kind == ArgusEventTypes.TestRunIssueAdded.value]


def assert_refreshed_after(key: str, moment: datetime) -> None:
    """Scylla returns naive datetimes; treat the stored value as UTC before comparing."""
    value = RuntimeStore.get(key=key).value
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    assert value >= moment


def issue_removed_events(run_id) -> list[dict]:
    events = ArgusEvent.find(run_id=run_id).allow_filtering().all()
    return [json.loads(e.body) for e in events if e.kind == ArgusEventTypes.TestRunIssueRemoved.value]


def fake_remote_github_issue(owner: str, repo: str, number: int, state: str = "open", title: str = "Remote Issue",
                             labels: list | None = None, assignees: list | None = None) -> SimpleNamespace:
    """Mimics the subset of ``github.Issue.Issue`` that GithubService reads."""
    return SimpleNamespace(
        number=number,
        state=state,
        title=title,
        html_url=f"https://github.com/{owner}/{repo}/issues/{number}",
        repository=SimpleNamespace(name=repo, owner=SimpleNamespace(name=owner)),
        labels=labels if labels is not None else [],
        assignees=assignees if assignees is not None else [],
    )


def fake_github_label(name: str, color: str = "d73a4a", description: str | None = "Something isn't working") -> SimpleNamespace:
    return SimpleNamespace(id=int(time.time_ns() % 10**9), name=name, color=color, description=description)


def fake_github_assignee(login: str) -> SimpleNamespace:
    return SimpleNamespace(login=login, html_url=f"https://github.com/{login}")


def fake_remote_jira_issue(key: str, status: str = "To Do", summary: str = "Remote Jira Issue",
                           labels: list[str] | None = None, assignee_email: str | None = None) -> SimpleNamespace:
    """Mimics the subset of ``jira.Issue`` that JiraService reads."""
    project, _ = key.split("-")
    return SimpleNamespace(
        key=key,
        permalink=lambda: f"{JIRA_SERVER}/browse/{key}",
        fields=SimpleNamespace(
            summary=summary,
            status=SimpleNamespace(name=status),
            project=SimpleNamespace(key=project),
            labels=labels if labels is not None else [],
            assignee=SimpleNamespace(emailAddress=assignee_email) if assignee_email else None,
        ),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mocked_issue_service(argus_db) -> IssueService:
    """Dry-run IssueService with MagicMock remote clients plugged in.

    ``service.gh.gh`` stands in for ``github.Github`` and ``service.jira.jira``
    for ``jira.JIRA``. Tests configure ``get_repo``/``issue``/``search_issues``
    on those mocks and assert on the calls made.
    """
    service = IssueService(dry_run=True)
    service.gh.gh = MagicMock(name="GithubClient")
    service.jira.jira = MagicMock(name="JiraClient")
    return service


@pytest.fixture
def run(client_service: ClientService, testrun_service: TestRunService, fake_test: ArgusTest) -> SCTTestRun:
    return submit_run(client_service, testrun_service, fake_test)


# ---------------------------------------------------------------------------
# Submitting links to issues already known to Argus (no remote call)
# ---------------------------------------------------------------------------


def test_submit_github_issue_link_for_existing_issue(run: SCTTestRun, mocked_issue_service: IssueService, logged_in_user: User):
    suffix = unique_suffix()
    url = f"https://github.com/scylladb/argus-{suffix}/issues/1"
    GithubIssue(user_id=uuid4(), type="issues", owner="scylladb", repo=f"argus-{suffix}", number=1,
                state="open", title="Example Issue", url=url).save()

    result = mocked_issue_service.submit(issue_url=url, test_id=run.test_id, run_id=run.id, user=logged_in_user)

    assert result["title"] == "Example Issue"
    mocked_issue_service.gh.gh.get_repo.assert_not_called()

    issue_with_links = mocked_issue_service.get("run_id", run.id, True)
    assert len(issue_with_links) == 1
    assert len(issue_with_links[0]["links"]) == 1

    events = issue_added_events(run.id)
    assert len(events) == 1
    assert "attached" in events[0]["message"]
    assert events[0]["url"] == url


def test_submit_jira_issue_link_for_existing_issue(run: SCTTestRun, mocked_issue_service: IssueService, logged_in_user: User):
    key = f"FROBNICATOR-{int(time.time_ns() % 10**9)}"
    url = f"{JIRA_SERVER}/browse/{key}"
    JiraIssue(user_id=uuid4(), key=key, state="todo", summary="Example Issue", project="FROBNICATOR", permalink=url).save()

    result = mocked_issue_service.submit(issue_url=url, test_id=run.test_id, run_id=run.id, user=logged_in_user)

    assert result["summary"] == "Example Issue"
    mocked_issue_service.jira.jira.issue.assert_not_called()

    issue_with_links = mocked_issue_service.get("run_id", run.id, True)
    assert len(issue_with_links) == 1
    assert len(issue_with_links[0]["links"]) == 1

    events = issue_added_events(run.id)
    assert len(events) == 1
    assert "attached" in events[0]["message"]


# ---------------------------------------------------------------------------
# Submitting links to issues unknown to Argus (fetched from mocked remotes)
# ---------------------------------------------------------------------------


def test_submit_unknown_github_issue_fetches_from_remote(run: SCTTestRun, mocked_issue_service: IssueService, logged_in_user: User):
    repo = f"argus-{unique_suffix()}"
    number = 4242
    url = f"https://github.com/scylladb/{repo}/issues/{number}"
    remote_issue = fake_remote_github_issue(
        owner="scylladb", repo=repo, number=number, state="open", title="Cluster fell over",
        labels=[fake_github_label("bug"), fake_github_label("regression", color="ffffff", description=None)],
        assignees=[fake_github_assignee("octocat")],
    )
    remote_repo = MagicMock(name="Repository")
    remote_repo.get_issue.return_value = remote_issue
    mocked_issue_service.gh.gh.get_repo.return_value = remote_repo

    result = mocked_issue_service.submit(issue_url=url, test_id=run.test_id, run_id=run.id, user=logged_in_user)

    mocked_issue_service.gh.gh.get_repo.assert_called_once_with(f"scylladb/{repo}")
    remote_repo.get_issue.assert_called_once_with(number)

    assert result["title"] == "Cluster fell over"
    assert result["state"] == "open"
    assert result["number"] == number
    assert result["owner"] == "scylladb"
    assert result["repo"] == repo
    assert result["type"] == "issues"
    assert result["url"] == url

    stored: GithubIssue = GithubIssue.get(id=result["id"])
    assert stored.user_id == logged_in_user.id
    assert [label.name for label in stored.labels] == ["bug", "regression"]
    assert stored.labels[1].description is None
    assert [assignee.login for assignee in stored.assignees] == ["octocat"]
    assert stored.assignees[0].html_url == "https://github.com/octocat"

    link: IssueLink = IssueLink.get(run_id=run.id, issue_id=stored.id)
    assert link.type == "github"
    assert link.test_id == run.test_id
    assert link.release_id == run.release_id
    assert link.group_id == run.group_id
    assert link.user_id == logged_in_user.id
    assert link.event_id is None

    events = issue_added_events(run.id)
    assert len(events) == 1
    assert "added" in events[0]["message"]
    assert events[0]["title"] == "Cluster fell over"
    assert events[0]["state"] == "open"


def test_submit_github_pull_request_is_stored_with_pull_type(run: SCTTestRun, mocked_issue_service: IssueService, logged_in_user: User):
    repo = f"argus-{unique_suffix()}"
    url = f"https://github.com/scylladb/{repo}/pull/7"
    remote_repo = MagicMock(name="Repository")
    remote_repo.get_issue.return_value = fake_remote_github_issue(owner="scylladb", repo=repo, number=7, title="Fix it")
    mocked_issue_service.gh.gh.get_repo.return_value = remote_repo

    result = mocked_issue_service.submit(issue_url=url, test_id=run.test_id, run_id=run.id, user=logged_in_user)

    remote_repo.get_issue.assert_called_once_with(7)
    assert result["type"] == "pull"
    assert result["number"] == 7


def test_submit_unknown_jira_issue_fetches_from_remote(run: SCTTestRun, mocked_issue_service: IssueService, logged_in_user: User):
    key = f"FROBNICATOR-{int(time.time_ns() % 10**9)}"
    url = f"{JIRA_SERVER}/browse/{key}"
    mocked_issue_service.jira.jira.issue.return_value = fake_remote_jira_issue(
        key, status="In Progress", summary="Compaction stalls", labels=["regression", "compaction"],
        assignee_email="dev@scylladb.com",
    )

    result = mocked_issue_service.submit(issue_url=url, test_id=run.test_id, run_id=run.id, user=logged_in_user)

    mocked_issue_service.jira.jira.issue.assert_called_once_with(key)
    mocked_issue_service.gh.gh.get_repo.assert_not_called()

    assert result["key"] == key
    assert result["summary"] == "Compaction stalls"
    assert result["state"] == "in progress"
    assert result["project"] == "FROBNICATOR"
    assert result["permalink"] == url

    stored: JiraIssue = JiraIssue.get(id=result["id"])
    assert stored.user_id == logged_in_user.id
    assert stored.assignees == ["dev@scylladb.com"]
    assert [label.name for label in stored.labels] == ["regression", "compaction"]
    assert [label.id for label in stored.labels] == [
        mocked_issue_service.jira.derive_label_id("regression"),
        mocked_issue_service.jira.derive_label_id("compaction"),
    ]

    link: IssueLink = IssueLink.get(run_id=run.id, issue_id=stored.id)
    assert link.type == "jira"
    assert link.test_id == run.test_id

    events = issue_added_events(run.id)
    assert len(events) == 1
    assert "added" in events[0]["message"]
    assert events[0]["summary"] == "Compaction stalls"
    assert events[0]["state"] == "in progress"


def test_submit_jira_issue_without_assignee_stores_empty_assignees(run: SCTTestRun, mocked_issue_service: IssueService, logged_in_user: User):
    key = f"FROBNICATOR-{int(time.time_ns() % 10**9)}"
    url = f"{JIRA_SERVER}/browse/{key}"
    mocked_issue_service.jira.jira.issue.return_value = fake_remote_jira_issue(key, assignee_email=None)

    result = mocked_issue_service.submit(issue_url=url, test_id=run.test_id, run_id=run.id, user=logged_in_user)

    assert result["assignees"] == []
    assert result["labels"] == []


def test_submit_same_issue_twice_reuses_issue_and_adds_second_link(
        client_service: ClientService, testrun_service: TestRunService, fake_test: ArgusTest,
        mocked_issue_service: IssueService, logged_in_user: User):
    first_run = submit_run(client_service, testrun_service, fake_test)
    second_run = submit_run(client_service, testrun_service, fake_test)
    repo = f"argus-{unique_suffix()}"
    url = f"https://github.com/scylladb/{repo}/issues/9"
    remote_repo = MagicMock(name="Repository")
    remote_repo.get_issue.return_value = fake_remote_github_issue(owner="scylladb", repo=repo, number=9)
    mocked_issue_service.gh.gh.get_repo.return_value = remote_repo

    first = mocked_issue_service.submit(issue_url=url, test_id=first_run.test_id, run_id=first_run.id, user=logged_in_user)
    second = mocked_issue_service.submit(issue_url=url, test_id=second_run.test_id, run_id=second_run.id, user=logged_in_user)

    # Only the first submission should reach GitHub; the second must find the local copy.
    mocked_issue_service.gh.gh.get_repo.assert_called_once()
    assert first["id"] == second["id"]

    by_test = mocked_issue_service.get("test_id", fake_test.id, aggregate_by_issue=True)
    matching = [i for i in by_test if str(i["id"]) == str(first["id"])]
    assert len(matching) == 1
    assert {link.run_id for link in matching[0]["links"]} == {first_run.id, second_run.id}

    assert "added" in issue_added_events(first_run.id)[0]["message"]
    assert "attached" in issue_added_events(second_run.id)[0]["message"]


def test_submit_for_sct_event_records_event_id_on_link(run: SCTTestRun, mocked_issue_service: IssueService, logged_in_user: User):
    repo = f"argus-{unique_suffix()}"
    url = f"https://github.com/scylladb/{repo}/issues/11"
    remote_repo = MagicMock(name="Repository")
    remote_repo.get_issue.return_value = fake_remote_github_issue(owner="scylladb", repo=repo, number=11)
    mocked_issue_service.gh.gh.get_repo.return_value = remote_repo
    event_id = uuid4()

    result = mocked_issue_service.submit_for_sct_event(
        issue_url=url, test_id=run.test_id, event_id=str(event_id), run_id=run.id, user=logged_in_user)

    link: IssueLink = IssueLink.get(run_id=run.id, issue_id=result["id"])
    assert link.event_id == event_id

    by_event = mocked_issue_service.get("event_id", event_id)
    assert len(by_event) == 1
    assert str(by_event[0]["id"]) == str(result["id"])


# ---------------------------------------------------------------------------
# Submission failure modes
# ---------------------------------------------------------------------------


def test_submit_unknown_github_issue_with_remote_disabled_raises(run: SCTTestRun, issue_service: IssueService, logged_in_user: User):
    url = f"https://github.com/scylladb/argus-{unique_suffix()}/issues/1"

    with pytest.raises(Exception, match="Github Remote is disabled"):
        issue_service.submit(issue_url=url, test_id=run.test_id, run_id=run.id, user=logged_in_user)

    assert issue_service.get("run_id", run.id) == []
    assert issue_added_events(run.id) == []


def test_submit_malformed_github_url_raises_before_remote_call(run: SCTTestRun, mocked_issue_service: IssueService, logged_in_user: User):
    url = "https://github.com/scylladb/argus/commit/deadbeef"

    with pytest.raises(Exception, match="URL doesn't match Github schema"):
        mocked_issue_service.submit(issue_url=url, test_id=run.test_id, run_id=run.id, user=logged_in_user)

    mocked_issue_service.gh.gh.get_repo.assert_not_called()
    assert IssueLink.find(run_id=run.id).all() == []


def test_submit_remote_github_failure_leaves_no_link(run: SCTTestRun, mocked_issue_service: IssueService, logged_in_user: User):
    url = f"https://github.com/scylladb/argus-{unique_suffix()}/issues/1"
    mocked_issue_service.gh.gh.get_repo.side_effect = RuntimeError("404 Not Found")

    with pytest.raises(RuntimeError, match="404"):
        mocked_issue_service.submit(issue_url=url, test_id=run.test_id, run_id=run.id, user=logged_in_user)

    assert IssueLink.find(run_id=run.id).all() == []
    assert GithubIssue.find(url=url).all() == []
    assert issue_added_events(run.id) == []


def test_submit_remote_jira_failure_leaves_no_link(run: SCTTestRun, mocked_issue_service: IssueService, logged_in_user: User):
    key = f"FROBNICATOR-{int(time.time_ns() % 10**9)}"
    url = f"{JIRA_SERVER}/browse/{key}"
    mocked_issue_service.jira.jira.issue.side_effect = RuntimeError("Issue Does Not Exist")

    with pytest.raises(RuntimeError, match="Does Not Exist"):
        mocked_issue_service.submit(issue_url=url, test_id=run.test_id, run_id=run.id, user=logged_in_user)

    assert IssueLink.find(run_id=run.id).all() == []
    assert JiraIssue.find(permalink=url).all() == []


# ---------------------------------------------------------------------------
# State checking: refresh_stale_issues against mocked remotes
# ---------------------------------------------------------------------------


def test_refresh_stale_github_issues_updates_state_from_remote(run: SCTTestRun, mocked_issue_service: IssueService, logged_in_user: User):
    repo = f"argus-{unique_suffix()}"
    url = f"https://github.com/scylladb/{repo}/issues/21"
    remote_repo = MagicMock(name="Repository")
    remote_repo.get_issue.return_value = fake_remote_github_issue(
        owner="scylladb", repo=repo, number=21, state="open", title="Flaky nemesis", labels=[fake_github_label("bug")])
    mocked_issue_service.gh.gh.get_repo.return_value = remote_repo
    submitted = mocked_issue_service.submit(issue_url=url, test_id=run.test_id, run_id=run.id, user=logged_in_user)
    assert submitted["state"] == "open"

    # Remote state changes: closed, retitled, relabelled, assigned.
    closed_remote = fake_remote_github_issue(
        owner="scylladb", repo=repo, number=21, state="closed", title="Flaky nemesis (fixed)",
        labels=[fake_github_label("fixed", color="0e8a16")], assignees=[fake_github_assignee("fixer")])
    # Other repos in the shared test DB return nothing so only our issue is touched.
    other_repo = MagicMock(name="OtherRepository")
    other_repo.get_issues.return_value = []
    remote_repo.get_issues.return_value = [closed_remote]
    mocked_issue_service.gh.gh.get_repo.side_effect = lambda name: remote_repo if name == f"scylladb/{repo}" else other_repo
    mocked_issue_service.gh.gh.get_repo.reset_mock()
    before_refresh = datetime.now(UTC).replace(microsecond=0)

    mocked_issue_service.gh.refresh_stale_issues()

    assert f"scylladb/{repo}" in {c.args[0] for c in mocked_issue_service.gh.gh.get_repo.call_args_list}
    _, kwargs = remote_repo.get_issues.call_args
    assert kwargs["state"] == "all"
    assert kwargs["since"] is not None

    refreshed: GithubIssue = GithubIssue.get(id=submitted["id"])
    assert refreshed.state == "closed"
    assert refreshed.title == "Flaky nemesis (fixed)"
    assert [label.name for label in refreshed.labels] == ["fixed"]
    assert [assignee.login for assignee in refreshed.assignees] == ["fixer"]

    # The state visible through the run's issue list must reflect the refresh.
    for_run = mocked_issue_service.get("run_id", run.id)
    assert len(for_run) == 1
    assert for_run[0]["state"] == "closed"
    assert for_run[0]["subtype"] == "github"

    assert_refreshed_after(GithubService.LAST_RAN_KEY, before_refresh)


def test_refresh_stale_github_issues_ignores_unknown_and_case_variant_urls(run: SCTTestRun, mocked_issue_service: IssueService, logged_in_user: User):
    repo = f"Argus-{unique_suffix()}"
    url = f"https://github.com/ScyllaDB/{repo}/issues/22"
    remote_repo = MagicMock(name="Repository")
    remote_repo.get_issue.return_value = fake_remote_github_issue(owner="ScyllaDB", repo=repo, number=22, state="open")
    mocked_issue_service.gh.gh.get_repo.return_value = remote_repo
    submitted = mocked_issue_service.submit(issue_url=url, test_id=run.test_id, run_id=run.id, user=logged_in_user)

    # The remote reports the same issue with a lowercase URL, plus an unrelated issue Argus never linked.
    remote_repo.get_issues.return_value = [
        fake_remote_github_issue(owner="scylladb", repo=repo.lower(), number=22, state="closed"),
        fake_remote_github_issue(owner="scylladb", repo=repo.lower(), number=9999, state="closed", title="Never linked"),
    ]
    other_repo = MagicMock(name="OtherRepository")
    other_repo.get_issues.return_value = []
    mocked_issue_service.gh.gh.get_repo.side_effect = lambda name: remote_repo if name == f"ScyllaDB/{repo}" else other_repo

    mocked_issue_service.gh.refresh_stale_issues()

    assert GithubIssue.get(id=submitted["id"]).state == "closed"
    assert GithubIssue.find(number=9999).allow_filtering().all() == []


def test_refresh_stale_github_issues_survives_unreachable_repo(run: SCTTestRun, mocked_issue_service: IssueService, logged_in_user: User):
    repo = f"argus-{unique_suffix()}"
    url = f"https://github.com/scylladb/{repo}/issues/23"
    remote_repo = MagicMock(name="Repository")
    remote_repo.get_issue.return_value = fake_remote_github_issue(owner="scylladb", repo=repo, number=23, state="open")
    mocked_issue_service.gh.gh.get_repo.return_value = remote_repo
    submitted = mocked_issue_service.submit(issue_url=url, test_id=run.test_id, run_id=run.id, user=logged_in_user)

    mocked_issue_service.gh.gh.get_repo.side_effect = RuntimeError("repository was deleted")

    mocked_issue_service.gh.refresh_stale_issues()

    assert GithubIssue.get(id=submitted["id"]).state == "open"
    assert RuntimeStore.get(key=GithubService.LAST_RAN_KEY).value is not None


def test_refresh_stale_jira_issues_updates_state_from_remote(run: SCTTestRun, mocked_issue_service: IssueService, logged_in_user: User):
    key = f"FROBNICATOR-{int(time.time_ns() % 10**9)}"
    url = f"{JIRA_SERVER}/browse/{key}"
    mocked_issue_service.jira.jira.issue.return_value = fake_remote_jira_issue(
        key, status="To Do", summary="Node crash", labels=["bug"], assignee_email="a@scylladb.com")
    submitted = mocked_issue_service.submit(issue_url=url, test_id=run.test_id, run_id=run.id, user=logged_in_user)
    assert submitted["state"] == "to do"

    mocked_issue_service.jira.jira.search_issues.return_value = [
        fake_remote_jira_issue(key, status="Done", summary="Node crash (resolved)", labels=["bug", "fixed"], assignee_email="b@scylladb.com"),
        fake_remote_jira_issue("FROBNICATOR-1", status="Done", summary="Unrelated issue Argus never linked"),
    ]
    before_refresh = datetime.now(UTC).replace(microsecond=0)

    mocked_issue_service.jira.refresh_stale_issues()

    args, kwargs = mocked_issue_service.jira.jira.search_issues.call_args
    assert args[0].startswith('updated >= "')
    assert kwargs["maxResults"] == 0

    refreshed: JiraIssue = JiraIssue.get(id=submitted["id"])
    assert refreshed.state == "done"
    assert refreshed.summary == "Node crash (resolved)"
    assert refreshed.assignees == ["b@scylladb.com"]
    assert [label.name for label in refreshed.labels] == ["bug", "fixed"]
    assert [label.id for label in refreshed.labels] == [
        mocked_issue_service.jira.derive_label_id("bug"),
        mocked_issue_service.jira.derive_label_id("fixed"),
    ]

    for_run = mocked_issue_service.get("run_id", run.id)
    assert len(for_run) == 1
    assert for_run[0]["state"] == "done"
    assert for_run[0]["subtype"] == "jira"

    assert_refreshed_after(JiraService.LAST_RAN_KEY, before_refresh)


def test_refresh_stale_jira_issues_clears_assignee_when_unassigned(run: SCTTestRun, mocked_issue_service: IssueService, logged_in_user: User):
    key = f"FROBNICATOR-{int(time.time_ns() % 10**9)}"
    url = f"{JIRA_SERVER}/browse/{key}"
    mocked_issue_service.jira.jira.issue.return_value = fake_remote_jira_issue(key, assignee_email="a@scylladb.com")
    submitted = mocked_issue_service.submit(issue_url=url, test_id=run.test_id, run_id=run.id, user=logged_in_user)
    assert JiraIssue.get(id=submitted["id"]).assignees == ["a@scylladb.com"]

    mocked_issue_service.jira.jira.search_issues.return_value = [fake_remote_jira_issue(key, assignee_email=None)]

    mocked_issue_service.jira.refresh_stale_issues()

    assert JiraIssue.get(id=submitted["id"]).assignees == []


def test_refresh_only_touches_its_own_backend(run: SCTTestRun, mocked_issue_service: IssueService, logged_in_user: User):
    repo = f"argus-{unique_suffix()}"
    gh_url = f"https://github.com/scylladb/{repo}/issues/31"
    key = f"FROBNICATOR-{int(time.time_ns() % 10**9)}"
    jira_url = f"{JIRA_SERVER}/browse/{key}"
    remote_repo = MagicMock(name="Repository")
    remote_repo.get_issue.return_value = fake_remote_github_issue(owner="scylladb", repo=repo, number=31, state="open")
    remote_repo.get_issues.return_value = [fake_remote_github_issue(owner="scylladb", repo=repo, number=31, state="closed")]
    mocked_issue_service.gh.gh.get_repo.return_value = remote_repo
    mocked_issue_service.jira.jira.issue.return_value = fake_remote_jira_issue(key, status="To Do")
    mocked_issue_service.jira.jira.search_issues.return_value = [fake_remote_jira_issue(key, status="Done")]

    gh_submitted = mocked_issue_service.submit(issue_url=gh_url, test_id=run.test_id, run_id=run.id, user=logged_in_user)
    jira_submitted = mocked_issue_service.submit(issue_url=jira_url, test_id=run.test_id, run_id=run.id, user=logged_in_user)

    mocked_issue_service.gh.refresh_stale_issues()
    mocked_issue_service.jira.jira.search_issues.assert_not_called()
    assert GithubIssue.get(id=gh_submitted["id"]).state == "closed"
    assert JiraIssue.get(id=jira_submitted["id"]).state == "to do"

    for_run = {i["subtype"]: i for i in mocked_issue_service.get("run_id", run.id)}
    assert for_run["github"]["state"] == "closed"
    assert for_run["jira"]["state"] == "to do"

    mocked_issue_service.jira.refresh_stale_issues()
    assert JiraIssue.get(id=jira_submitted["id"]).state == "done"


# ---------------------------------------------------------------------------
# Deleting links
# ---------------------------------------------------------------------------


def test_delete_github_issue_link_removes_orphaned_issue(run: SCTTestRun, mocked_issue_service: IssueService, logged_in_user: User):
    repo = f"argus-{unique_suffix()}"
    url = f"https://github.com/scylladb/{repo}/issues/41"
    remote_repo = MagicMock(name="Repository")
    remote_repo.get_issue.return_value = fake_remote_github_issue(owner="scylladb", repo=repo, number=41)
    mocked_issue_service.gh.gh.get_repo.return_value = remote_repo
    submitted = mocked_issue_service.submit(issue_url=url, test_id=run.test_id, run_id=run.id, user=logged_in_user)

    result = mocked_issue_service.delete(issue_id=str(submitted["id"]), run_id=str(run.id), user=logged_in_user)

    assert result["deleted"] == submitted["id"]
    assert mocked_issue_service.get("run_id", run.id) == []
    with pytest.raises(DocumentNotFound):
        GithubIssue.get(id=submitted["id"])

    removed = issue_removed_events(run.id)
    assert len(removed) == 1
    assert removed[0]["url"] == url


def test_delete_jira_issue_link_falls_through_to_jira_backend(run: SCTTestRun, mocked_issue_service: IssueService, logged_in_user: User):
    key = f"FROBNICATOR-{int(time.time_ns() % 10**9)}"
    url = f"{JIRA_SERVER}/browse/{key}"
    mocked_issue_service.jira.jira.issue.return_value = fake_remote_jira_issue(key, summary="Deletable")
    submitted = mocked_issue_service.submit(issue_url=url, test_id=run.test_id, run_id=run.id, user=logged_in_user)

    result = mocked_issue_service.delete(issue_id=submitted["id"], run_id=run.id, user=logged_in_user)

    assert result["deleted"] == submitted["id"]
    assert mocked_issue_service.get("run_id", run.id) == []
    with pytest.raises(DocumentNotFound):
        JiraIssue.get(id=submitted["id"])

    removed = issue_removed_events(run.id)
    assert len(removed) == 1
    assert removed[0]["url"] == url
    assert removed[0]["title"] == "Deletable"
