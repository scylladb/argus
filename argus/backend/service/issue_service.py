from uuid import UUID
from flask import current_app
from coodie.exceptions import DocumentNotFound

from argus.backend.models.github_issue import GithubIssue, IssueLink
from argus.backend.service.github_service import GithubService
from argus.backend.service.issue_utils import build_version_map, filter_links_by_version
from argus.backend.service.jira_service import JiraService


class IssueService:

    def __init__(self, dry_run: bool | None = None):
        github_dry_run = dry_run if dry_run is not None else not current_app.config.get("GITHUB_ENABLED", True)
        jira_dry_run = dry_run if dry_run is not None else not current_app.config.get("JIRA_ENABLED", True)
        self.gh = GithubService(github_dry_run)
        self.jira = JiraService(jira_dry_run)

    def _get_service(self, url):
        return self.gh if "github.com" in url else self.jira

    def _get_links(self, filter_key: str, filter_id: UUID | str) -> list[IssueLink]:
        if filter_key not in ["release_id", "group_id", "test_id", "run_id", "user_id", "view_id", "event_id"]:
            raise Exception(
                "filter_key can only be one of: \"release_id\", \"group_id\", \"test_id\", \"run_id\", \"user_id\", \"view_id\", \"event_id\""
            )
        if filter_key == "view_id":
            gh_links = list(self.gh._get_github_issues_for_view(filter_id))
            jira_links = list(self.jira._get_jira_issues_for_view(filter_id))
            return gh_links + jira_links
        return list(IssueLink.find(**{filter_key: filter_id}).allow_filtering().all())

    def get(
        self,
        filter_key: str,
        filter_id: UUID | str,
        aggregate_by_issue: bool = False,
        product_version: str | None = None,
        include_no_version: bool = False,
    ):
        filter_id = UUID(filter_id) if isinstance(filter_id, str) else filter_id
        links = self._get_links(filter_key, filter_id)

        if product_version:
            version_map = build_version_map(links)
            links = filter_links_by_version(links, product_version, include_no_version, version_map)

        issues = self.gh.resolve_issues(links=links, aggregate_by_issue=aggregate_by_issue)
        jira_issues = self.jira.resolve_issues(links=links, aggregate_by_issue=aggregate_by_issue)
        issues.extend(jira_issues)

        return issues

    def delete(self, issue_id: UUID | str, run_id: UUID | str):
        issue_id = UUID(issue_id) if isinstance(issue_id, str) else issue_id
        run_id = UUID(run_id) if isinstance(run_id, str) else run_id
        try:
            return self.gh.delete_issue(issue_id=issue_id, run_id=run_id)
        except DocumentNotFound:
            return self.jira.delete_issue(issue_id=issue_id, run_id=run_id)

    def submit(self, issue_url: str, test_id: UUID | str, run_id: UUID | str):
        test_id = UUID(test_id) if isinstance(test_id, str) else test_id
        run_id = UUID(run_id) if isinstance(run_id, str) else run_id
        return self._get_service(issue_url).submit_issue(issue_url=issue_url, test_id=test_id, run_id=run_id)

    def submit_for_sct_event(self, issue_url: str, test_id: UUID | str, event_id: UUID | str, run_id: UUID | str):
        test_id = UUID(test_id) if isinstance(test_id, str) else test_id
        run_id = UUID(run_id) if isinstance(run_id, str) else run_id
        event_id = UUID(event_id) if isinstance(event_id, str) else event_id
        return self._get_service(issue_url).submit_issue(issue_url=issue_url, test_id=test_id, run_id=run_id, event_id=event_id)
