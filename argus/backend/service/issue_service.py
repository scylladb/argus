from uuid import UUID
from argus.backend.models.github_issue import GithubIssue
from argus.backend.service.github_service import GithubService
from argus.backend.service.jira_service import JiraService


class IssueService:

    def __init__(self):
        self.gh = GithubService()
        self.jira = JiraService()

    def _get_service(self, url):
        return self.gh if "github.com" in url else self.jira

    def get(self, filter_key: str, filter_id: UUID | str, aggregate_by_issue: bool = False):
        issues = self.gh.get_issues(filter_key=filter_key, filter_id=filter_id, aggregate_by_issue=aggregate_by_issue)
        jira_issues = self.jira.get_issues(filter_key=filter_key, filter_id=filter_id, aggregate_by_issue=aggregate_by_issue)
        issues.extend(jira_issues)

        return issues

    def delete(self, issue_id: UUID | str, run_id: UUID | str):
        try:
            return self.gh.delete_issue(issue_id=issue_id, run_id=run_id)
        except GithubIssue.DoesNotExist:
            return self.jira.delete_issue(issue_id=issue_id, run_id=run_id)

    def submit(self, issue_url: str, test_id: UUID | str, run_id: UUID | str):
        return self._get_service(issue_url).submit_issue(issue_url=issue_url, test_id=test_id, run_id=run_id)
