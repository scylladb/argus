import time
import uuid
from dataclasses import asdict, dataclass
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

from argus.backend.models.web import ArgusGroup, ArgusRelease, ArgusTest, User
from argus.backend.service.client_service import ClientService
from argus.backend.service.issue_service import IssueService
from argus.backend.service.planner_service import CreatePlanPayload, PlanningService
from argus.backend.service.release_manager import ReleaseManagerService
from argus.backend.tests.conftest import get_fake_test_run

SCT = "scylla-cluster-tests"
JIRA_SERVER = "https://zxqtesting.atlassian.net"


@dataclass
class Seeded:
    release: ArgusRelease
    group: ArgusGroup
    tests: list[ArgusTest]


def unique(prefix: str) -> str:
    return f"{prefix}_{time.time_ns()}_{uuid.uuid4().hex[:6]}"


async def seed_release(service: ReleaseManagerService, test_count: int = 2) -> Seeded:
    release_name = unique("summary")
    release = await service.create_release(release_name, release_name, False)
    group_name = unique("group")
    group = await service.create_group(group_name, group_name, build_system_id=release_name, release_id=release.id)
    tests = []
    for _ in range(test_count):
        name = unique("test")
        tests.append(await service.create_test(name, name, name, name, group_id=group.id, release_id=release.id,
                                               plugin_name=SCT))
    return Seeded(release=release, group=group, tests=tests)


async def submit_run(client_service: ClientService, test: ArgusTest, version: str | None,
                     status: str | None = None) -> UUID:
    run_type, request = get_fake_test_run(test)
    await client_service.submit_run(run_type, asdict(request))
    run_id = UUID(request.run_id)
    if version:
        await client_service.submit_product_version(run_type, run_id, version)
    if status:
        await client_service.update_run_status(run_type, run_id, status)
    return run_id


async def create_plan(release: ArgusRelease, tests: list[ArgusTest], target_version: str, user: User,
                      groups: list[ArgusGroup] | None = None):
    payload = CreatePlanPayload(
        name=unique("plan"), description="", owner=user.id, participants=[], target_version=target_version,
        release_id=release.id, tests=[test.id for test in tests], groups=[group.id for group in groups or []],
        assignments={},
    )
    return await PlanningService().create_plan(payload, user)


def mocked_issue_service() -> IssueService:
    service = IssueService(dry_run=True)
    service.gh.gh = MagicMock(name="GithubClient")
    service.jira.jira = MagicMock(name="JiraClient")
    return service


def fake_remote_jira_issue(key: str) -> SimpleNamespace:
    project, _ = key.split("-")
    fields = SimpleNamespace(
        summary=f"Issue {key}", status=SimpleNamespace(name="Open"), project=SimpleNamespace(key=project), labels=[],
        assignee=None, issuetype=SimpleNamespace(name="Task"), priority=None,
    )
    return SimpleNamespace(key=key, permalink=lambda: f"{JIRA_SERVER}/browse/{key}", fields=fields,
                           raw={"editmeta": {"fields": {}}}, update=MagicMock(name="update"))


def new_jira_key() -> str:
    return f"SUMMARY-{time.time_ns() % 10**9}"


async def link_jira(service: IssueService, key: str, test: ArgusTest, run_id: UUID, user: User) -> dict:
    service.jira.jira.issue.return_value = fake_remote_jira_issue(key)
    return await service.submit(issue_url=f"{JIRA_SERVER}/browse/{key}", test_id=test.id, run_id=run_id, user=user)


async def link_github(service: IssueService, number: int, test: ArgusTest, run_id: UUID, user: User,
                      repo: str = "summary-repo") -> dict:
    remote_issue = SimpleNamespace(
        number=number, state="open", title=f"Issue {number}",
        html_url=f"https://github.com/scylladb/{repo}/issues/{number}",
        repository=SimpleNamespace(name=repo, owner=SimpleNamespace(name="scylladb")), labels=[], assignees=[],
    )
    service.gh.gh.get_repo.return_value.get_issue.return_value = remote_issue
    return await service.submit(issue_url=remote_issue.html_url, test_id=test.id, run_id=run_id, user=user)


def by_version(summary: dict, family: str) -> dict:
    entry = next(entry for entry in summary["families"] if entry["family"] == family)
    return {version["version"]: version for version in entry["versions"]} | {None: entry["rollup"]}
