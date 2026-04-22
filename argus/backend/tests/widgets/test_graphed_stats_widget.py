import uuid

import pytest


@pytest.fixture
def empty_view(flask_client):
    name = f"gs_view_{uuid.uuid4().hex[:8]}"
    res = flask_client.post(
        "/api/v1/views/create",
        json={"name": name, "items": [], "settings": "{}"},
    ).json
    return res["response"]


def test_graphed_stats_empty_view(flask_client, empty_view):
    res = flask_client.get(
        f"/api/v1/views/widgets/graphed_stats?view_id={empty_view['id']}"
    ).json
    assert res["status"] == "ok"
    assert res["response"] == {"test_runs": [], "nemesis_data": []}


def test_graphed_stats_unknown_view_errors(flask_client):
    res = flask_client.get(
        f"/api/v1/views/widgets/graphed_stats?view_id={uuid.uuid4()}"
    ).json
    assert res["status"] == "error"
    assert res["response"]["exception"] == "DoesNotExist"


def test_runs_details_empty_list(flask_client):
    res = flask_client.post(
        "/api/v1/views/widgets/runs_details", json={"run_ids": []}
    ).json
    assert res["status"] == "ok"
    assert res["response"] == {}


def test_runs_details_unknown_run_ids(flask_client):
    run_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    res = flask_client.post(
        "/api/v1/views/widgets/runs_details",
        json={"run_ids": run_ids},
    ).json
    assert res["status"] == "ok"
    assert set(res["response"].keys()) == set(run_ids)
    for entry in res["response"].values():
        assert entry == {
            "build_id": None,
            "start_time": None,
            "assignee": None,
            "version": "unknown",
            "issues": [],
        }


def test_runs_details_missing_run_ids_errors(flask_client):
    res = flask_client.post("/api/v1/views/widgets/runs_details", json={}).json
    assert res["status"] == "error"
    assert "Missing run_ids" in res["response"]["arguments"][0]


def test_runs_details_run_ids_not_list_errors(flask_client):
    res = flask_client.post(
        "/api/v1/views/widgets/runs_details",
        json={"run_ids": "not-a-list"},
    ).json
    assert res["status"] == "error"
    assert "must be a list" in res["response"]["arguments"][0]
