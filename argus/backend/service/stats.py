from collections import defaultdict
from functools import reduce
import logging

from datetime import datetime
from typing import TypedDict
from uuid import UUID

from cassandra.cqlengine.models import Model
from argus.backend.plugins.loader import all_plugin_models
from argus.backend.util.common import chunk, get_build_number
from argus.backend.util.enums import TestStatus, TestInvestigationStatus
from argus.backend.models.web import ArgusGithubIssue, ArgusRelease, ArgusGroup, ArgusTest,\
    ArgusScheduleTest, ArgusTestRunComment, ArgusUserView
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
        TestStatus.TEST_ERROR: 10,
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


class ComparableTestInvestigationStatus:
    PRIORITY_MAP = {
        TestInvestigationStatus.NOT_INVESTIGATED: 10,
        TestInvestigationStatus.IN_PROGRESS: 9,
        TestInvestigationStatus.INVESTIGATED: 8,
        TestInvestigationStatus.IGNORED: 7,
    }

    def __init__(self, status: TestInvestigationStatus):
        self._status = status

    def _get_prio(self):
        return self.PRIORITY_MAP.get(self._status, 0)

    def __eq__(self, __o: object) -> bool:
        if not isinstance(__o, ComparableTestInvestigationStatus):
            return False
        return self._get_prio() == __o._get_prio()

    def __ne__(self, __o: object) -> bool:
        if not isinstance(__o, ComparableTestInvestigationStatus):
            return False
        return not self.__eq__(__o)

    def __lt__(self, __o: object) -> bool:
        if not isinstance(__o, ComparableTestInvestigationStatus):
            return False
        return self._get_prio() < __o._get_prio()

    def __gt__(self, __o: object) -> bool:
        if not isinstance(__o, ComparableTestInvestigationStatus):
            return False
        return self._get_prio() > __o._get_prio()

    def __ge__(self, __o: object) -> bool:
        if not isinstance(__o, ComparableTestInvestigationStatus):
            return False
        return self._get_prio() >= __o._get_prio()

    def __le__(self, __o: object) -> bool:
        if not isinstance(__o, ComparableTestInvestigationStatus):
            return False
        return self._get_prio() <= __o._get_prio()


def generate_field_status_map(
        last_runs: list[TestRunStatRow],
        field_name = "status",
        container_class = TestStatus,
        cmp_class = ComparableTestStatus
    ) -> dict[int, tuple[str, TestRunStatRow]]:

    status_map = {}
    for run in last_runs:
        run_number = get_build_number(run["build_job_url"])
        match status := status_map.get(run_number):
            case str():
                if cmp_class(container_class(status)) < cmp_class(container_class(run[field_name])):
                    status_map[run_number] = run[field_name]
            case _:
                status_map[run_number] = (run[field_name], run)
    return status_map

