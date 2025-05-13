import re
import logging
from collections import defaultdict
from datetime import UTC, datetime
from functools import reduce
from uuid import UUID
from flask import current_app, g
from github import Github, Auth

from argus.backend.models.runtime_store import RuntimeStore
from argus.backend.models.web import ArgusEventTypes, ArgusTest, ArgusUserView
from argus.backend.models.github_issue import GithubIssue, IssueAssignee, IssueLink, IssueLabel
from argus.backend.plugins.core import PluginInfoBase
from argus.backend.plugins.loader import AVAILABLE_PLUGINS
from argus.backend.service.event_service import EventService
from argus.backend.util.common import chunk

LOGGER = logging.getLogger(__name__)


class GithubService:
    LAST_RAN_KEY = "github_service_last_issue_refresh"

    plugins = AVAILABLE_PLUGINS

    def __init__(self):
        auth = Auth.Token(token=self.get_installation_token())
        self.gh = Github(auth=auth, per_page=1000)

    def get_plugin(self, plugin_name: str) -> PluginInfoBase | None:
        return self.plugins.get(plugin_name)

    def get_installation_token(self):
        self._refresh_installation_token()
        return current_app.config.get("GITHUB_ACCESS_TOKEN")

    def _refresh_installation_token(self):
        # TODO: To be replaced by JWT refreshing logic once we have Github App in place
        pass

    def refresh_stale_issues(self):
        try:
            last_ran = RuntimeStore.get(key=self.LAST_RAN_KEY)
        except RuntimeStore.DoesNotExist:
            last_ran = RuntimeStore()
            last_ran.key = self.LAST_RAN_KEY
            last_ran.value = datetime(year=2020, month=1, day=1, hour=0, minute=0, tzinfo=UTC)
            last_ran.save()

        LOGGER.info("Starting Github Issue sync...")
        check_time = datetime.now(tz=UTC)

        all_issues: list[GithubIssue] = list(GithubIssue.all())
        issues_by_identifier = {
            f"{issue.owner.lower()}/{issue.repo.lower()}#{issue.number}": issue for issue in all_issues}
        touch_count = 0

        unique_repos = {f"{issue.owner}/{issue.repo}" for issue in all_issues}
        for idx, repo in enumerate(unique_repos):
            LOGGER.info("[%s/%s] Fetching %s...", idx + 1, len(unique_repos), repo)
            repo = self.gh.get_repo(repo)
            issues = repo.get_issues(since=last_ran.value, state="all", direction="desc", sort="created")
            for issue_idx, issue in enumerate(issues):
                match = re.match(
                    r"http(s)?://(www\.)?github\.com/(?P<owner>[\w\d]+)/"
                    r"(?P<repo>[\w\d\-_]+)/(?P<type>issues|pull)/(?P<issue_number>\d+)(/)?",
                    issue.html_url,
                )

                identifier = f"{match.group('owner').lower()}/{match.group('repo').lower()}#{match.group('issue_number')}"
                issue_to_update = issues_by_identifier.get(identifier)
                if not issue_to_update:
                    LOGGER.debug("[%s/%s] No issue found for %s...", issue_idx + 1, "?", identifier)
                    continue
                LOGGER.debug("[%s/%s] Refreshing %s...", issue_idx + 1, "?", identifier)
                issue_to_update.title = issue.title
                issue_to_update.state = issue.state
                issue_to_update.labels = [IssueLabel(
                    id=label.id, name=label.name, color=label.color, description=label.description) for label in issue.labels]
                issue_to_update.assignees = [IssueAssignee(
                    login=assignee.login, html_url=assignee.html_url) for assignee in issue.assignees]
                issue_to_update.save()
                touch_count += 1

        LOGGER.info("Finished. Found %s out of %s issues", touch_count, len(all_issues))
        last_ran.value = check_time
        last_ran.save()

    def submit_github_issue(self, issue_url: str, test_id: UUID, run_id: UUID):
        match = re.match(
            r"http(s)?://(www\.)?github\.com/(?P<owner>[\w\d]+)/"
            r"(?P<repo>[\w\d\-_]+)/(?P<type>issues|pull)/(?P<issue_number>\d+)(/)?",
            issue_url,
        )
        if not match:
            raise Exception("URL doesn't match Github schema")

        test: ArgusTest = ArgusTest.get(id=test_id)
        plugin = self.get_plugin(plugin_name=test.plugin_name)
        run = plugin.model.get(id=run_id)

        existing = True
        try:
            issue = GithubIssue.get(url=issue_url)
        except:
            issue = None
            existing = False
        if not issue:
            repo_id = f"{match.group('owner')}/{match.group('repo')}"
            remote_repo = self.gh.get_repo(repo_id)
            remote_issue = remote_repo.get_issue(int(match.group("issue_number")))

            issue = GithubIssue()
            issue.user_id = g.user.id
            issue.type = match.group("type")
            issue.owner = remote_issue.repository.owner.name
            issue.repo = remote_issue.repository.name
            issue.number = remote_issue.number
            issue.state = remote_issue.state
            issue.title = remote_issue.title
            issue.url = issue_url
            issue.repo_identifier = repo_id
            for label in remote_issue.labels:
                l = IssueLabel()
                l.id = label.id
                l.name = label.name
                l.description = label.description
                l.color = label.color
                issue.labels.append(l)

            for assignee in remote_issue.assignees:
                a = IssueAssignee()
                a.login = assignee.login
                a.html_url = assignee.html_url
                issue.assignees.append(a)

            issue.save()

        link = IssueLink()
        link.run_id = run.id
        link.issue_id = issue.id
        link.release_id = test.release_id
        link.test_id = test.id
        link.group_id = test.group_id

        link.save()

        EventService.create_run_event(
            kind=ArgusEventTypes.TestRunIssueAdded,
            body={
                "message": f"An issue titled \"{{title}}\" was {'attached' if existing else 'added'} by {{username}}",
                "username": g.user.username,
                "url": issue_url,
                "title": issue.title,
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
            "title": issue.title,
            "state": issue.state,
        }

        return response

    def _get_github_issues_for_view(self, view_id: UUID | str) -> list[IssueLink]:
        view: ArgusUserView = ArgusUserView.get(id=view_id)
        links = []
        for batch in chunk(view.tests):
            links.extend(IssueLink.filter(test_id__in=batch).allow_filtering().all())

        return links

    def get_github_issues(self, filter_key: str, filter_id: UUID, aggregate_by_issue: bool = False) -> dict:
        if filter_key not in ["release_id", "group_id", "test_id", "run_id", "user_id", "view_id"]:
            raise Exception(
                "filter_key can only be one of: \"release_id\", \"group_id\", \"test_id\", \"run_id\", \"user_id\", \"view_id\""
            )
        if filter_key == "view_id":
            links = list(self._get_github_issues_for_view(filter_id))
        else:
            links = list(IssueLink.filter(**{filter_key: filter_id}).allow_filtering().all())
        issues = reduce(lambda acc, link: acc[link.issue_id].append(link) or acc, links, defaultdict(list))
        resolved_issues = []
        for batch in chunk(issues.keys()):
            resolved_issues.extend(GithubIssue.filter(id__in=batch).all())
        if aggregate_by_issue:
            response = []
            for issue in resolved_issues:
                issue_dict = dict(issue.items())
                issue_dict["links"] = issues[issue.id]
                response.append(issue_dict)

        else:
            response = [dict(issue.items()) for issue in resolved_issues]
        return response

    def delete_github_issue(self, issue_id: UUID, run_id: UUID) -> dict:
        issue: GithubIssue = GithubIssue.get(id=issue_id)
        links = list(IssueLink.filter(issue_id=issue_id).allow_filtering().all())
        link: IssueLink = IssueLink.get(run_id=run_id, issue_id=issue_id)
        remaining_links = len(list(filter(lambda l: l.run_id != link.run_id and link.issue_id != issue_id, links)))

        EventService.create_run_event(
            kind=ArgusEventTypes.TestRunIssueRemoved,
            body={
                "message": "An issue titled \"{title}\" was removed by {username} from \"{run_id}\"",
                "username": g.user.username,
                "url": issue.url,
                "title": issue.title,
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
