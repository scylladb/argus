import asyncio
from uuid import UUID
from coodie.exceptions import DocumentNotFound

from argus.backend.models.github_issue import GithubIssue, IssueLink
from argus.backend.models.web import ArgusTest, ArgusUserView, User
from argus.backend.plugins.loader import AVAILABLE_PLUGINS
from argus.backend.util.common import chunk, gather_limited, select_rows
from argus.backend.util.config import Config
from argus.backend.service.github_service import GithubService
from argus.backend.service.issue_utils import build_version_map, filter_links_by_version
from argus.backend.service.jira_service import JiraService

LINKED_RUN_COLUMNS = ("id", "build_id", "build_number", "status", "start_time", "scylla_version", "product_version")


class IssueServiceException(Exception):
    pass


class IssueService:

    def __init__(self, dry_run: bool | None = None):
        config = Config.load_yaml_config()
        github_dry_run = dry_run if dry_run is not None else not config.get("GITHUB_ENABLED", True)
        jira_dry_run = dry_run if dry_run is not None else not config.get("JIRA_ENABLED", True)
        self.gh = GithubService(github_dry_run)
        self.jira = JiraService(jira_dry_run)

    def _get_service(self, url):
        return self.gh if "github.com" in url else self.jira

    async def _get_links(self, filter_key: str, filter_id: UUID | str) -> list[IssueLink]:
        if filter_key not in ["release_id", "group_id", "test_id", "run_id", "user_id", "view_id", "event_id"]:
            raise Exception(
                "filter_key can only be one of: \"release_id\", \"group_id\", \"test_id\", \"run_id\", \"user_id\", \"view_id\", \"event_id\""
            )
        if filter_key == "view_id":
            view: ArgusUserView = await ArgusUserView.get(id=filter_id)
            links = []
            for batch in chunk(view.tests):
                links.extend(await IssueLink.find(test_id__in=batch).allow_filtering().all())
            return links
        return await IssueLink.find(**{filter_key: filter_id}).allow_filtering().all()

    async def get(
        self,
        filter_key: str,
        filter_id: UUID | str,
        aggregate_by_issue: bool = False,
        product_version: str | None = None,
        include_no_version: bool = False,
    ):
        filter_id = UUID(filter_id) if isinstance(filter_id, str) else filter_id
        links = await self._get_links(filter_key, filter_id)

        if product_version:
            version_map = await build_version_map(links)
            links = await filter_links_by_version(links, product_version, include_no_version, version_map)

        issues = await self.gh.resolve_issues(links=links, aggregate_by_issue=aggregate_by_issue)
        jira_issues = await self.jira.resolve_issues(links=links, aggregate_by_issue=aggregate_by_issue)
        issues.extend(jira_issues)

        return issues

    async def get_issue_links(self, key: str) -> dict:
        normalized = key.upper()
        trackers = {"jira": self.jira}
        candidates = [
            (subtype, tracker) for subtype, tracker in trackers.items() if tracker.is_issue_key(normalized)
        ]
        if not candidates:
            raise IssueServiceException(f"Not an issue key: {key!r}. Expected a Jira key such as SCT-1234.")
        for subtype, tracker in candidates:
            rows = await tracker.get_issues_by_key(normalized)
            if not rows:
                continue
            batches = await asyncio.gather(*(IssueLink.find(issue_id=row.id).all() for row in rows))
            links = {link.run_id: link for batch in batches for link in batch}
            issue = max(rows, key=lambda row: row.added_on)
            runs = await self._resolve_link_runs(list(links.values()))
            return {
                "issue": {**issue.model_dump(), "subtype": subtype},
                "links": sorted(runs, key=lambda run: run["start_time"], reverse=True),
            }
        return {"issue": None, "links": []}

    async def _resolve_link_runs(self, links: list[IssueLink]) -> list[dict]:
        tests: dict[UUID, ArgusTest] = {}
        for batch in chunk({link.test_id for link in links}):
            tests.update({test.id: test for test in await ArgusTest.find(id__in=batch).all()})
        linked = [
            (link, tests[link.test_id]) for link in links
            if link.test_id in tests and tests[link.test_id].plugin_name in AVAILABLE_PLUGINS
        ]
        rows = await gather_limited(
            select_rows(AVAILABLE_PLUGINS[test.plugin_name].model.find(id=link.run_id), *LINKED_RUN_COLUMNS)
            for link, test in linked
        )
        return [
            {
                "run_id": run["id"],
                "test_id": test.id,
                "test_name": test.name,
                "plugin_name": test.plugin_name,
                "status": run["status"],
                "start_time": run["start_time"],
                "build_id": run["build_id"],
                "build_number": run["build_number"],
                "scylla_version": run["scylla_version"],
                "product_version": run["product_version"],
                "linked_on": link.added_on,
            }
            for (link, test), found in zip(linked, rows)
            for run in found[:1]
        ]

    async def delete(self, issue_id: UUID | str, run_id: UUID | str, user: User):
        issue_id = UUID(issue_id) if isinstance(issue_id, str) else issue_id
        run_id = UUID(run_id) if isinstance(run_id, str) else run_id
        try:
            return await self.gh.delete_issue(issue_id=issue_id, run_id=run_id, user=user)
        except DocumentNotFound:
            return await self.jira.delete_issue(issue_id=issue_id, run_id=run_id, user=user)

    async def submit(self, issue_url: str, test_id: UUID | str, run_id: UUID | str, user: User):
        test_id = UUID(test_id) if isinstance(test_id, str) else test_id
        run_id = UUID(run_id) if isinstance(run_id, str) else run_id
        return await self._get_service(issue_url).submit_issue(
            issue_url=issue_url, test_id=test_id, run_id=run_id, user=user
        )

    async def submit_for_sct_event(
        self, issue_url: str, test_id: UUID | str, event_id: UUID | str, run_id: UUID | str, user: User
    ):
        test_id = UUID(test_id) if isinstance(test_id, str) else test_id
        run_id = UUID(run_id) if isinstance(run_id, str) else run_id
        event_id = UUID(event_id) if isinstance(event_id, str) else event_id
        return await self._get_service(issue_url).submit_issue(
            issue_url=issue_url, test_id=test_id, run_id=run_id, user=user, event_id=event_id
        )