class ViewStats:
    def __init__(self, release: ArgusUserView) -> None:
        self.release = release
        self.groups: list[GroupStats] = []
        self.status_map = {status: 0 for status in TestStatus}
        self.total_tests = 0
        self.last_status = TestStatus.NOT_PLANNED
        self.last_investigation_status = TestInvestigationStatus.NOT_INVESTIGATED
        self.has_bug_report = False
        self.issues: list[ArgusGithubIssue] = []
        self.comments: list[ArgusTestRunComment] = []
        self.test_schedules: dict[UUID, ArgusScheduleTest] = {}
        self.forced_collection = False
        self.rows = []
        self.releases = {}
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
            "releases": self.releases,
            "groups": converted_groups,
            "total": self.total_tests,
            **self.status_map,
            "disabled": False,
            "perpetual": False,
            "lastStatus": self.last_investigation_status,
            "lastInvestigationStatus": self.last_investigation_status,
            "hasBugReport": self.has_bug_report,
            **aggregated_investigation_status
        }

    def _fetch_multiple_release_queries(self, entity: Model, releases: list[str]):
        result_set = []
        for release_id in releases:
            result_set.extend(entity.filter(release_id=release_id).all())
        return result_set

    def collect(self, rows: list[TestRunStatRow], limited=False, force=False, dict: dict[str, TestRunStatRow] | None = None, tests: list[ArgusTest] = None) -> None:
        self.forced_collection = force
        all_release_ids = list({t.release_id for t in tests})
        if not limited:
            self.test_schedules = reduce(
                lambda acc, row: acc[row["test_id"]].append(row) or acc,
                self._fetch_multiple_release_queries(ArgusScheduleTest, all_release_ids),
                defaultdict(list)
            )

        self.rows = rows
        self.dict = dict
        if not limited or force:
            self.issues = reduce(
                lambda acc, row: acc[row["run_id"]].append(row) or acc,
                self._fetch_multiple_release_queries(ArgusGithubIssue, all_release_ids),
                defaultdict(list)
            )
            self.comments = reduce(
                lambda acc, row: acc[row["test_run_id"]].append(row) or acc,
                self._fetch_multiple_release_queries(ArgusTestRunComment, all_release_ids),
                defaultdict(list)
            )
        self.all_tests = tests
        groups = []
        for slice in chunk(list({t.release_id for t in tests})):
            self.releases.update({str(release.id): release for release in ArgusRelease.filter(id__in=slice).all()})

        for slice in chunk(list({t.group_id for t in tests})):
            groups.extend(ArgusGroup.filter(id__in=slice).all())
        for group in groups:
            if group.enabled:
                stats = GroupStats(group=group, parent_release=self)
                stats.collect(limited=limited)
                self.groups.append(stats)

    def increment_status(self, status=TestStatus.NOT_PLANNED):
        self.total_tests += 1
        self.status_map[TestStatus(status)] += 1
        self.last_status = TestStatus(status)


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
        self.test_schedules: dict[UUID, ArgusScheduleTest] = {}
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

    def collect(self, rows: list[TestRunStatRow], limited=False, force=False, dict: dict | None = None, tests=None) -> None:
        self.forced_collection = force
        if not self.release.enabled and not force:
            return

        if not self.release.perpetual and not limited:
            self.test_schedules = reduce(
                lambda acc, row: acc[row["test_id"]].append(row) or acc,
                ArgusScheduleTest.filter(release_id=self.release.id).all(), 
                defaultdict(list)
            )

        self.rows = rows
        self.dict = dict
        if not limited or force:
            self.issues = reduce(
                lambda acc, row: acc[row["run_id"]].append(row) or acc,
                ArgusGithubIssue.filter(release_id=self.release.id).all(),
                defaultdict(list)
            )
            self.comments = reduce(
                lambda acc, row: acc[row["test_run_id"]].append(row) or acc,
                ArgusTestRunComment.filter(release_id=self.release.id).all(),
                defaultdict(list)
            )
        self.all_tests = ArgusTest.filter(release_id=self.release.id).all() if not tests else tests
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
                    schedules=self.parent_release.test_schedules.get(test.id, [])
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
        self.tracked_run_number = None

    def to_dict(self) -> dict:
        return {
            "test": dict(self.test.items()),
            "status": self.status,
            "investigation_status": self.investigation_status,
            "last_runs": self.last_runs,
            "start_time": self.start_time,
            "hasBugReport": self.has_bug_report,
            "hasComments": self.has_comments,
            "buildNumber": self.tracked_run_number,
            "buildId": self.test.build_system_id,
        }

    def collect(self, limited=False):

        # TODO: Parametrize run limit
        # FIXME: This is only a mitigation, build_number overflows on the build system side.
        if not self.parent_group.parent_release.dict:
            last_runs = [r for r in self.parent_group.parent_release.rows if r["build_id"] == self.test.build_system_id]
        else:
            last_runs = self.parent_group.parent_release.dict.get(self.test.build_system_id, [])
        last_runs: list[TestRunStatRow] = sorted(
            last_runs, reverse=True, key=lambda r: get_build_number(r["build_job_url"]))
        try:
            last_run = last_runs[0]
        except IndexError:
            self.status = TestStatus.NOT_RUN if self.is_scheduled else TestStatus.NOT_PLANNED
            self.parent_group.increment_status(status=self.status)
            return
        status_map = generate_field_status_map(last_runs)

        worst_case = status_map.get(get_build_number(last_run["build_job_url"]))
        self.status = worst_case[0]
        self.investigation_status = worst_case[1]["investigation_status"]
        self.start_time = last_run["start_time"]

        self.parent_group.increment_status(status=self.status)
        if limited and not self.parent_group.parent_release.forced_collection:
            return

        self.last_runs = [
            {
                "id": run["id"],
                "status": run["status"],
                "build_number": get_build_number(run["build_job_url"]),
                "build_job_name": run["build_id"],
                "start_time": run["start_time"],
                "assignee": run["assignee"],
                "issues": [dict(issue.items()) for issue in self.parent_group.parent_release.issues[run["id"]]],
                "comments": [dict(comment.items()) for comment in self.parent_group.parent_release.comments[run["id"]]],
            }
            for run in last_runs
        ]
        try:
            target_run = next(run for run in self.last_runs if run["id"] == worst_case[1]["id"])
        except StopIteration:
            target_run = worst_case[1]
            target_run["issues"] = [dict(issue.items()) for issue in self.parent_group.parent_release.issues[target_run["id"]]]
            target_run["comments"] = [dict(comment.items()) for comment in self.parent_group.parent_release.comments[target_run["id"]]]
        self.has_bug_report = len(target_run["issues"]) > 0
        self.parent_group.parent_release.has_bug_report = self.has_bug_report or self.parent_group.parent_release.has_bug_report
        self.has_comments = len(target_run["comments"]) > 0
        self.last_runs = self.last_runs[:5]
        self.tracked_run_number = target_run.get("build_number", get_build_number(target_run.get("build_job_url")))


