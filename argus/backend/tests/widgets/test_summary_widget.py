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
