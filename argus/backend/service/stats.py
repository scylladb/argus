import logging

from datetime import datetime
from typing import TypedDict
from uuid import UUID

from argus.backend.plugins.loader import all_plugin_models
from argus.backend.util.common import get_build_number
from argus.backend.util.enums import TestStatus, TestInvestigationStatus
from argus.backend.models.web import ArgusGithubIssue, ArgusRelease, ArgusGroup, ArgusTest,\
    ArgusScheduleTest, ArgusTestRunComment
from argus.backend.db import ScyllaCluster

LOGGER = logging.getLogger(__name__)


class TestRunStatRow(TypedDict):
    build_id: str
    status: TestStatus
    investigation_status: TestInvestigationStatus
    assignee: UUID
    scylla_version: str  # TODO: rework SCT specific field
    start_time: datetime
    end_time: datetime
    heartbeat: int
    id: UUID
    test_id: UUID
    group_id: UUID
    release_id: UUID
    build_job_url: str


class ComparableTestStatus:
    PRIORITY_MAP = {
        TestStatus.FAILED: 10,
        TestStatus.ABORTED: 9,
        TestStatus.RUNNING: 8,
        TestStatus.CREATED: 7,
        TestStatus.PASSED: 6,
    }

    def __init__(self, status: TestStatus):
        self._status = status

    def _get_prio(self):
        return self.PRIORITY_MAP.get(self._status, 0)

    def __eq__(self, __o: object) -> bool:
        if not isinstance(__o, ComparableTestStatus):
            return False
        return self._get_prio() == __o._get_prio()

    def __ne__(self, __o: object) -> bool:
        if not isinstance(__o, ComparableTestStatus):
            return False
        return not self.__eq__(__o)

    def __lt__(self, __o: object) -> bool:
        if not isinstance(__o, ComparableTestStatus):
            return False
        return self._get_prio() < __o._get_prio()

    def __gt__(self, __o: object) -> bool:
        if not isinstance(__o, ComparableTestStatus):
            return False
        return self._get_prio() > __o._get_prio()

    def __ge__(self, __o: object) -> bool:
        if not isinstance(__o, ComparableTestStatus):
            return False
        return self._get_prio() >= __o._get_prio()

    def __le__(self, __o: object) -> bool:
        if not isinstance(__o, ComparableTestStatus):
            return False
        return self._get_prio() <= __o._get_prio()


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
        self.test_schedules: list[ArgusScheduleTest] = []
        self.forced_collection = False
        self.rows = []
        self.all_tests = []

    def to_dict(self) -> dict:
        converted_groups = {str(group.group.id): group.to_dict() for group in self.groups}
        aggregated_investigation_status = {}
        for group in converted_groups.values():
            for investigation_status in TestInvestigationStatus:
                current_status = aggregated_investigation_status.get(investigation_status.value, {})
                result = {
                    status.value: current_status.get(status.value, 0) + group.get(investigation_status.value, {}).get(status, 0)
                    for status in TestStatus
                }
                aggregated_investigation_status[investigation_status.value] = result

        return {
            "release": dict(self.release.items()),
            "groups": converted_groups,
            "total": self.total_tests,
            **self.status_map,
            "disabled": not self.release.enabled,
            "perpetual": self.release.perpetual,
            "lastStatus": self.last_investigation_status,
            "lastInvestigationStatus": self.last_investigation_status,
            "hasBugReport": self.has_bug_report,
            **aggregated_investigation_status
        }

    def collect(self, rows: list[TestRunStatRow], limited=False, force=False) -> None:
        self.forced_collection = force
        if not self.release.enabled and not force:
            return

        if not self.release.perpetual and not limited:
            self.test_schedules = list(ArgusScheduleTest.filter(
                release_id=self.release.id
            ).all())

        self.rows = rows
        if not limited or force:
            self.issues = ArgusGithubIssue.filter(release_id=self.release.id).all()
            self.comments = ArgusTestRunComment.filter(release_id=self.release.id).all()
        self.all_tests = ArgusTest.filter(release_id=self.release.id).all()
        groups: list[ArgusGroup] = ArgusGroup.filter(release_id=self.release.id).all()
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
    def __init__(self, group: ArgusGroup, parent_release: ReleaseStats) -> None:
        self.group = group
        self.parent_release = parent_release
        self.status_map = {status: 0 for status in TestStatus}
        self.total_tests = 0
        self.last_status = TestStatus.NOT_PLANNED
        self.last_investigation_status = TestInvestigationStatus.NOT_INVESTIGATED
        self.disabled = False
        self.tests: list[TestStats] = []

    def to_dict(self) -> dict:
        converted_tests = {str(test.test.id): test.to_dict() for test in self.tests}
        investigation_progress = {}
        for test in converted_tests.values():
            progress_for_status = investigation_progress.get(test["investigation_status"], {})
            status_count = progress_for_status.get(test["status"], 0)
            status_count += 1
            progress_for_status[test["status"]] = status_count
            investigation_progress[test["investigation_status"]] = progress_for_status

        return {
            "group": dict(self.group.items()),
            "total": self.total_tests,
            **self.status_map,
            "lastStatus": self.last_status,
            "lastInvestigationStatus": self.last_investigation_status,
            "disabled": self.disabled,
            "tests": converted_tests,
            **investigation_progress
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
        test: ArgusTest,
        parent_group: GroupStats,
        schedules: list[ArgusScheduleTest] | None = None
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

    def _generate_status_map(self, last_runs: list[TestRunStatRow]) -> dict[int, str]:
        status_map = {}
        for run in last_runs:
            run_number = get_build_number(run["build_job_url"])
            match status := status_map.get(run_number):
                case str():
                    if ComparableTestStatus(TestStatus(status)) < ComparableTestStatus(TestStatus(run["status"])):
                        status_map[run_number] = run["status"]
                case _:
                    status_map[run_number] = run["status"]
        return status_map

    def collect(self, limited=False):

        # TODO: Parametrize run limit
        # FIXME: This is only a mitigation, build_number overflows on the build system side.
        last_runs = [r for r in self.parent_group.parent_release.rows if r["build_id"] == self.test.build_system_id][:15]
        last_runs: list[TestRunStatRow] = sorted(
            last_runs, reverse=True, key=lambda r: get_build_number(r["build_job_url"]))
        try:
            last_run = last_runs[0]
        except IndexError:
            self.status = TestStatus.NOT_RUN if self.is_scheduled else TestStatus.NOT_PLANNED
            self.parent_group.increment_status(status=self.status)
            return
        status_map = self._generate_status_map(last_runs)

        self.status = status_map.get(get_build_number(last_run["build_job_url"]))
        self.investigation_status = TestInvestigationStatus(last_run["investigation_status"])
        self.start_time = last_run["start_time"]

        self.parent_group.increment_status(status=self.status)
        if limited and not self.parent_group.parent_release.forced_collection:
            return

        self.last_runs = [
            {
                "status": run["status"],
                "build_number": get_build_number(run["build_job_url"]),
                "build_job_name": run["build_id"],
                "start_time": run["start_time"],
                "assignee": run["assignee"],
                "issues": [dict(i.items()) for i in self.parent_group.parent_release.issues if i.run_id == run["id"]],
                "comments": [dict(i.items()) for i in self.parent_group.parent_release.comments if i.test_run_id == run["id"]],
            }
            for run in last_runs
        ][:5]
        self.has_bug_report = len(self.last_runs[0]["issues"]) > 0
        self.parent_group.parent_release.has_bug_report = self.has_bug_report or self.parent_group.parent_release.has_bug_report
        self.has_comments = len(self.last_runs[0]["comments"]) > 0


class ReleaseStatsCollector:
    def __init__(self, release_name: str, release_version: str | None = None) -> None:
        self.database = ScyllaCluster.get()
        self.session = self.database.get_session()
        self.release = None
        self.release_stats = None
        self.release_rows = []
        self.release_name = release_name
        self.release_version = release_version

    def collect(self, limited=False, force=False) -> dict:
        self.release: ArgusRelease = ArgusRelease.get(name=self.release_name)
        self.release_rows = [row for plugin in all_plugin_models()
                             for row in plugin.get_stats_for_release(release=self.release)]
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
