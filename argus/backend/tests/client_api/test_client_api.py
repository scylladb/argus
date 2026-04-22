"""Controller-level integration tests for argus/backend/controller/client_api.py.

Covers endpoints not already exercised through other test modules:

- GET  /api/v1/client/testrun/<run_id>/info                                  (get_run_info)
- POST /api/v1/client/testrun/<run_type>/submit                              (submit_run)
- GET  /api/v1/client/testrun/<run_type>/<run_id>/get                        (get_run)
- POST /api/v1/client/testrun/<run_type>/<run_id>/heartbeat                  (run_heartbeat)
- GET  /api/v1/client/testrun/<run_type>/<run_id>/get_status                 (run_get_status)
- POST /api/v1/client/testrun/<run_type>/<run_id>/set_status                 (run_set_status)
- POST /api/v1/client/testrun/<run_type>/<run_id>/update_product_version    (run_update_product_version)
- POST /api/v1/client/testrun/<run_type>/<run_id>/logs/submit                (run_submit_logs)
- POST /api/v1/client/testrun/<run_type>/<run_id>/finalize                   (run_finalize)
- POST /api/v1/client/testrun/pytest/result/submit                           (submit_pytest_result)
- GET  /api/v1/client/testrun/pytest/<test_name>/stats/<field>/<aggr>        (get_pytest_test_field_stats)
- POST /api/v1/client/testrun/report                                         (render_email_report)

The send_email path (/testrun/report/email) and config endpoints are exercised in
argus/backend/tests/email_service/ and argus/backend/tests/client_service/ respectively.
SSH proxy endpoints under /ssh/ live in argus/backend/tests/tunnel/.
"""

import json
import time
from uuid import uuid4

import pytest

from argus.backend.service.email_service import EmailService
from argus.backend.tests.email_service.conftest import EmailListener

API_PREFIX = "/api/v1/client"
RUN_TYPE = "scylla-cluster-tests"


