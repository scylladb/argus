"""Driver-matrix run lifecycle through the real ArgusDriverMatrixClient.

The junit payload is base64-encoded before it reaches
``submit_driver_result``, matching what ``argus-driver-matrix-client``
does (``cli.py`` encodes the file with ``base64.encodebytes``).
"""

import base64

import pytest

from argus.common.enums import TestStatus

pytestmark = pytest.mark.docker_required

RUN_TYPE = "driver-matrix-tests"


def _build_xml(suite_name: str = "suite-1", case_name: str = "case-1") -> str:
    """Minimal valid xUnit document accepted by the cpp adapter."""
    return (
        f'<testsuites timestamp="2026-08-29T00:00:00" time="0.10">'
        f'<testsuite name="{suite_name}" tests="1" failures="0" errors="0" '
        f'skipped="0" disabled="0" passed="1" time="0.10">'
        f'<testcase name="{case_name}" classname="cls" time="0.05"/>'
        f'</testsuite>'
        f'</testsuites>'
    )


def test_driver_matrix_lifecycle(driver_matrix_client, driver_matrix_test, api_client):
    client = driver_matrix_client
    run_id = client.run_id

    client.submit_driver_matrix_run(
        job_name=driver_matrix_test.build_system_id,
        job_url="http://example.com/job/42/",
    )

    client.submit_driver_result(
        driver_name="TEST-e2eDriver-1.0.xml",
        driver_type="cpp",
        raw_junit_data=base64.encodebytes(_build_xml().encode("utf-8")),
    )

    client.submit_env("scylla-version: 6.0.0\nkernel: 5.15.0")

    client.set_matrix_status(TestStatus.PASSED)
    assert client.get_status() is TestStatus.PASSED

    # Verify persisted state via the generic per-plugin run read endpoint.
    resp = api_client.get(f"/api/v1/run/{RUN_TYPE}/{run_id}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ok"
    run = resp.json()["response"]
    assert run["scylla_version"] == "6.0.0"
    collected = next((c for c in run["test_collection"] if "e2eDriver" in c["name"]), None)
    assert collected is not None
    assert collected["tests_total"] == 1
