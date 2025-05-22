from datetime import datetime, UTC

import pytest

from argus.backend.service.views_widgets.pytest import PytestViewService
from argus.backend.service.client_service import ClientService
from argus.backend.service.testrun import TestRunService


def test_valid_results(client_service: ClientService, pv_service: PytestViewService):

    sample_data = {
        "name": "testSuite::test_sample",
        "timestamp": 1753687331.758162,
        "session_timestamp": 1753687331.758162,
        "test_type": "dtest",
        "run_id": "879b516b-6e93-4c4c-9c86-dd0f2fda5c66",
        "status": "passed",
        "duration": 1.27434,
        "markers": ["dtest_full", "dtest"],
        "user_fields": {
            "SCYLLA_MODE": "release",
            "SCYLLA_VERSION": "2023.1",
        }
    }

    result = client_service.submit_pytest_result(sample_data)

    assert sample_data["name"] == result["name"]
    assert datetime.fromtimestamp(sample_data["timestamp"], tz=UTC) == result["id"]

    fields = pv_service.get_user_fields_for_result(result["name"], result["id"].isoformat())

    assert fields == sample_data["user_fields"]


def test_avg_duration(testrun_service: TestRunService, client_service: ClientService):

    sample_data = {
        "name": "testSuite::test_sample_duration_avg",
        "timestamp": 1753687331.758162,
        "session_timestamp": 1753687331.758162,
        "test_type": "dtest",
        "run_id": "879b516b-6e93-4c4c-9c86-dd0f2fda5c66",
        "status": "passed",
        "duration": 1.27434,
        "markers": ["dtest_full", "dtest"],
        "user_fields": {
            "SCYLLA_MODE": "release",
            "SCYLLA_VERSION": "2023.1",
        }
    }

    durations = [3, 5, 7]
    sample_tests = [{**sample_data, "timestamp": 1753687331.758162 + (i*10), "duration": durations[i]} for i in  range(3)]

    for sample in sample_tests:
        client_service.submit_pytest_result(sample)

    result = testrun_service.get_pytest_test_field_stats(sample_data["name"], "duration", "avg", {})

    assert sum(durations)/len(durations) == result[sample_data["name"]]["duration"]["avg"]


def test_avg_duration_with_status_query(testrun_service: TestRunService, client_service: ClientService):

    sample_data = {
        "name": "testSuite::test_sample_duration_avg",
        "timestamp": 1753687331.758162,
        "session_timestamp": 1753687331.758162,
        "test_type": "dtest",
        "run_id": "879b516b-6e93-4c4c-9c86-dd0f2fda5c66",
        "status": "passed",
        "duration": 1.27434,
        "markers": ["dtest_full", "dtest"],
        "user_fields": {
            "SCYLLA_MODE": "release",
            "SCYLLA_VERSION": "2023.1",
        }
    }

    durations = [3, 5, 7]
    sample_tests = [{**sample_data, "timestamp": 1753687331.758162 + (i*10), "duration": durations[i]} for i in  range(3)]

    for sample in sample_tests:
        client_service.submit_pytest_result(sample)

    result = testrun_service.get_pytest_test_field_stats(sample_data["name"], "duration", "avg", {})

    assert sum(durations)/len(durations) == result[sample_data["name"]]["duration"]["avg"]

    result = testrun_service.get_pytest_test_field_stats(sample_data["name"], "duration", "avg", {"status": "passed"})
    assert sum(durations)/len(durations) == result[sample_data["name"]]["duration"]["avg"]


def test_avg_duration_with_time_query(testrun_service: TestRunService, client_service: ClientService):

    sample_data = {
        "name": "testSuite::test_sample_duration_avg",
        "timestamp": 1753687331.758162,
        "session_timestamp": 1753687331.758162,
        "test_type": "dtest",
        "run_id": "879b516b-6e93-4c4c-9c86-dd0f2fda5c66",
        "status": "passed",
        "duration": 1.27434,
        "markers": ["dtest_full", "dtest"],
        "user_fields": {
            "SCYLLA_MODE": "release",
            "SCYLLA_VERSION": "2023.1",
        }
    }

    since = 1753680000
    durations = [3, 5, 7]
    sample_tests = [{**sample_data, "timestamp": 1753687331.758162 + (i*10), "duration": durations[i]} for i in  range(3)]

    for sample in sample_tests:
        client_service.submit_pytest_result(sample)

    result = testrun_service.get_pytest_test_field_stats(sample_data["name"], "duration", "avg", {})

    assert sum(durations)/len(durations) == result[sample_data["name"]]["duration"]["avg"]

    result = testrun_service.get_pytest_test_field_stats(sample_data["name"], "duration", "avg", {"since": since})
    assert sum(durations)/len(durations) == result[sample_data["name"]]["duration"]["avg"]


def test_avg_duration_with_status_and_time_query(testrun_service: TestRunService, client_service: ClientService):

    sample_data = {
        "name": "testSuite::test_sample_duration_avg",
        "timestamp": 1753687331.758162,
        "session_timestamp": 1753687331.758162,
        "test_type": "dtest",
        "run_id": "879b516b-6e93-4c4c-9c86-dd0f2fda5c66",
        "status": "passed",
        "duration": 1.27434,
        "markers": ["dtest_full", "dtest"],
        "user_fields": {
            "SCYLLA_MODE": "release",
            "SCYLLA_VERSION": "2023.1",
        }
    }

    durations = [3, 5, 7]
    since = 1753680000
    sample_tests = [{**sample_data, "timestamp": 1753687331.758162 + (i*10), "duration": durations[i]} for i in  range(3)]

    for sample in sample_tests:
        client_service.submit_pytest_result(sample)

    result = testrun_service.get_pytest_test_field_stats(sample_data["name"], "duration", "avg", {})

    assert sum(durations)/len(durations) == result[sample_data["name"]]["duration"]["avg"]

    result = testrun_service.get_pytest_test_field_stats(sample_data["name"], "duration", "avg", {"status": "passed", "since": since})
    assert sum(durations)/len(durations) == result[sample_data["name"]]["duration"]["avg"]
