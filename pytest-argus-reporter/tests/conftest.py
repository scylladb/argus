import re
import os

import pytest
import requests_mock as rm_module


pytest_plugins = "pytester"  # pylint: disable=invalid-name


@pytest.fixture(scope="function")  # executed on every test
def requests_mock():
    """Mock out the requests component of your code with defined responses.
    Mocks out any requests made through the python requests library with useful
    responses for unit testing. See:
    https://requests-mock.readthedocs.io/en/latest/
    """
    kwargs = {"real_http": False}

    with rm_module.Mocker(**kwargs) as mock:
        yield mock


@pytest.fixture(scope="session", autouse=True)
def configure_needed_env_vars():
    original_environment = dict(os.environ)
    os.environ.update({"ARGUS_RUN_ID": "1234", "ARGUS_TEST_TYPE": "dtest"})
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(original_environment)


@pytest.fixture(scope="function", autouse=True)
def configure_argus_mock(requests_mock):  # pylint: disable=redefined-outer-name
    matcher = re.compile(r"https://argus.scylladb.com/api/v1/client/testrun/pytest/result/.*")

    requests_mock.post(matcher, status_code=201)

    requests_mock.get(
        re.compile("https://argus.scylladb.com/api/v1/client/testrun/pytest/.*/stats/duration/avg"),
        response_list=[
            dict(
                json={
                    "response": {"bootstrap_test.py::TestBootstrap::test_start_stop_node": {"duration": {"avg": 60.0}}},
                    "status": "ok",
                },
                status_code=200,
            ),
            dict(
                json={
                    "response": {"bootstrap_test.py::TestBootstrap::test_start_stop_node": {"duration": {"avg": 60.0}}},
                    "status": "ok",
                },
                status_code=200,
            ),
            dict(
                json={
                    "response": {
                        "bootstrap_test.py::TestBootstrap::test_start_stop_node": {"duration": {"avg": 120.0}}
                    },
                    "status": "ok",
                },
                status_code=200,
            ),
            dict(
                json={
                    "response": {"bootstrap_test.py::TestBootstrap::test_start_stop_node": {"duration": {"avg": None}}},
                    "status": "ok",
                },
                status_code=200,
            ),
        ],
    )
