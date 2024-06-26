from dataclasses import dataclass
from datetime import datetime
from functools import reduce
import logging
from pprint import pformat
import re
from typing import Literal, TypedDict
from uuid import UUID
from xml.etree import ElementTree
from cassandra.cqlengine import columns
from argus.backend.db import ScyllaCluster
from argus.backend.models.web import ArgusRelease
from argus.backend.plugins.core import PluginModelBase
from argus.backend.plugins.driver_matrix_tests.udt import TestCollection, TestSuite, TestCase, EnvironmentInfo
from argus.backend.plugins.driver_matrix_tests.raw_types import RawMatrixTestResult
from argus.backend.util.enums import TestStatus


LOGGER = logging.getLogger(__name__)

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


@dataclass(init=True, repr=True, frozen=True)
class DriverMatrixRunSubmissionRequestV2():
    schema_version: str
    run_id: str
    job_name: str
    job_url: str


TestTypeType = Literal['java', 'cpp', 'python', 'gocql']


class AdaptedXUnitData(TypedDict):
    timestamp: str


def python_driver_matrix_adapter(xml: ElementTree.ElementTree) -> AdaptedXUnitData:
    testsuites = list(xml.getroot().iter("testsuite"))

    return {
        "timestamp": testsuites[0].attrib.get("timestamp"),
    }


def java_driver_matrix_adapter(xml: ElementTree.ElementTree) -> AdaptedXUnitData:
    testsuites = xml.getroot()
    ts_now = datetime.utcnow().timestamp()
    try:
        time_taken = float(testsuites.attrib.get("time"))
    except ValueError:
        time_taken = 0.0

    timestamp = datetime.utcfromtimestamp(ts_now - time_taken).isoformat()

    return {
        "timestamp": timestamp,
    }


def cpp_driver_matrix_adapter(xml: ElementTree.ElementTree) -> AdaptedXUnitData:
    testsuites = xml.getroot()

    return {
        "timestamp": testsuites.attrib.get("timestamp"),
    }


def gocql_driver_matrix_adapter(xml: ElementTree.ElementTree) -> AdaptedXUnitData:
    testsuites = list(xml.getroot().iter("testsuite"))

    return {
        "timestamp": testsuites[0].attrib.get("timestamp"),
    }


def generic_adapter(xml: ElementTree.ElementTree) -> AdaptedXUnitData:
    return {
        "timestamp": datetime.utcnow().isoformat()
    }