@pytest.fixture
def submitted_run_id(flask_client, fake_test) -> str:
    run_id = str(uuid4())
    payload = {
        "run_id": run_id,
        "job_name": fake_test.build_system_id,
        "job_url": "http://example.com/job/7",
        "started_by": "client_api_user",
        "commit_id": "cafef00d",
        "origin_url": "http://example.com/repo.git",
        "branch_name": "main",
        "sct_config": {"cluster_backend": "aws"},
        "schema_version": "v8",
    }
    resp = flask_client.post(
        f"{API_PREFIX}/testrun/{RUN_TYPE}/submit",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.text
    assert resp.json["status"] == "ok"
    return run_id


def _get_run_info(flask_client, run_id: str) -> dict:
    resp = flask_client.get(f"{API_PREFIX}/testrun/{run_id}/info")
    assert resp.status_code == 200, resp.text
    assert resp.json["status"] == "ok", resp.json
    return resp.json["response"]


def test_submit_run_then_get_run_returns_payload(flask_client, submitted_run_id):
    resp = flask_client.get(f"{API_PREFIX}/testrun/{RUN_TYPE}/{submitted_run_id}/get")
    assert resp.status_code == 200, resp.text
    assert resp.json["status"] == "ok"
    body = resp.json["response"]
    assert body is not None
    assert str(body["id"]) == submitted_run_id


def test_get_run_returns_null_for_unknown_run(flask_client):
    resp = flask_client.get(f"{API_PREFIX}/testrun/{RUN_TYPE}/{uuid4()}/get")
    assert resp.status_code == 200
    assert resp.json["status"] == "ok"
    assert resp.json["response"] is None


def test_get_run_info_returns_full_details(flask_client, submitted_run_id, fake_test):
    info = _get_run_info(flask_client, submitted_run_id)
    assert info["plugin_name"] == RUN_TYPE
    assert str(info["test_run"]["id"]) == submitted_run_id
    assert info["test_info"]["test"]["name"] == fake_test.name
    assert info["comments"] == []
    assert info["activity"]["raw_events"] == []


def test_get_run_info_unknown_run_returns_error(flask_client):
    resp = flask_client.get(f"{API_PREFIX}/testrun/{uuid4()}/info")
    assert resp.status_code == 200
    assert resp.json["status"] == "error"
    assert resp.json["response"]["exception"] == "ClientException"


def test_heartbeat_sets_recent_timestamp(flask_client, submitted_run_id):
    before = int(time.time())
    resp = flask_client.post(f"{API_PREFIX}/testrun/{RUN_TYPE}/{submitted_run_id}/heartbeat")
    after = int(time.time())
    assert resp.status_code == 200
    assert resp.json["status"] == "ok"
    hb = resp.json["response"]
    assert isinstance(hb, int)
    assert before <= hb <= after

    info = _get_run_info(flask_client, submitted_run_id)
    assert info["test_run"]["heartbeat"] == hb


def test_get_status_returns_initial_created(flask_client, submitted_run_id):
    resp = flask_client.get(f"{API_PREFIX}/testrun/{RUN_TYPE}/{submitted_run_id}/get_status")
    assert resp.status_code == 200
    assert resp.json["status"] == "ok"
    assert resp.json["response"] == "created"


def test_set_status_updates_run(flask_client, submitted_run_id):
    resp = flask_client.post(
        f"{API_PREFIX}/testrun/{RUN_TYPE}/{submitted_run_id}/set_status",
        data=json.dumps({"new_status": "running"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json["status"] == "ok"
    assert resp.json["response"] == "running"

    follow_up = flask_client.get(f"{API_PREFIX}/testrun/{RUN_TYPE}/{submitted_run_id}/get_status")
    assert follow_up.json["response"] == "running"


def test_update_product_version_persists_value(flask_client, submitted_run_id):
    resp = flask_client.post(
        f"{API_PREFIX}/testrun/{RUN_TYPE}/{submitted_run_id}/update_product_version",
        data=json.dumps({"product_version": "6.1.0"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json["status"] == "ok"
    assert resp.json["response"] == "Submitted"

    info = _get_run_info(flask_client, submitted_run_id)
    assert info["test_run"]["scylla_version"] == "6.1.0"


def test_submit_logs_appends_unique_logs(flask_client, submitted_run_id):
    payload = {
        "logs": [
            {"log_name": "monitor.log", "log_link": "http://example.com/m.log"},
            {"log_name": "loader.log", "log_link": "http://example.com/l.log"},
            # Duplicate log_name should be deduplicated by submit_logs.
            {"log_name": "monitor.log", "log_link": "http://example.com/dup.log"},
        ],
    }
    resp = flask_client.post(
        f"{API_PREFIX}/testrun/{RUN_TYPE}/{submitted_run_id}/logs/submit",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json["status"] == "ok"
    assert resp.json["response"] == "Submitted"

    info = _get_run_info(flask_client, submitted_run_id)
    log_names = {entry[0] for entry in info["test_run"]["logs"]}
    assert log_names == {"monitor.log", "loader.log"}


def test_finalize_run_records_end_time(flask_client, submitted_run_id):
    resp = flask_client.post(f"{API_PREFIX}/testrun/{RUN_TYPE}/{submitted_run_id}/finalize")
    assert resp.status_code == 200
    assert resp.json["status"] == "ok"
    assert resp.json["response"] == "Finalized"

    info = _get_run_info(flask_client, submitted_run_id)
    assert info["test_run"]["end_time"] is not None


def _pytest_payload(test_name: str, status: str = "passed", duration: float = 0.5) -> dict:
    ts = time.time()
    return {
        "name": test_name,
        "timestamp": ts,
        "session_timestamp": ts,
        "test_type": "dtest",
        "run_id": str(uuid4()),
        "status": status,
        "duration": duration,
        "markers": ["client_api_test"],
        "user_fields": {"SCYLLA_MODE": "release"},
    }


def test_submit_pytest_result_via_endpoint(flask_client):
    payload = _pytest_payload(f"client_api_pytest::test_{uuid4().hex}")
    resp = flask_client.post(
        f"{API_PREFIX}/testrun/pytest/result/submit",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.text
    assert resp.json["status"] == "ok"
    body = resp.json["response"]
    assert body["name"] == payload["name"]
    assert body["id"] is not None


def test_pytest_field_stats_returns_avg_duration(flask_client):
    test_name = f"client_api_pytest::test_avg_{uuid4().hex}"
    durations = [1.0, 2.0, 3.0]
    for d in durations:
        payload = _pytest_payload(test_name, duration=d)
        # Force unique timestamps so each row is a distinct primary key.
        payload["timestamp"] = time.time() + d
        payload["session_timestamp"] = payload["timestamp"]
        resp = flask_client.post(
            f"{API_PREFIX}/testrun/pytest/result/submit",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert resp.status_code == 200, resp.text
        assert resp.json["status"] == "ok"

    resp = flask_client.get(f"{API_PREFIX}/testrun/pytest/{test_name}/stats/duration/avg")
    assert resp.status_code == 200, resp.text
    assert resp.json["status"] == "ok"
    avg = resp.json["response"][test_name]["duration"]["avg"]
    assert avg == pytest.approx(sum(durations) / len(durations), rel=1e-3)


def test_render_email_report_returns_html(flask_client, submitted_run_id):
    EmailService.set_sender(EmailListener())
    try:
        payload = {
            "run_id": submitted_run_id,
            "title": "#auto",
            "recipients": ["nobody@example.com"],
            "sections": [],
            "attachments": [],
            "schema_version": "v8",
        }
        resp = flask_client.post(
            f"{API_PREFIX}/testrun/report",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert resp.status_code == 200, resp.text
        body = resp.get_data(as_text=True)
        # render_email_report returns the html body directly (no JSON envelope).
        assert "<html" in body.lower() or "<table" in body.lower()
        assert submitted_run_id in body or "client_api_user" in body
    finally:
        EmailService.set_sender(None)
