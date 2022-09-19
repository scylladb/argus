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
    tests_total = columns.Integer()
    failures = columns.Integer()
    disabled = columns.Integer()
    skipped = columns.Integer()
    passed = columns.Integer()
    errors = columns.Integer()
    time = columns.Float()
    cases = columns.List(value_type=columns.UserDefinedType(user_type=TestCase))


class TestCollection(UserType):
    name = columns.Text()
    driver = columns.Text()
    tests_total = columns.Integer()
    failures = columns.Integer()
    disabled = columns.Integer()
    skipped = columns.Integer()
    passed = columns.Integer()
    errors = columns.Integer()
    timestamp = columns.DateTime()
    time = columns.Float()
    suites = columns.List(value_type=columns.UserDefinedType(user_type=TestSuite))


class EnvironmentInfo(UserType):
    key = columns.Text()
    value = columns.Text()
