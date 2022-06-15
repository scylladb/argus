import logging

from datetime import datetime
from argus.db.db_types import TestStatus, TestInvestigationStatus
from argus.db.testrun import TestRun
from argus.db.models import ArgusGithubIssue, ArgusRelease, ArgusReleaseGroup, ArgusReleaseGroupTest, ArgusReleaseScheduleTest, ArgusTestRunComment
from argus.backend.db import ScyllaCluster

LOGGER = logging.getLogger(__name__)


class ReleaseStats:
    def __init__(self, release: ArgusRelease) -> None:
        self.release = release
        self.groups: list[GroupStats] = []
        self.status_map = {status: 0 for status in TestStatus}
        self.total_tests = 0
        self.last_status = TestStatus.NOT_PLANNED
        self.last_investigation_status = TestInvestigationStatus.NOT_INVESTIGATED
        self.has_bug_report = False
        self.issues: list[ArgusGithubIssue] = []
        self.comments: list[ArgusTestRunComment] = []
        self.test_schedules: list[ArgusReleaseScheduleTest] = []
        self.forced_collection = False

    def to_dict(self) -> dict:
        return {
            "release": dict(self.release.items()),
            "groups": {str(group.group.id): group.to_dict() for group in self.groups},
            "total": self.total_tests,
            **self.status_map,
            "disabled": not self.release.enabled,
            "perpetual": self.release.perpetual,
            "lastStatus": self.last_investigation_status,
            "lastInvestigationStatus": self.last_investigation_status,
            "hasBugReport": self.has_bug_report
        }

    def collect(self, rows: list[dict], limited=False, force=False) -> None:
        self.forced_collection = force
        if not self.release.enabled and not force:
            return

        if not self.release.perpetual and not limited:
            self.test_schedules = list(ArgusReleaseScheduleTest.filter(
                release_id=self.release.id
            ).all())

        self.rows = rows
        if not limited or force:
            self.issues = ArgusGithubIssue.filter(release_id=self.release.id).all()
            self.comments = ArgusTestRunComment.filter(release_id=self.release.id).all()
        self.all_tests = ArgusReleaseGroupTest.filter(release_id=self.release.id).all()
        groups: list[ArgusReleaseGroup] = ArgusReleaseGroup.filter(release_id=self.release.id).all()
        for group in groups:
            if group.enabled:
                stats = GroupStats(group=group, parent_release=self)
                stats.collect(limited=limited)
                self.groups.append(stats)

    def increment_status(self, status=TestStatus.NOT_PLANNED):
        self.total_tests += 1
        self.status_map[TestStatus(status)] += 1
        self.last_status = TestStatus(status)


class GroupStats:
    def __init__(self, group: ArgusReleaseGroup, parent_release: ReleaseStats) -> None:
        self.group = group
        self.parent_release = parent_release
        self.status_map = {status: 0 for status in TestStatus}
        self.total_tests = 0
        self.last_status = TestStatus.NOT_PLANNED
        self.last_investigation_status = TestInvestigationStatus.NOT_INVESTIGATED
        self.disabled = False
        self.tests: list[TestStats] = []

    def to_dict(self) -> dict:
        return {
            "group": dict(self.group.items()),
            "total": self.total_tests,
            **self.status_map,
            "lastStatus": self.last_status,
            "lastInvestigationStatus": self.last_investigation_status,
            "disabled": self.disabled,
            "tests": {str(test.test.id): test.to_dict() for test in self.tests}
        }

    def collect(self, limited=False):
        tests = [test for test in self.parent_release.all_tests if test.group_id == self.group.id]

        for test in tests:
            if test.enabled:
                stats = TestStats(
                    test=test,
                    parent_group=self,
                    schedules=tuple(
                        schedule for schedule in self.parent_release.test_schedules if schedule.test_id == test.id)
                )
                stats.collect(limited=limited)
                self.tests.append(stats)

    def increment_status(self, status=TestStatus.NOT_PLANNED):
        self.status_map[TestStatus(status)] += 1
        self.total_tests += 1
        self.last_status = TestStatus(status)
        self.parent_release.increment_status(status)


