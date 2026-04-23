from collections import defaultdict
import logging
from uuid import UUID
import json
import re
from argus.backend.db import ScyllaCluster
from argus.backend.plugins.sct.testrun import SCTNemesis, SCTTestRun
from argus.backend.models.github_issue import GithubIssue, IssueLink
from argus.backend.models.jira import JiraIssue
from argus.backend.util.common import chunk
from argus.backend.util.nemesis_map import get_nemesis_name

LOGGER = logging.getLogger(__name__)


class GraphedStatsService:
    def __init__(self) -> None:
        self.cluster = ScyllaCluster.get()

    def get_graphed_stats(self, test_id: UUID, filters=None):
        rows = list(SCTTestRun.filter(test_id=test_id).only([
            "build_id",
            "start_time",
            "end_time",
            "id",
            "investigation_status",
            "packages",
            "status"
        ]).all())

        nemesis_rows = []
        for batch in chunk({r.id for r in rows}):
            # Typically this should result in <100 runs per test, but
            # we batch to make sure we don't exceed max cartesian product
            nemesis_rows.extend(SCTNemesis.filter(run_id__in=batch).all())

        nemesis_data = defaultdict(list)
        for row in nemesis_rows:
            nemesis_data[row.run_id].append(row)

        release_data = {
            "test_runs": [],
            "nemesis_data": []
        }

        filter_patterns = []
        if filters:
            try:
                filter_patterns = [re.compile(pattern) for pattern in json.loads(filters)]
            except (json.JSONDecodeError, re.error) as e:
                LOGGER.error(f"Error parsing filters: {e}")

        for run in [row for row in rows if row["investigation_status"].lower() != "ignored"]:
            # Skip if build_id matches any filter pattern
            if filter_patterns and any(pattern.search(run["build_id"]) for pattern in filter_patterns):
                continue
            try:
                version = [package.version for package in run["packages"] if package.name == "scylla-server"][0]
            except (IndexError, TypeError):
                version = "unknown"

            duration = (run["end_time"] - run["start_time"]).total_seconds() if run["end_time"] else 0
            release_data["test_runs"].append({
                "build_id": run["build_id"],
                "start_time": run["start_time"].timestamp(),
                "duration": duration if duration > 0 else 0,
                "status": run["status"],
                "version": version,
                "run_id": str(run["id"]),
                "investigation_status": run["investigation_status"]
            })

            if nemeses := nemesis_data.get(run["id"]):
                for nemesis in [n for n in nemeses if n.status in ("succeeded", "failed")]:
                    release_data["nemesis_data"].append({
                        "version": version,
                        "name": get_nemesis_name(nemesis.name),
                        "start_time": nemesis.start_time,
                        "duration": nemesis.end_time - nemesis.start_time,
                        "status": nemesis.status,
                        "run_id": str(run["id"]),
                        "stack_trace": nemesis.stack_trace,
                        "build_id": run["build_id"]
                    })

        return release_data

    def get_runs_details(self, run_ids: list[str]):
        """Get detailed information for provided test runs including assignee and attached issues.

        Args:
            run_ids: List of run IDs to fetch detailed information for

        Returns:
            Dictionary mapping run IDs to their detailed information (build_id, start_time, assignee, version, and issues)
        """
        result = {}

        if not run_ids:
            return result

        # Step 1: Get issue links for all run_ids in batches
        all_issue_links = {}
        for batch_run_ids in chunk(run_ids):
            batch_links = IssueLink.objects.filter(run_id__in=batch_run_ids).only(["run_id", "issue_id"]).all()

            for link in batch_links:
                run_id_str = str(link.run_id)
                if run_id_str not in all_issue_links:
                    all_issue_links[run_id_str] = []
                all_issue_links[run_id_str].append(link.issue_id)

        # Step 2: Fetch all unique issue details
        all_issue_ids = set()
        for links in all_issue_links.values():
            all_issue_ids.update(links)

        issues_by_id = {}
        if all_issue_ids:
            for batch_issue_ids in chunk(list(all_issue_ids)):
                for issue in GithubIssue.filter(id__in=batch_issue_ids).only(
                        ["id", "state", "title", "number", "url"]).all():
                    issues_by_id[issue.id] = issue

            missing_ids = [id for id in all_issue_ids if id not in issues_by_id]
            if missing_ids:
                for batch_issue_ids in chunk(missing_ids):
                    for issue in JiraIssue.filter(id__in=batch_issue_ids).only(
                            ["id", "state", "summary", "key", "permalink"]).all():
                        issues_by_id[issue.id] = issue

        # Step 3: Fetch test runs for all provided run_ids
        test_runs = {}
        for run_id in run_ids:
            try:
                test_run = SCTTestRun.filter(id=run_id).only(
                    ["id", "status", "build_id", "start_time", "assignee", "investigation_status", "build_number", "packages", "build_job_url"]).get()
                test_runs[run_id] = test_run
            except Exception as e:
                LOGGER.error(f"Failed to fetch test run {run_id}: {str(e)}")

        # Step 4: Build result with run and issue details
        for run_id in run_ids:
            try:
                test_run = test_runs.get(run_id)
                if not test_run:
                    result[run_id] = {
                        "build_id": None,
                        "start_time": None,
                        "assignee": None,
                        "version": "unknown",
                        "issues": []
                    }
                    continue

                links = all_issue_links.get(run_id, [])
                issues = [issues_by_id[issue_id] for issue_id in links if issue_id in issues_by_id]

                build_number = test_run.build_number

                # Get Scylla version from packages
                for pkg_name in ["scylla-server-upgraded", "scylla-server-upgrade-target", "scylla-server", "scylla-server-target"]:
                    sut_version = next(
                        (f"{pkg.version}-{pkg.date}" for pkg in test_run.packages if pkg.name == pkg_name), None)
                    if sut_version:
                        break
                else:
                    sut_version = "unknown"

                result[run_id] = {
                    "build_id": f"{test_run.build_id}#{build_number}",
                    "status": test_run.status,
                    "start_time": test_run.start_time.isoformat(),
                    "assignee": test_run.assignee,
                    "version": sut_version,
                    "investigation_status": test_run.investigation_status,
                    "issues": [
                        {
                            "subtype": "github",
                            "number": issue.number,
                            "state": issue.state,
                            "title": issue.title,
                            "url": issue.url,
                        } if isinstance(issue, GithubIssue) else {
                            "subtype": "jira",
                            "key": issue.key,
                            "state": issue.state,
                            "summary": issue.summary,
                            "permalink": issue.permalink,
                        }
                        for issue in issues
                    ],
                }
            except Exception as e:
                LOGGER.error(f"Error fetching details for run {run_id}: {str(e)}")
                result[run_id] = {
                    "build_id": None,
                    "start_time": None,
                    "assignee": None,
                    "version": "unknown",
                    "issues": []
                }

        return result