class DriverTestRun(PluginModelBase):
    _plugin_name = "driver-matrix-tests"
    __table_name__ = "driver_test_run"
    scylla_version = columns.Text()
    test_collection = columns.List(value_type=columns.UserDefinedType(user_type=TestCollection))
    environment_info = columns.List(value_type=columns.UserDefinedType(user_type=EnvironmentInfo))

    _no_upstream = ["rust"]

    _TEST_ADAPTERS = {
        "java": java_driver_matrix_adapter,
        "cpp": cpp_driver_matrix_adapter,
        "python": python_driver_matrix_adapter,
        "gocql": gocql_driver_matrix_adapter,
    }


    _artifact_fnames = {
        "cpp": r"TEST-(?P<driver_name>[\w]*)-(?P<version>[\d\.-]*)",
        "gocql": r"xunit\.(?P<driver_name>[\w]*)\.(?P<proto>v\d)\.(?P<version>[v\d\.]*)",
        "python": r"pytest\.(?P<driver_name>[\w]*)\.(?P<proto>v\d)\.(?P<version>[\d\.]*)",
        "java": r"TEST-(?P<version>[\d\.\w-]*)",
        "rust": r"(?P<driver_name>rust)_results_v(?P<version>[\d\w\-.]*)",
    }

    @classmethod
    def _stats_query(cls) -> str:
        return ("SELECT id, test_id, group_id, release_id, status, start_time, build_job_url, build_id, "
                f"assignee, end_time, investigation_status, heartbeat, scylla_version FROM {cls.table_name()} WHERE build_id IN ? PER PARTITION LIMIT 15")

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
        if request_data["schema_version"] == "v2":
            req = DriverMatrixRunSubmissionRequestV2(**request_data)
        else:
            return cls.submit_matrix_run(request_data)

        run = cls()
        run.id = req.run_id
        run.build_id = req.job_name
        run.build_job_url = req.job_url
        run.start_time = datetime.utcnow()
        run.assign_categories()
        try:
            run.assignee = run.get_scheduled_assignee()
        except Exception:  # pylint: disable=broad-except
            run.assignee = None

        run.status = TestStatus.CREATED.value
        run.save()
        return run

    @classmethod
    def submit_driver_result(cls, run_id: UUID, driver_name: str, driver_type: TestTypeType, xml_data: str):
        run: DriverTestRun = cls.get(id=run_id)

        collection = run.parse_result_xml(driver_name, xml_data, driver_type)
        run.test_collection.append(collection)

        if run.status == TestStatus.CREATED:
            run.status = TestStatus.RUNNING.value

        run.save()
        return run


    @classmethod
    def submit_driver_failure(cls, run_id: UUID, driver_name: str, driver_type: TestTypeType, fail_message: str):
        run: DriverTestRun = cls.get(id=run_id)

        collection = TestCollection()
        collection.failures = 1
        collection.failure_message = fail_message
        collection.name = driver_name
        driver_info = run.get_driver_info(driver_name, driver_type)
        collection.driver = driver_info.get("driver_name")
        collection.tests_total = 1
        run.test_collection.append(collection)

        if run.status == TestStatus.CREATED:
            run.status = TestStatus.RUNNING.value

        run.save()
        return run

    @classmethod
    def submit_env_info(cls, run_id: UUID, env_data: str):
        run: DriverTestRun = cls.get(id=run_id)
        env = run.parse_build_environment(env_data)

        for key, value in env.items():
            env_info = EnvironmentInfo()
            env_info.key = key
            env_info.value = value
            run.environment_info.append(env_info)

        run.scylla_version = env.get("scylla-version")

        run.save()
        return run

    def parse_build_environment(self, raw_env: str) -> dict[str, str]:
        result = {}
        for line in raw_env.split("\n"):
            if not line:
                continue
            LOGGER.debug("ENV: %s", line)
            key, val = line.split(": ")
            result[key] = val.strip()

        return result

    def get_test_cases(self, cases: list[ElementTree.Element]) -> list[TestCase]:
        result = []
        for raw_case in cases:
            children = list(raw_case.findall("./*"))
            if len(children) > 0:
                status = children[0].tag
                message = f"{children[0].attrib.get('message', 'no-message')} ({children[0].attrib.get('type', 'no-type')})"
            else:
                status = "passed"
                message = ""

            case = TestCase()
            case.name = raw_case.attrib["name"]
            case.status = status
            case.time = float(raw_case.attrib.get("time", 0.0))
            case.classname = raw_case.attrib.get("classname", "")
            case.message = message
            result.append(case)

        return result

    def get_driver_info(self, xml_name: str, test_type: TestTypeType) -> dict[str, str]:
        if test_type == "cpp":
            filename_re = r"TEST-(?P<driver_name>[\w]*)-(?P<version>[\d\.]*)(\.xml)?"
        else:
            filename_re = r"(?P<name>[\w]*)\.(?P<driver_name>[\w]*)\.(?P<proto>v\d)\.(?P<version>[\d\.]*)(\.xml)?"

        match = re.match(filename_re, xml_name)

        return match.groupdict() if match else {}

    def get_passed_count(self, suite_attribs: dict[str, str]) -> int:
        if (pass_count := suite_attribs.get("passed")):
            return int(pass_count)
        total = int(suite_attribs.get("tests", 0))
        errors = int(suite_attribs.get("errors", 0))
        skipped = int(suite_attribs.get("skipped", 0))
        failures = int(suite_attribs.get("failures", 0))

        return total - errors - skipped - failures

    def parse_result_xml(self, name: str, xml_data: str, test_type: TestTypeType) -> TestCollection:
        xml: ElementTree.ElementTree = ElementTree.ElementTree(ElementTree.fromstring(xml_data))
        LOGGER.debug("%s", pformat(xml))
        testsuites = xml.getroot()
        adapted_data = self._TEST_ADAPTERS.get(test_type, generic_adapter)(xml)

        driver_info = self.get_driver_info(name, test_type)
        test_collection = TestCollection()
        test_collection.timestamp = datetime.fromisoformat(adapted_data["timestamp"][0:-1] if adapted_data["timestamp"][-1] == "Z" else adapted_data["timestamp"])
        test_collection.name = name
        test_collection.driver = driver_info.get("driver_name")
        test_collection.tests_total = 0
        test_collection.failures = 0
        test_collection.errors = 0
        test_collection.disabled = 0
        test_collection.skipped = 0
        test_collection.passed = 0
        test_collection.time = 0.0
        test_collection.suites = []

        for xml_suite in testsuites.iter("testsuite"):
            suite = TestSuite()
            suite.name = xml_suite.attrib["name"]
            suite.tests_total = int(xml_suite.attrib.get("tests", 0))
            suite.failures = int(xml_suite.attrib.get("failures", 0))
            suite.disabled = int(0)
            suite.passed = self.get_passed_count(xml_suite.attrib)
            suite.skipped = int(xml_suite.attrib.get("skipped", 0))
            suite.errors = int(xml_suite.attrib.get("errors", 0))
            suite.time = float(xml_suite.attrib["time"])
            suite.cases = self.get_test_cases(xml_suite.findall("testcase"))

            test_collection.suites.append(suite)
            test_collection.tests_total += suite.tests_total
            test_collection.failures += suite.failures
            test_collection.errors += suite.errors
            test_collection.disabled += suite.disabled
            test_collection.skipped += suite.skipped
            test_collection.passed += suite.passed
            test_collection.time += suite.time

        return test_collection

    @classmethod
    def submit_matrix_run(cls, request_data):
        # Legacy method
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
        for collection in self.test_collection:
            # patch failure
            if collection.failure_message:
                return TestStatus.FAILED

        if len(self.test_collection) < 2:
            return TestStatus.FAILED

        driver_types = {collection.driver for collection in self.test_collection}
        if len(driver_types) <= 1 and not any(driver for driver in self._no_upstream if driver in driver_types):
            return TestStatus.FAILED

        failure_count = reduce(lambda acc, val: acc + (val.failures or 0 + val.errors or 0), self.test_collection, 0)
        if failure_count > 0:
            return TestStatus.FAILED

        return TestStatus.PASSED

    def change_status(self, new_status: TestStatus):
        self.status = new_status

    def get_events(self) -> list:
        return []

    def submit_product_version(self, version: str):
        self.scylla_version = version

    def finish_run(self, payload: dict = None):
        self.end_time = datetime.utcnow()
        self.status = self._determine_run_status().value

    def submit_logs(self, logs: list[dict]):
        pass