class TestStats:
    def __init__(
        self,
        test: ArgusReleaseGroupTest,
        parent_group: GroupStats,
        schedules: list[ArgusReleaseScheduleTest] | None = None
    ) -> None:
        self.test = test
        self.parent_group = parent_group
        self.start_time = datetime.fromtimestamp(0)
        self.status = TestStatus.NOT_PLANNED
        self.investigation_status = TestInvestigationStatus.NOT_INVESTIGATED
        self.last_runs: list[dict] = []
        self.has_bug_report = False
        self.has_comments = False
        self.schedules = schedules if schedules else tuple()
        self.is_scheduled = len(self.schedules) > 0

    def to_dict(self) -> dict:
        return {
            "test": dict(self.test.items()),
            "status": self.status,
            "investigation_status": self.investigation_status,
            "last_runs": self.last_runs,
            "start_time": self.start_time,
            "hasBugReport": self.has_bug_report,
            "hasComments": self.has_comments
        }

    def collect(self, limited=False):

        last_runs = filter(lambda r: r["build_id"] == self.test.build_system_id, self.parent_group.parent_release.rows)
        try:
            last_run = next(last_runs)
        except StopIteration:
            self.status = TestStatus.NOT_RUN if self.is_scheduled else TestStatus.NOT_PLANNED
            self.parent_group.increment_status(status=self.status)
            return

        self.status = TestStatus(last_run["status"])
        self.investigation_status = TestInvestigationStatus(last_run["investigation_status"])
        self.start_time = last_run["start_time"]

        self.parent_group.increment_status(status=last_run["status"])
        if limited and not self.parent_group.parent_release.forced_collection:
            return

        self.last_runs = [
            {
                "status": run["status"],
                "build_number": run["build_job_url"].rstrip("/").split("/")[-1],
                "build_job_name": run["build_id"],
                "start_time": run["start_time"],
                "assignee": run["assignee"],
                "issues": [dict(i.items()) for i in self.parent_group.parent_release.issues if i.run_id == run["id"]],
                "comments": [dict(i.items()) for i in self.parent_group.parent_release.comments if i.test_run_id == run["id"]],
            }
            for run in [last_run, *last_runs]
        ][:4]
        self.has_bug_report = len(self.last_runs[0]["issues"]) > 0
        self.parent_group.parent_release.has_bug_report = self.has_bug_report or self.parent_group.parent_release.has_bug_report
        self.has_comments = len(self.last_runs[0]["comments"]) > 0


class ReleaseStatsCollector:
    def __init__(self, release_name: str, release_version: str | None = None) -> None:
        self.database = ScyllaCluster.get()
        self.session = self.database.get_session()
        self.run_by_release_stats_statement = self.database.prepare(
            "SELECT id, test_id, group_id, release_id, status, start_time, build_job_url, build_id, assignee, "
            f"end_time, investigation_status, heartbeat, scylla_version FROM {TestRun.table_name()} WHERE release_id = ?"
        )
        self.release_name = release_name
        self.release_version = release_version

    def collect(self, limited=False, force=False) -> dict:
        self.release: ArgusRelease = ArgusRelease.get(name=self.release_name)
        self.release_rows = self.session.execute(
            self.run_by_release_stats_statement, parameters=(self.release.id,)).all()
        if self.release.dormant and not force:
            return {
                "dormant": True
            }

        if self.release_version:
            self.release_rows = list(
                filter(lambda row: row["scylla_version"] == self.release_version, self.release_rows))

        self.release_stats = ReleaseStats(release=self.release)
        self.release_stats.collect(rows=self.release_rows, limited=limited, force=force)
        return self.release_stats.to_dict()
