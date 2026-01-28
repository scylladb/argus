from hashlib import sha1
import re
import logging
from collections import defaultdict
from datetime import UTC, datetime
from functools import reduce
from unittest.mock import MagicMock
from uuid import UUID
from flask import current_app, g
from jira import JIRA

from argus.backend.models.jira import JiraIssue
from argus.backend.models.runtime_store import RuntimeStore
from argus.backend.models.web import ArgusEventTypes, ArgusTest, ArgusUserView
from argus.backend.models.github_issue import IssueLink, IssueLabel
from argus.backend.plugins.core import PluginInfoBase
from argus.backend.plugins.loader import AVAILABLE_PLUGINS
from argus.backend.service.event_service import EventService
from argus.backend.util.common import chunk

LOGGER = logging.getLogger(__name__)


class JiraServiceException(Exception):
    pass


class JiraService:
    LAST_RAN_KEY = "jira_service_last_issue_refresh"

    plugins = AVAILABLE_PLUGINS

    def __init__(self, dry_run = False):
        if dry_run:
            self.jira = None
            return
        config = current_app.config
        self.jira = JIRA(server=config["JIRA_SERVER"], basic_auth=(config["JIRA_EMAIL"], config["JIRA_TOKEN"]))

    def get_plugin(self, plugin_name: str) -> PluginInfoBase | None:
        return self.plugins.get(plugin_name)

    def derive_label_id(self, label: str):
        return int(sha1(label.encode()).hexdigest()[:8], base=16)

    def refresh_stale_issues(self):
        try:
            last_ran = RuntimeStore.get(key=self.LAST_RAN_KEY)
        except RuntimeStore.DoesNotExist:
            last_ran = RuntimeStore()
            last_ran.key = self.LAST_RAN_KEY
            last_ran.value = datetime(year=2025, month=1, day=1, hour=0, minute=0, tzinfo=UTC)
            last_ran.save()

        LOGGER.info("Starting JIRA Issue sync...")
        check_time = datetime.now(tz=UTC)

        all_jira_issues: list[JiraIssue] = list(JiraIssue.all())
        issue_by_key = { i.key: i for i in all_jira_issues }
        dt = last_ran.value.strftime("%Y-%m-%d %H:%M")
        issues = self.jira.search_issues(f"updated >= \"{dt}\"", maxResults=0)
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
                local_issue.labels = [IssueLabel(id=self.derive_label_id(label), name=label, color="000", description="") for label in issue.fields.labels]
                local_issue.save()
                update_count += 1

        LOGGER.info("Finished. Updated %s out of %s issues", update_count, len(all_jira_issues))
        last_ran.value = check_time
        last_ran.save()

    def get_issue(self, issue_url: str) -> tuple[JiraIssue, bool]:
        match = re.match(
            r"http(s)?://scylladb\.atlassian\.net/browse/(?P<key>[A-Z\-\d]+)(/)?",
            issue_url,
        )
        if not match:
            raise JiraServiceException("URL doesn't match ScyllaDB JIRA schema")

        existing = True
        try:
            issue = list(JiraIssue.filter(permalink=issue_url).all())[0]
        except:
            issue = None
            existing = False
        if not issue:
            if not self.jira:
                raise JiraServiceException("Jira remote is disabled.")
            key = match.group("key")
            remote_issue = self.jira.issue(key)

            issue = JiraIssue()
            issue.user_id = g.user.id
            issue.key = remote_issue.key
            issue.state = remote_issue.fields.status.name.lower()
            issue.summary = remote_issue.fields.summary
            issue.project = remote_issue.fields.project.key
            issue.permalink = remote_issue.permalink()
            for label in remote_issue.fields.labels:
                l = IssueLabel()
                l.id = self.derive_label_id(label)
                l.name = label
                l.color = "000"
                l.description = ""
                issue.labels.append(l)

            if assignee := remote_issue.fields.assignee:
                issue.assignees = [assignee.emailAddress]

            issue.save()

        return issue, existing

    def submit_issue(self, issue_url: str, test_id: UUID, run_id: UUID, event_id: UUID | str = None):
        test: ArgusTest = ArgusTest.get(id=test_id)
        plugin = self.get_plugin(plugin_name=test.plugin_name)
        run = plugin.model.get(id=run_id)
        issue, state = self.get_issue(issue_url)

        link = IssueLink()
        link.run_id = run.id
        link.user_id = g.user.id
        link.issue_id = issue.id
        link.release_id = test.release_id
        link.test_id = test.id
        link.group_id = test.group_id
        link.event_id = event_id
        link.type = "jira"

        link.save()

        EventService.create_run_event(
            kind=ArgusEventTypes.TestRunIssueAdded,
            body={
                "message": f"An issue titled \"{{summary}}\" was {'attached' if state else 'added'} by {{username}}",
                "username": g.user.username,
                "url": issue_url,
                "summary": issue.summary,
                "state": issue.state,
            },
            user_id=g.user.id,
            run_id=link.run_id,
            release_id=link.release_id,
            group_id=link.group_id,
            test_id=link.test_id
        )

        response = {
            **dict(list(issue.items())),
            "summary": issue.summary,
            "state": issue.state,
        }

        return response

    def _get_jira_issues_for_view(self, view_id: UUID | str) -> list[IssueLink]:
        view: ArgusUserView = ArgusUserView.get(id=view_id)
        links = []
        for batch in chunk(view.tests):
            links.extend(IssueLink.filter(test_id__in=batch).allow_filtering().all())

        return links

    def get_issues(self, filter_key: str, filter_id: UUID, aggregate_by_issue: bool = False) -> list[dict]:
        if filter_key not in ["release_id", "group_id", "test_id", "run_id", "user_id", "view_id", "event_id"]:
            raise Exception(
                "filter_key can only be one of: \"release_id\", \"group_id\", \"test_id\", \"run_id\", \"user_id\", \"view_id\", \"event_id\""
            )
        if filter_key == "view_id":
            links = list(self._get_jira_issues_for_view(filter_id))
        else:
            links = list(IssueLink.filter(**{filter_key: filter_id}).allow_filtering().all())
        issues = reduce(lambda acc, link: acc[link.issue_id].append(link) or acc, links, defaultdict(list))
        resolved_issues = []
        for batch in chunk(issues.keys()):
            resolved_issues.extend(JiraIssue.filter(id__in=batch).all())
        if aggregate_by_issue:
            response = []
            for issue in resolved_issues:
                issue_dict = dict(issue.items())
                issue_dict["links"] = issues[issue.id]
                issue_dict["subtype"] = "jira"
                response.append(issue_dict)

        else:
            response = [{**dict(issue.items()), **issues[issue.id][0], "subtype": "jira" } for issue in resolved_issues]
        return response

    def delete_issue(self, issue_id: UUID, run_id: UUID) -> dict:
        issue: JiraIssue = JiraIssue.get(id=issue_id)
        links = list(IssueLink.filter(issue_id=issue_id).allow_filtering().all())
        link: IssueLink = IssueLink.get(run_id=run_id, issue_id=issue_id)
        remaining_links = len(list(filter(lambda l: l.run_id != link.run_id and link.issue_id != issue_id, links)))

        EventService.create_run_event(
            kind=ArgusEventTypes.TestRunIssueRemoved,
            body={
                "message": "An issue titled \"{title}\" was removed by {username} from \"{run_id}\"",
                "username": g.user.username,
                "url": issue.permalink,
                "title": issue.summary,
                "state": issue.state,
                "run_id": run_id,
            },
            user_id=g.user.id,
            run_id=link.run_id,
            release_id=link.release_id,
            group_id=link.group_id,
            test_id=link.test_id
        )

        link.delete()
        if remaining_links == 0:
            issue.delete()

        return {
            "deleted": issue_id if remaining_links == 0 else (link.run_id, link.issue_id)
        }
