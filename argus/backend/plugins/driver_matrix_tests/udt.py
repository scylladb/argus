from cassandra.cqlengine.usertype import UserType
from cassandra.cqlengine import columns


class TestCase(UserType):
    name = columns.Text()
    status = columns.Text()
    time = columns.Float()
    classname = columns.Text()
    message = columns.Text()


class TestSuite(UserType):
    name = columns.Text()
    tests_total = columns.Integer(default=lambda: 0)
    failures = columns.Integer(default=lambda: 0)
    disabled = columns.Integer(default=lambda: 0)
    skipped = columns.Integer(default=lambda: 0)
    passed = columns.Integer(default=lambda: 0)
    errors = columns.Integer(default=lambda: 0)
    time = columns.Float()
    cases = columns.List(value_type=columns.UserDefinedType(user_type=TestCase))


class TestCollection(UserType):
    name = columns.Text()
    driver = columns.Text()
    tests_total = columns.Integer(default=lambda: 0)
    failure_message = columns.Text()
    failures = columns.Integer(default=lambda: 0)
    disabled = columns.Integer(default=lambda: 0)
    skipped = columns.Integer(default=lambda: 0)
    passed = columns.Integer(default=lambda: 0)
    errors = columns.Integer(default=lambda: 0)
    timestamp = columns.DateTime()
    time = columns.Float(default=lambda: 0.0)
    suites = columns.List(value_type=columns.UserDefinedType(user_type=TestSuite))


class EnvironmentInfo(UserType):
    key = columns.Text()
    value = columns.Text()
