from typing import TypedDict


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
