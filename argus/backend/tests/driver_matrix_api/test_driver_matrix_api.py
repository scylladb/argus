"""Controller-level tests for the driver-matrix-tests plugin API.

Endpoints exercised (mounted under ``/api/v1/client/driver_matrix``):

- ``POST /result/submit``
- ``POST /result/fail``
- ``POST /env/submit``
- ``GET  /test_report``

The tests follow the ``test_sct_api`` style:

- Use ``flask_client`` to issue real HTTP calls.
- Prefer JSON-only verification via paired GET endpoints.
- Fall back to ORM lookups (``DriverTestRun.get(...)``) only for endpoints
  that do not have a paired read endpoint exposing the persisted state
  (``result/fail`` failure messages, ``env/submit`` environment_info).
- Every test creates its own UUIDs so runs are fully isolated.
"""

import base64
import json
import time
from uuid import uuid4

import pytest

from argus.backend.models.web import ArgusGroup, ArgusRelease, ArgusTest
from argus.backend.plugins.driver_matrix_tests.model import DriverTestRun

CLIENT_PREFIX = "/api/v1/client"
DRIVER_MATRIX_PREFIX = f"{CLIENT_PREFIX}/driver_matrix"
RUN_TYPE = "driver-matrix-tests"


def _build_xml(timestamp: str = "2024-01-01T00:00:00", suite_name: str = "suite-1",
               case_name: str = "case-1") -> str:
    """Build a minimal valid xUnit document accepted by the cpp adapter."""
    return (
        f'<testsuites timestamp="{timestamp}" time="0.10">'
        f'<testsuite name="{suite_name}" tests="1" failures="0" errors="0" '
        f'skipped="0" disabled="0" passed="1" time="0.10">'
        f'<testcase name="{case_name}" classname="cls" time="0.05"/>'
        f'</testsuite>'
        f'</testsuites>'
    )


def _b64(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


@pytest.fixture
def driver_matrix_test(release_manager_service, group: ArgusGroup, release: ArgusRelease) -> ArgusTest:
    """A function-scoped ArgusTest registered against the driver-matrix-tests plugin."""
    name = f"dmt_test_{time.time_ns()}"
    return release_manager_service.create_test(
        name, name, name, name,
        group_id=str(group.id), release_id=str(release.id),
        plugin_name=RUN_TYPE,
    )


@pytest.fixture
def driver_matrix_run_id(flask_client, driver_matrix_test: ArgusTest) -> str:
    """Submit a fresh driver-matrix run via the public submit endpoint and return its id."""
    run_id = str(uuid4())
    payload = {
        "schema_version": "v2",
        "run_id": run_id,
        "job_name": driver_matrix_test.build_system_id,
        "job_url": "http://example.com/job/42/",
    }
    resp = flask_client.post(
        f"{CLIENT_PREFIX}/testrun/{RUN_TYPE}/submit",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.text
    assert resp.json["status"] == "ok"
    return run_id


def test_submit_driver_matrix_result(flask_client, release, driver_matrix_test, driver_matrix_run_id):
    driver_name = "TEST-myDriver-1.0.xml"
    payload = {
        "schema_version": "v8",
        "run_id": driver_matrix_run_id,
        "driver_type": "cpp",
        "driver_name": driver_name,
        "raw_xml": _b64(_build_xml()),
    }
    resp = flask_client.post(
        f"{DRIVER_MATRIX_PREFIX}/result/submit",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.text
    body = resp.json
    assert body["status"] == "ok"
    assert body["response"] is True

    # Verify via the paired test_report read endpoint (JSON-only).
    report = flask_client.get(
        f"{DRIVER_MATRIX_PREFIX}/test_report",
        query_string={"buildId": driver_matrix_test.build_system_id},
    )
    assert report.status_code == 200, report.text
    report_body = report.json
    assert report_body["status"] == "ok"
    response = report_body["response"]
    assert response["release"] == release.name
    assert response["test"] == driver_matrix_test.name
    assert response["build_id"] == driver_matrix_test.build_system_id
    # The cpp parser stores the xml file name as the version label.
    assert "myDriver" in response["versions"]
    assert driver_name in response["versions"]["myDriver"]


def test_submit_driver_matrix_result_idempotent_per_driver_name(
    flask_client, driver_matrix_test, driver_matrix_run_id
):
    """Submitting the same driver_name twice must be a no-op (idempotent)."""
    payload = {
        "schema_version": "v8",
        "run_id": driver_matrix_run_id,
        "driver_type": "cpp",
        "driver_name": "TEST-dupDriver-2.0.xml",
        "raw_xml": _b64(_build_xml()),
    }
    first = flask_client.post(
        f"{DRIVER_MATRIX_PREFIX}/result/submit",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert first.status_code == 200 and first.json["status"] == "ok"

    second = flask_client.post(
        f"{DRIVER_MATRIX_PREFIX}/result/submit",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert second.status_code == 200 and second.json["status"] == "ok"

    report = flask_client.get(
        f"{DRIVER_MATRIX_PREFIX}/test_report",
        query_string={"buildId": driver_matrix_test.build_system_id},
    )
    assert report.status_code == 200
    versions = report.json["response"]["versions"].get("dupDriver", [])
    assert versions.count("TEST-dupDriver-2.0.xml") == 1


def test_submit_driver_matrix_failure(flask_client, driver_matrix_run_id):
    payload = {
        "schema_version": "v8",
        "run_id": driver_matrix_run_id,
        "driver_type": "cpp",
        "driver_name": "broken-driver",
        "failure_reason": "compilation error",
    }
    resp = flask_client.post(
        f"{DRIVER_MATRIX_PREFIX}/result/fail",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.text
    body = resp.json
    assert body["status"] == "ok"
    assert body["response"] is True

    # No JSON read endpoint exposes failure_message; ORM fallback.
    run = DriverTestRun.get(id=driver_matrix_run_id)
    failure = next((c for c in run.test_collection if c.name == "broken-driver"), None)
    assert failure is not None
    assert failure.failure_message == "compilation error"
    assert failure.failures == 1


def test_submit_driver_matrix_env(flask_client, driver_matrix_run_id):
    raw_env = "scylla-version: 6.0.0\nkernel: 5.15.0"
    payload = {
        "schema_version": "v8",
        "run_id": driver_matrix_run_id,
        "raw_env": raw_env,
    }
    resp = flask_client.post(
        f"{DRIVER_MATRIX_PREFIX}/env/submit",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.text
    body = resp.json
    assert body["status"] == "ok"
    assert body["response"] is True

    # No JSON read endpoint exposes environment_info; ORM fallback.
    run = DriverTestRun.get(id=driver_matrix_run_id)
    assert run.scylla_version == "6.0.0"
    env_map = {ei.key: ei.value for ei in run.environment_info}
    assert env_map.get("scylla-version") == "6.0.0"
    assert env_map.get("kernel") == "5.15.0"


def test_get_driver_matrix_test_report_missing_build_id(flask_client):
    resp = flask_client.get(f"{DRIVER_MATRIX_PREFIX}/test_report")
    assert resp.status_code == 200
    body = resp.json
    assert body["status"] == "error"
    assert "No build id provided" in body["response"]["message"]


def test_get_driver_matrix_test_report_unknown_build_id(flask_client):
    resp = flask_client.get(
        f"{DRIVER_MATRIX_PREFIX}/test_report",
        query_string={"buildId": f"unknown-{uuid4()}"},
    )
    assert resp.status_code == 200
    body = resp.json
    assert body["status"] == "error"
    assert "No results for build_id" in body["response"]["message"]
