from datetime import datetime
from typing import Optional

from pydantic import Field
from coodie.usertype import UserType


class TestCase(UserType):
    name: Optional[str] = None
    status: Optional[str] = None
    time: Optional[float] = None
    classname: Optional[str] = None
    message: Optional[str] = None

    class Settings:
        __type_name__ = "test_case"


class TestSuite(UserType):
    name: Optional[str] = None
    tests_total: Optional[int] = 0
    failures: Optional[int] = 0
    disabled: Optional[int] = 0
    skipped: Optional[int] = 0
    passed: Optional[int] = 0
    errors: Optional[int] = 0
    time: Optional[float] = None
    cases: list[TestCase] = Field(default_factory=list)

    class Settings:
        __type_name__ = "test_suite"


class TestCollection(UserType):
    name: Optional[str] = None
    driver: Optional[str] = None
    tests_total: Optional[int] = 0
    failure_message: Optional[str] = None
    failures: Optional[int] = 0
    disabled: Optional[int] = 0
    skipped: Optional[int] = 0
    passed: Optional[int] = 0
    errors: Optional[int] = 0
    timestamp: Optional[datetime] = None
    time: Optional[float] = 0.0
    suites: list[TestSuite] = Field(default_factory=list)

    class Settings:
        __type_name__ = "test_collection"


class EnvironmentInfo(UserType):
    key: Optional[str] = None
    value: Optional[str] = None

    class Settings:
        __type_name__ = "environment_info"
