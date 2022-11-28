from functools import reduce
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


class ArgusDriverMatrixClient(ArgusClient):
    test_type = "driver-matrix-tests"
    schema_version: None = "v1"

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
                "time": float(case.attrib["time"]),
                "classname": case.attrib["classname"],
                "message": message,
            })

        return raw_cases

    def get_driver_info(self, xml_name: str) -> dict[str, str]:
        filename_re = r"(?P<name>[\w]*)\.(?P<driver_name>[\w]*)\.(?P<proto>v\d)\.(?P<version>[\d\.]*)\.xml"

        match = re.match(filename_re, xml_name)

        return match.groupdict() if match else {}

    def parse_result_xml(self, xml_path: Path, env: dict[str, str] = None) -> RawMatrixTestResult:
        with xml_path.open(mode="rt", encoding="utf-8") as xml_file:
            xml = ElementTree.parse(source=xml_file)
            LOGGER.info("%s", pformat(xml))
        testsuites = xml.getroot()

        driver_info = self.get_driver_info(xml_path.name)
        test_collection = {
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
        for idx, suite in enumerate(testsuites.iter("testsuite")):
            if idx == 0:
                test_collection["timestamp"] = suite.attrib.get("timestamp")
            raw_suite = {
                "name": suite.attrib["name"],
                "tests": int(suite.attrib["tests"]),
                "failures": int(suite.attrib["failures"]),
                "disabled": int(0),
                "passed": int(suite.attrib["passed"]),
                "skipped": int(suite.attrib["skipped"]),
                "errors": int(suite.attrib["errors"]),
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

    def get_results(self, result_path: str, env: dict[str, str] = None) -> list[RawMatrixTestResult]:
        xmls = glob(f"{result_path}/**/*.xml", recursive=True)
        LOGGER.info("Will use following XMLs: %s", pformat(xmls))
        results = []
        for xml in xmls:
            result = self.parse_result_xml(Path(xml), env=env)
            results.append(result)
        return results

    def submit(self, build_id: str, build_url: str, env_path: str, result_path: str):
        env = self.parse_build_environment(env_path)
        results = self.get_results(result_path, env)

        self.submit_driver_matrix_run(job_name=build_id, job_url=build_url, test_environment=env, results=results)
        failures = reduce(lambda total, coll: coll["failures"] + total, results, 0)
        status = TestStatus.FAILED if failures > 0 else TestStatus.PASSED
        self.set_matrix_status(status)

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
