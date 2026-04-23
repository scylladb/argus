import uuid

import pytest
from flask import g


@pytest.fixture
def empty_view(flask_client):
    name = f"summary_view_{uuid.uuid4().hex[:8]}"
    res = flask_client.post(
        "/api/v1/views/create",
        json={"name": name, "items": [], "settings": "{}"},
    ).json
    return res["response"]


def test_summary_versioned_runs_empty_view(flask_client, empty_view):
    res = flask_client.get(
        f"/api/v1/views/widgets/summary/versioned_runs?view_id={empty_view['id']}"
    ).json
    assert res["status"] == "ok"
    assert res["response"] == {"versions": {}, "test_info": {}}


def test_summary_versioned_runs_unknown_view_errors(flask_client):
    res = flask_client.get(
        f"/api/v1/views/widgets/summary/versioned_runs?view_id={uuid.uuid4()}"
    ).json
    assert res["status"] == "error"
    assert res["response"]["exception"] == "DoesNotExist"


def test_summary_runs_results_empty_payload(flask_client):
    res = flask_client.post("/api/v1/views/widgets/summary/runs_results", json={}).json
    assert res["status"] == "ok"
    assert res["response"] == {}


def test_summary_runs_results_unknown_test_returns_empty(flask_client):
    test_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    payload = {test_id: {"some_method": {"run_id": run_id, "status": "passed"}}}
    res = flask_client.post(
        "/api/v1/views/widgets/summary/runs_results", json=payload
    ).json
    assert res["status"] == "ok"
    # Unknown test/run yields empty list of metric tables
    assert res["response"][test_id]["some_method"][run_id] == []


def test_summary_versioned_runs_with_seeded_view(flask_client, seeded_view_with_run, sct_run):
    """View pointing at a seeded SCT run returns the run's version + test info."""
    res = flask_client.get(
        f"/api/v1/views/widgets/summary/versioned_runs?view_id={seeded_view_with_run.view_id}"
    ).json
    assert res["status"] == "ok"
    body = res["response"]
    expected_version = f"{sct_run.package_version}-{sct_run.package_date}-{sct_run.package_revision_id}"
    assert expected_version in body["versions"]
    method_name = sct_run.test_method.rsplit(".", 1)[-1]
    assert sct_run.test_id in body["versions"][expected_version]
    assert body["versions"][expected_version][sct_run.test_id][method_name]["run_id"] == sct_run.run_id
    assert sct_run.test_id in body["test_info"]


def test_summary_runs_results_with_seeded_metric(flask_client, generic_results_for_run):
    """Posting a real test/method/run trio returns the seeded P99 read cell."""
    seed = generic_results_for_run
    method = "test_widget"
    payload = {
        seed.test_id: {method: {"run_id": seed.run_id, "status": "passed"}}
    }
    res = flask_client.post(
        "/api/v1/views/widgets/summary/runs_results", json=payload
    ).json
    assert res["status"] == "ok"
    tables = res["response"][seed.test_id][method][seed.run_id]
    assert tables, "expected at least one metric table for seeded run"
    table_entry = next(entry for entry in tables if seed.table_name in entry)
    table_data = table_entry[seed.table_name]
    assert seed.row_name in table_data["table_data"]
    cell = table_data["table_data"][seed.row_name][seed.column_name]
    assert cell["value"] == 12.5
    assert cell["status"] == "PASS"
