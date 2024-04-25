from functools import reduce
from datetime import datetime
from typing import TypedDict, Literal
import re
import logging
from uuid import UUID
from pathlib import Path
from pprint import pformat
from glob import glob
from xml.etree import ElementTree

from argus.backend.util.enums import TestStatus
from argus.client.base import ArgusClient
from argus.backend.plugins.driver_matrix_tests.raw_types import RawMatrixTestResult, RawMatrixTestCase


LOGGER = logging.getLogger(__name__)

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


class ArgusDriverMatrixClient(ArgusClient):
    test_type = "driver-matrix-tests"
    schema_version: None = "v1"

    TEST_ADAPTERS = {
        "java": java_driver_matrix_adapter,
        "cpp": cpp_driver_matrix_adapter,
        "python": python_driver_matrix_adapter,
        "gocql": gocql_driver_matrix_adapter,
    }

    def __init__(self, run_id: UUID, auth_token: str, base_url: str, api_version="v1") -> None:
        super().__init__(auth_token, base_url, api_version)
        self.run_id = run_id

    def parse_build_environment(self, env_path: str) -> dict[str, str]:
        with open(Path(env_path), mode="rt", encoding="utf-8") as env_file:
            raw_env = env_file.read()

        result = {}
        for line in raw_env.split("\n"):
            if not line:
                continue
            LOGGER.debug("ENV: %s", line)
            key, val = line.split(": ")
            result[key] = val.strip()

        return result

    def get_test_cases(self, cases: list[ElementTree.Element]) -> list[RawMatrixTestCase]:
        raw_cases = []
        for case in cases:
            children = list(case.findall("./*"))
            if len(children) > 0:
                status = children[0].tag
                message = f"{children[0].attrib.get('message', 'no-message')} ({children[0].attrib.get('type', 'no-type')})"
            else:
                status = "passed"
                message = ""

            raw_cases.append({
                "name": case.attrib["name"],
                "status": status,
                "time": float(case.attrib.get("time", 0.0)),
                "classname": case.attrib.get("classname", ""),
                "message": message,
            })

        return raw_cases

    def get_driver_info(self, xml_name: str, test_type: TestTypeType) -> dict[str, str]:
        if test_type == "cpp":
            filename_re = r"TEST-(?P<driver_name>[\w]*)-(?P<version>[\d\.]*)\.xml"
        else:
            filename_re = r"(?P<name>[\w]*)\.(?P<driver_name>[\w]*)\.(?P<proto>v\d)\.(?P<version>[\d\.]*)\.xml"

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

    def parse_result_xml(self, xml_path: Path, test_type:  TestTypeType) -> RawMatrixTestResult:
        with xml_path.open(mode="rt", encoding="utf-8") as xml_file:
            xml = ElementTree.parse(source=xml_file)
            LOGGER.info("%s", pformat(xml))
        testsuites = xml.getroot()
        adapted_data = self.TEST_ADAPTERS.get(test_type, generic_adapter)(xml)

        driver_info = self.get_driver_info(xml_path.name, test_type)
        test_collection = {
            "timestamp": adapted_data["timestamp"],
            "name": xml_path.stem,
            "driver_name": driver_info.get("driver_name"),
            "tests": 0,
            "failures": 0,
            "errors": 0,
            "disabled": 0,
            "skipped": 0,
            "passed": 0,
            "time": 0.0,
        }
        all_suites = []
        for suite in testsuites.iter("testsuite"):
            raw_suite = {
                "name": suite.attrib["name"],
                "tests": int(suite.attrib.get("tests", 0)),
                "failures": int(suite.attrib.get("failures", 0)),
                "disabled": int(0),
                "passed": self.get_passed_count(suite.attrib),
                "skipped": int(suite.attrib.get("skipped", 0)),
                "errors": int(suite.attrib.get("errors", 0)),
                "time": float(suite.attrib["time"]),
                "cases": self.get_test_cases(list(suite.iter("testcase")))
            }
            all_suites.append(raw_suite)
            test_collection["tests"] += raw_suite["tests"]
            test_collection["failures"] += raw_suite["failures"]
            test_collection["errors"] += raw_suite["errors"]
            test_collection["disabled"] += raw_suite["disabled"]
            test_collection["skipped"] += raw_suite["skipped"]
            test_collection["passed"] += raw_suite["passed"]
            test_collection["time"] += raw_suite["time"]

        return {
            **test_collection,
            "suites": all_suites
        }

    def get_results(self, result_path: str, test_type: TestTypeType) -> list[RawMatrixTestResult]:
        xmls = glob(f"{result_path}/**/*.xml", recursive=True)
        LOGGER.info("Will use following XMLs: %s", pformat(xmls))
        results = []
        for xml in xmls:
            result = self.parse_result_xml(Path(xml), test_type)
            results.append(result)
        return results

    def submit(self, build_id: str, build_url: str, env_path: str, result_path: str, test_type: TestTypeType):
        env = self.parse_build_environment(env_path)
        results = self.get_results(result_path, test_type)

        self.submit_driver_matrix_run(job_name=build_id, job_url=build_url, test_environment=env, results=results)

    def submit_driver_matrix_run(self, job_name: str, job_url: str,
                                 results: list[RawMatrixTestResult], test_environment: dict[str, str]) -> None:
        response = super().submit_run(run_type=self.test_type, run_body={
            "run_id": str(self.run_id),
            "job_name": job_name,
            "job_url": job_url,
            "test_environment": test_environment,
            "matrix_results": results
        })

        self.check_response(response)

    def set_matrix_status(self, status: TestStatus):
        response = super().set_status(run_type=self.test_type, run_id=self.run_id, new_status=status)
        self.check_response(response)
