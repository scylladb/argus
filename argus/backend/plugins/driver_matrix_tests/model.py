from dataclasses import dataclass
from datetime import datetime
from functools import reduce
import re
from uuid import UUID
from cassandra.cqlengine import columns
from argus.backend.db import ScyllaCluster
from argus.backend.models.web import ArgusRelease
from argus.backend.plugins.core import PluginModelBase
from argus.backend.plugins.driver_matrix_tests.udt import TestCollection, TestSuite, TestCase, EnvironmentInfo
from argus.backend.plugins.driver_matrix_tests.raw_types import RawMatrixTestResult
from argus.backend.util.enums import TestStatus


class DriverMatrixPluginError(Exception):
    pass


@dataclass(init=True, repr=True, frozen=True)
class DriverMatrixRunSubmissionRequest():
    schema_version: str
    run_id: str
    job_name: str
    job_url: str
    test_environment: dict[str, str]
    matrix_results: list[RawMatrixTestResult]


class DriverTestRun(PluginModelBase):
    _plugin_name = "driver-matrix-tests"
    __table_name__ = "driver_test_run"
    scylla_version = columns.Text()
    test_collection = columns.List(value_type=columns.UserDefinedType(user_type=TestCollection))
    environment_info = columns.List(value_type=columns.UserDefinedType(user_type=EnvironmentInfo))


    _artifact_fnames = {
        "cpp": r"TEST-(?P<driver_name>[\w]*)-(?P<version>[\d\.-]*)",
        "gocql": r"xunit\.(?P<driver_name>[\w]*)\.(?P<proto>v\d)\.(?P<version>[v\d\.]*)",
        "python": r"pytest\.(?P<driver_name>[\w]*)\.(?P<proto>v\d)\.(?P<version>[\d\.]*)",
        "java": r"TEST-(?P<version>[\d\.\w-]*)",
    }

    @classmethod
    def _stats_query(cls) -> str:
        return ("SELECT id, test_id, group_id, release_id, status, start_time, build_job_url, build_id, "
                f"assignee, end_time, investigation_status, heartbeat, scylla_version FROM {cls.table_name()} WHERE release_id = ?")

    @classmethod
    def get_distinct_product_versions(cls, release: ArgusRelease) -> list[str]:
        cluster = ScyllaCluster.get()
        statement = cluster.prepare(f"SELECT scylla_version FROM {cls.table_name()} WHERE release_id = ?")
        rows = cluster.session.execute(query=statement, parameters=(release.id,))
        unique_versions = {r["scylla_version"] for r in rows if r["scylla_version"]}

        return sorted(list(unique_versions), reverse=True)

    @classmethod
    def load_test_run(cls, run_id: UUID) -> 'DriverTestRun':
        return cls.get(id=run_id)

    @classmethod
    def parse_driver_name(cls, raw_file_name: str) -> str:
        for test, pattern in cls._artifact_fnames.items():
            match = re.match(pattern, raw_file_name)
            if not match:
                continue
            driver_info = match.groupdict()
            if test == "java":
                version = driver_info["version"]
                return "scylla" if len(version.split(".")) > 3 or "scylla" in version else "datastax"
            else:
                return driver_info["driver_name"]
        return "unknown_driver"


    @classmethod
    def submit_run(cls, request_data: dict) -> 'DriverTestRun':
        req = DriverMatrixRunSubmissionRequest(**request_data)
        run = cls()
        run.id = req.run_id  # pylint: disable=invalid-name
        run.build_id = req.job_name
        run.build_job_url = req.job_url
        run.assign_categories()
        try:
            run.assignee = run.get_scheduled_assignee()
        except Exception:  # pylint: disable=broad-except
            run.assignee = None
        for key, value in req.test_environment.items():
            env_info = EnvironmentInfo()
            env_info.key = key
            env_info.value = value
            run.environment_info.append(env_info)

        run.scylla_version = req.test_environment.get("scylla-version")
        run.test_collection = []

        for result in req.matrix_results:
            collection = TestCollection()
            collection.name = result.get("name")
            collection.driver = cls.parse_driver_name(collection.name)
            collection.tests_total = result.get("tests")
            collection.failures = result.get("failures")
            collection.errors = result.get("errors")
            collection.skipped = result.get("skipped")
            collection.passed = result.get("passed")
            collection.disabled = result.get("disabled")
            collection.time = result.get("time")
            timestamp = result.get("timestamp")
            # TODO: Not needed once python>=3.11
            timestamp = timestamp[0:-1] if timestamp[-1] == "Z" else timestamp
            collection.timestamp = datetime.fromisoformat(timestamp)
            for raw_suite in result.get("suites"):
                suite = TestSuite()
                suite.name = raw_suite.get("name")
                suite.tests_total = raw_suite.get("tests")
                suite.failures = raw_suite.get("failures")
                suite.errors = raw_suite.get("errors")
                suite.skipped = raw_suite.get("skipped")
                suite.passed = raw_suite.get("passed")
                suite.disabled = raw_suite.get("disabled")
                suite.time = raw_suite.get("time")

                for raw_case in raw_suite.get("cases"):
                    case = TestCase()
                    case.name = raw_case.get("name")
                    case.status = raw_case.get("status")
                    case.time = raw_case.get("time")
                    case.classname = raw_case.get("classname")
                    case.message = raw_case.get("message")
                    suite.cases.append(case)

                collection.suites.append(suite)
            run.test_collection.append(collection)

        run.status = run._determine_run_status().value
        run.save()
        return run

    def get_resources(self) -> list:
        return []

    def get_nemeses(self) -> list:
        return []

    def _determine_run_status(self):
        if len(self.test_collection) < 2:
            return TestStatus.FAILED

        driver_types = {collection.driver for collection in self.test_collection}
        if len(driver_types) <= 1:
            return TestStatus.FAILED

        failure_count = reduce(lambda acc, val: acc + (val.failures + val.errors), self.test_collection, 0)
        if failure_count > 0:
            return TestStatus.FAILED

        return TestStatus.PASSED

    def change_status(self, new_status: TestStatus):
        raise DriverMatrixPluginError("This method is obsolete. Status is now determined on submission.")

    def get_events(self) -> list:
        return []

    def submit_product_version(self, version: str):
        self.scylla_version = version

    def finish_run(self, payload: dict = None):
        self.end_time = datetime.utcnow()

    def submit_logs(self, logs: list[dict]):
        pass
