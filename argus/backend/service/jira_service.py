import asyncio
from hashlib import sha1
import re
import logging
from collections import defaultdict
from datetime import UTC, datetime
from functools import cached_property, reduce
from unittest.mock import MagicMock
from urllib.parse import urlparse
from uuid import UUID
from jira import JIRA

from argus.backend.models.jira import JiraIssue
from coodie.exceptions import DocumentNotFound

from argus.backend.models.runtime_store import RuntimeStore
from argus.backend.models.web import ArgusEventTypes, ArgusTest, User, invalidate_release_snapshots
from argus.backend.models.github_issue import IssueLink, IssueLabel
from argus.backend.plugins.core import PluginInfoBase
from argus.backend.plugins.loader import AVAILABLE_PLUGINS
from argus.backend.service.event_service import EventService
from argus.backend.util.common import chunk
from argus.backend.util.config import Config

LOGGER = logging.getLogger(__name__)


class JiraServiceException(Exception):
    pass


class JiraService:
    LAST_RAN_KEY = "jira_service_last_issue_refresh"

    plugins = AVAILABLE_PLUGINS

    def __init__(self, dry_run = False):
        if dry_run:
            self.jira = None

    @cached_property
    def jira(self) -> JIRA:
        config = Config.load_yaml_config()
        return JIRA(server=config["JIRA_SERVER"], basic_auth=(config["JIRA_EMAIL"], config["JIRA_TOKEN"]))

    def get_plugin(self, plugin_name: str) -> PluginInfoBase | None:
        return self.plugins.get(plugin_name)

    async def _client(self) -> JIRA | None:
        return await asyncio.to_thread(lambda: self.jira)

    def derive_label_id(self, label: str):
        return int(sha1(label.encode()).hexdigest()[:8], base=16)

    async def refresh_stale_issues(self):
        try:
            last_ran = await RuntimeStore.get(key=self.LAST_RAN_KEY)
        except DocumentNotFound:
            last_ran = RuntimeStore(key=self.LAST_RAN_KEY)
            last_ran.value = datetime(year=2025, month=1, day=1, hour=0, minute=0, tzinfo=UTC)
            await last_ran.save()

        LOGGER.info("Starting JIRA Issue sync...")
        check_time = datetime.now(tz=UTC)

        all_jira_issues: list[JiraIssue] = await JiraIssue.find().all()
        issue_by_key = { i.key: i for i in all_jira_issues }
        dt = last_ran.value.strftime("%Y-%m-%d %H:%M")
        jira = await self._client()
        issues = await asyncio.to_thread(jira.search_issues, f"updated >= \"{dt}\"", maxResults=0)
        update_count = 0
        LOGGER.info("Checking %s issues...", len(issues))
        for issue in issues:
            if local_issue := issue_by_key.get(issue.key):
                LOGGER.debug("Updating %s...", issue.key)
                local_issue.summary = issue.fields.summary
                local_issue.state = issue.fields.status.name.lower()
                if assignee := issue.fields.assignee:
                    local_issue.assignees = [assignee.emailAddress]
                else:
                    local_issue.assignees = []
                local_issue.labels = [
                    IssueLabel(id=self.derive_label_id(label), name=label, color="000", description="")
                    for label in issue.fields.labels
                ]
                await local_issue.save()
                update_count += 1

        LOGGER.info("Finished. Updated %s out of %s issues", update_count, len(all_jira_issues))
        last_ran.value = check_time
        await last_ran.save()

    async def get_issue(self, issue_url: str, user: User) -> tuple[JiraIssue, bool]:
        server_host = re.escape(urlparse(Config.load_yaml_config()["JIRA_SERVER"]).hostname)
        match = re.match(
            rf"http(s)?://{server_host}/browse/(?P<key>[A-Z]+-\d+)(/)?",
            issue_url,
        )
        if not match:
            raise JiraServiceException("URL doesn't match configured Jira server")

        rows = await JiraIssue.find(permalink=issue_url).all()
        issue = rows[0] if rows else None
        existing = issue is not None
        if not issue:
            jira = await self._client()
            if not jira:
                raise JiraServiceException("Jira remote is disabled.")
            key = match.group("key")
            remote_issue = await asyncio.to_thread(jira.issue, key)

            issue = JiraIssue.model_construct()
            issue.user_id = user.id
            issue.key = remote_issue.key
            issue.state = remote_issue.fields.status.name.lower()
            issue.summary = remote_issue.fields.summary
            issue.project = remote_issue.fields.project.key
            issue.permalink = remote_issue.permalink()
            for label in remote_issue.fields.labels:
                l = IssueLabel.model_construct()
                l.id = self.derive_label_id(label)
                l.name = label
                l.color = "000"
                l.description = ""
                issue.labels.append(l)

            if assignee := remote_issue.fields.assignee:
                issue.assignees = [assignee.emailAddress]

            await issue.save()

        return issue, existing

    async def submit_issue(self, issue_url: str, test_id: UUID, run_id: UUID, user: User, event_id: UUID | str = None):
        test: ArgusTest = await ArgusTest.get(id=test_id)
        plugin = self.get_plugin(plugin_name=test.plugin_name)
        run = await plugin.model.get(id=run_id)
        issue, state = await self.get_issue(issue_url, user)

        link = IssueLink.model_construct()
        link.run_id = run.id
        link.user_id = user.id
        link.issue_id = issue.id
        link.release_id = test.release_id
        link.test_id = test.id
        link.group_id = test.group_id
        link.event_id = event_id
        link.type = "jira"

        await link.save()

        await EventService.create_run_event(
            kind=ArgusEventTypes.TestRunIssueAdded,
            body={
                "message": f"An issue titled \"{{summary}}\" was {'attached' if state else 'added'} by {{username}}",
                "username": user.username,
                "url": issue_url,
                "summary": issue.summary,
                "state": issue.state,
            },
            user_id=user.id,
            run_id=link.run_id,
            release_id=link.release_id,
            group_id=link.group_id,
            test_id=link.test_id
        )

        await invalidate_release_snapshots(test.release_id)
        response = {
            **issue.model_dump(),
            "summary": issue.summary,
            "state": issue.state,
        }

        return response

    async def resolve_issues(self, links: list[IssueLink], aggregate_by_issue: bool = False) -> list[dict]:
        """Resolve JiraIssue records from pre-filtered links and build response dicts."""
        issues = reduce(lambda acc, link: acc[link.issue_id].append(link) or acc, links, defaultdict(list))
        resolved_issues = []
        for batch in chunk(issues.keys()):
            resolved_issues.extend(await JiraIssue.find(id__in=batch).all())
        if aggregate_by_issue:
            response = []
            for issue in resolved_issues:
                issue_dict = issue.model_dump()
                issue_dict["links"] = issues[issue.id]
                issue_dict["subtype"] = "jira"
                response.append(issue_dict)

        else:
            response = [{**issue.model_dump(), **issues[issue.id][0].model_dump(), "subtype": "jira" } for issue in resolved_issues]
        return response

    async def delete_issue(self, issue_id: UUID, run_id: UUID, user: User) -> dict:
        issue: JiraIssue = await JiraIssue.get(id=issue_id)
        links = await IssueLink.find(issue_id=issue_id).allow_filtering().all()
        link: IssueLink = await IssueLink.get(run_id=run_id, issue_id=issue_id)
        remaining_links = len(list(filter(lambda l: l.run_id != link.run_id and link.issue_id != issue_id, links)))

        await EventService.create_run_event(
            kind=ArgusEventTypes.TestRunIssueRemoved,
            body={
                "message": "An issue titled \"{title}\" was removed by {username} from \"{run_id}\"",
                "username": user.username,
                "url": issue.permalink,
                "title": issue.summary,
                "state": issue.state,
                "run_id": str(run_id),
            },
            user_id=user.id,
            run_id=link.run_id,
            release_id=link.release_id,
            group_id=link.group_id,
            test_id=link.test_id
        )

        await link.delete()
        if remaining_links == 0:
            await issue.delete()

        await invalidate_release_snapshots(link.release_id)
        return {
            "deleted": issue_id if remaining_links == 0 else (link.run_id, link.issue_id)
        }
