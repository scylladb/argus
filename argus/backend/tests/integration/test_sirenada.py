"""Sirenada run submission through the real ArgusSirenadaClient.

The client parses ``junit_results.xml`` + ``test_credentials.json`` from a
results directory and submits everything in one request; both files are
synthesized into ``tmp_path``.
"""

import json
import uuid

import pytest

from argus.client.sirenada.client import ArgusSirenadaClient
from argus.common.enums import TestStatus

pytestmark = pytest.mark.docker_required


def _write_results_dir(tmp_path):
    # A testcase element with no children parses as "passed".
    (tmp_path / "junit_results.xml").write_text(
        '<testsuites><testsuite name="sirenada-suite">'
        '<testcase classname="tests.TestLogin" file="test_login.py" name="test_login_ok" time="1.5"/>'
        '</testsuite></testsuites>'
    )
    (tmp_path / "test_credentials.json").write_text(json.dumps({
        "SIRENADA_TEST_ID": "e2e-sirenada-test",
        "SIRENADA_USER_NAME": "e2e-user",
        "SIRENADA_USER_PASS": "e2e-pass",
        "SIRENADA_OTP_SECRET": "e2e-otp",
        "ClusterID": "e2e-cluster",
        "region": "us-east-1",
    }))


def test_sirenada_submit_run(make_client, sirenada_test, api_client, tmp_path):
    client = make_client(ArgusSirenadaClient)
    run_id = str(uuid.uuid4())
    _write_results_dir(tmp_path)

    env = {
        "SIRENADA_JOB_ID": run_id,
        "SIRENADA_BROWSER": "chrome",
        "SIRENADA_REGION": "us-east-1",
        "SIRENADA_CLUSTER": "serverless",
        "WORKSPACE": str(tmp_path),
        "BUILD_NUMBER": "17",
        "BUILD_URL": "http://example.com/job/17/",
        "JOB_NAME": sirenada_test.build_system_id,
    }
    client.submit_sirenada_run(env=env, test_results_path=tmp_path)

    # Verify persisted state via the generic per-plugin run read endpoint.
    resp = api_client.get(f"/api/v1/run/sirenada/{run_id}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ok"
    run = resp.json()["response"]
    assert run["build_id"] == sirenada_test.build_system_id
    assert run["status"] == TestStatus.PASSED.value
    assert run["browsers"] == ["chrome"]
    assert [case["test_name"] for case in run["results"]] == ["test_login_ok"]