class ReleaseStatsCollector:
    def __init__(self, release_name: str, release_version: str | None = None) -> None:
        self.database = ScyllaCluster.get()
        self.session = self.database.get_session()
        self.release = None
        self.release_stats = None
        self.release_rows = []
        self.release_name = release_name
        self.release_version = release_version

    def collect(self, limited=False, force=False, include_no_version=False) -> dict:
        self.release: ArgusRelease = ArgusRelease.get(name=self.release_name)
        all_tests: list[ArgusTest] = list(ArgusTest.filter(release_id=self.release.id).all())
        build_ids = reduce(lambda acc, test: acc[test.plugin_name or "unknown"].append(test.build_system_id) or acc, all_tests, defaultdict(list))
        self.release_rows = [futures for plugin in all_plugin_models()
                             for futures in plugin.get_stats_for_release(release=self.release, build_ids=build_ids.get(plugin._plugin_name, []))]
        self.release_rows = [row for future in self.release_rows for row in future.result()]
        if self.release.dormant and not force:
            return {
                "dormant": True
            }
        if self.release_version:
            if include_no_version:
                expr = lambda row: row["scylla_version"] == self.release_version or not row["scylla_version"] 
            elif self.release_version == "!noVersion":
                expr = lambda row: not row["scylla_version"]
            else:
                expr = lambda row: row["scylla_version"] == self.release_version
        else:
            if include_no_version:
                expr = lambda row: row
            else:
                expr = lambda row: row["scylla_version"]
        self.release_rows = list(filter(expr, self.release_rows))
        self.release_dict = {}
        for row in self.release_rows:
            runs = self.release_dict.get(row["build_id"], [])
            runs.append(row)
            self.release_dict[row["build_id"]] = runs

        self.release_stats = ReleaseStats(release=self.release)
        self.release_stats.collect(rows=self.release_rows, limited=limited, force=force, dict=self.release_dict, tests=all_tests)
        return self.release_stats.to_dict()


class ViewStatsCollector:
    def __init__(self, view_id: UUID, filter: str | None = None) -> None:
        self.database = ScyllaCluster.get()
        self.session = self.database.get_session()
        self.view = None
        self.view_stats = None
        self.view_rows = []
        self.runs_by_build_id = {}
        self.view_id = view_id
        self.filter = filter

    def collect(self, limited=False, force=False, include_no_version=False) -> dict:
        self.view: ArgusUserView = ArgusUserView.get(id=self.view_id)
        all_tests: list[ArgusTest] = []
        for slice in chunk(self.view.tests):
            all_tests.extend(ArgusTest.filter(id__in=slice).all())
        build_ids = reduce(lambda acc, test: acc[test.plugin_name or "unknown"].append(test.build_system_id) or acc, all_tests, defaultdict(list))
        self.view_rows = [futures for plugin in all_plugin_models()
                             for futures in plugin.get_stats_for_release(release=self.view, build_ids=build_ids.get(plugin._plugin_name, []))]
        self.view_rows = [row for future in self.view_rows for row in future.result()]

        if self.filter:
            if include_no_version:
                expr = lambda row: row["scylla_version"] == self.filter or not row["scylla_version"] 
            elif self.filter == "!noVersion":
                expr = lambda row: not row["scylla_version"]
            else:
                expr = lambda row: row["scylla_version"] == self.filter
        else:
            if include_no_version:
                expr = lambda row: row
            else:
                expr = lambda row: row["scylla_version"]
        self.view_rows = list(filter(expr, self.view_rows))
        for row in self.view_rows:
            runs = self.runs_by_build_id.get(row["build_id"], [])
            runs.append(row)
            self.runs_by_build_id[row["build_id"]] = runs

        self.view_stats = ViewStats(release=self.view)
        self.view_stats.collect(rows=self.view_rows, limited=limited, force=force, dict=self.runs_by_build_id, tests=all_tests)
        return self.view_stats.to_dict()
