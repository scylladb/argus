from dataclasses import dataclass
from typing import TypedDict
from uuid import UUID


class RawMatrixTestCase(TypedDict):
    name: str
    status: str
    time: float
    classname: str
    message: str


class RawMatrixTestSuite(TypedDict):
    name: str
    tests: int
    failures: int
    disabled: int
    skipped: int
    passed: int
    errors: int
    time: float
    cases: list[RawMatrixTestCase]


class RawMatrixTestResult(TypedDict):
    name: str
    driver_name: str
    tests: int
    failures: int
    errors: int
    disabled: int
    skipped: int
    passed: int
    time: float
    timestamp: str
    suites: list[RawMatrixTestSuite]


@dataclass(init=True, frozen=True)
class DriverMatrixSubmitResultRequest():
    schema_version: str
    run_id: UUID
    driver_type: str
    driver_name: str
    raw_xml: str


@dataclass(init=True, frozen=True)
class DriverMatrixSubmitFailureRequest():
    schema_version: str
    run_id: UUID
    driver_type: str
    driver_name: str
    failure_reason: str


@dataclass(init=True, frozen=True)
class DriverMatrixSubmitEnvRequest():
    schema_version: str
    run_id: UUID
    raw_env: str
