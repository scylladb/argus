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


def test_graphed_stats_with_seeded_view(flask_client, seeded_view_with_run, sct_run):
    """Seeded SCT run appears in the graphed_stats response."""
    res = flask_client.get(
        f"/api/v1/views/widgets/graphed_stats?view_id={seeded_view_with_run.view_id}"
    ).json
    assert res["status"] == "ok"
    body = res["response"]
    assert body["nemesis_data"] == []
    assert len(body["test_runs"]) == 1
    run = body["test_runs"][0]
    assert run["run_id"] == sct_run.run_id
    assert run["version"] == sct_run.package_version


def test_graphed_stats_with_nemesis(flask_client, seeded_view_with_run, sct_run_with_nemesis):
    """A finalized nemesis on the seeded run shows up in nemesis_data."""
    res = flask_client.get(
        f"/api/v1/views/widgets/graphed_stats?view_id={seeded_view_with_run.view_id}"
    ).json
    assert res["status"] == "ok"
    nemeses = res["response"]["nemesis_data"]
    assert len(nemeses) == 1
    assert nemeses[0]["status"] == "succeeded"
    assert nemeses[0]["run_id"] == sct_run_with_nemesis.run_id


def test_runs_details_with_linked_issue(flask_client, linked_github_issue, sct_run):
    """runs_details returns build_id/version and surfaces linked GitHub issues."""
    res = flask_client.post(
        "/api/v1/views/widgets/runs_details",
        json={"run_ids": [sct_run.run_id]},
    ).json
    assert res["status"] == "ok"
    entry = res["response"][sct_run.run_id]
    expected_version = f"{sct_run.package_version}-{sct_run.package_date}"
    assert entry["version"] == expected_version
    assert entry["build_id"].startswith(sct_run.run_id) or "#" in entry["build_id"]
    assert len(entry["issues"]) == 1
    issue = entry["issues"][0]
    assert issue["number"] == 12345
    assert issue["state"] == "open"
    assert issue["title"] == "widget seed issue"
