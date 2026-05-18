"""Controller-level integration tests for the graph-view + test-results
endpoints exposed by ``argus/backend/controller/api.py``.

Scope (iteration 7 of the controller coverage matrix):

- ``POST /api/v1/create-graph-view``
- ``POST /api/v1/update-graph-view``
- ``GET  /api/v1/test-results``
- ``HEAD /api/v1/test-results``
"""

import json
import uuid

import pytest


API_PREFIX = "/api/v1"


# ---------------------------------------------------------------------------
# /create-graph-view + /update-graph-view
# ---------------------------------------------------------------------------

@pytest.fixture
def created_graph_view(flask_client, fake_test):
    payload = {
        "testId": str(fake_test.id),
        "name": "iteration7-view",
        "description": "iteration7-desc",
    }
    resp = flask_client.post(
        f"{API_PREFIX}/create-graph-view",
        data=json.dumps(payload), content_type="application/json",
    )
    assert resp.status_code == 200, resp.data
    body = resp.json
    assert body["status"] == "ok"
    return body["response"]


def test_create_graph_view_round_trip(flask_client, fake_test, created_graph_view):
    assert created_graph_view["name"] == "iteration7-view"
    assert created_graph_view["description"] == "iteration7-desc"
    assert str(created_graph_view["test_id"]) == str(fake_test.id)
    view_id = str(created_graph_view["id"])
    assert view_id

    # Verify via GET /test-results — graph_views section should include it.
    get_resp = flask_client.get(
        f"{API_PREFIX}/test-results", query_string={"testId": str(fake_test.id)}
    )
    assert get_resp.status_code == 200, get_resp.data
    body = get_resp.json
    assert body["status"] == "ok"
    view_ids = [str(v["id"]) for v in body["response"]["graph_views"]]
    assert view_id in view_ids


def test_update_graph_view_changes_name_and_graphs(flask_client, fake_test, created_graph_view):
    payload = {
        "testId": str(fake_test.id),
        "id": str(created_graph_view["id"]),
        "name": "iteration7-updated",
        "description": "iteration7-updated-desc",
        "graphs": {"graph-key-1": "graph-data-1"},
    }
    resp = flask_client.post(
        f"{API_PREFIX}/update-graph-view",
        data=json.dumps(payload), content_type="application/json",
    )
    assert resp.status_code == 200, resp.data
    body = resp.json
    assert body["status"] == "ok"
    assert body["response"]["name"] == "iteration7-updated"
    assert body["response"]["description"] == "iteration7-updated-desc"
    assert body["response"]["graphs"]["graph-key-1"] == "graph-data-1"

    # Round-trip via /test-results
    get_resp = flask_client.get(
        f"{API_PREFIX}/test-results", query_string={"testId": str(fake_test.id)}
    )
    views = {str(v["id"]): v for v in get_resp.json["response"]["graph_views"]}
    assert views[str(created_graph_view["id"])]["name"] == "iteration7-updated"


def test_update_graph_view_unknown_id_errors(flask_client, fake_test):
    payload = {
        "testId": str(fake_test.id),
        "id": str(uuid.uuid4()),
        "name": "x",
        "description": "x",
        "graphs": {},
    }
    resp = flask_client.post(
        f"{API_PREFIX}/update-graph-view",
        data=json.dumps(payload), content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json["status"] == "error"


# ---------------------------------------------------------------------------
# /test-results  (GET + HEAD)
# ---------------------------------------------------------------------------

def test_test_results_returns_graphs_payload(flask_client, fake_test):
    resp = flask_client.get(
        f"{API_PREFIX}/test-results", query_string={"testId": str(fake_test.id)}
    )
    assert resp.status_code == 200, resp.data
    body = resp.json
    assert body["status"] == "ok"
    response = body["response"]
    assert response["graphs"] == []
    assert isinstance(response["releases_filters"], list)
    assert isinstance(response["graph_views"], list)
    assert "ticks" in response


def test_test_results_with_date_range(flask_client, fake_test):
    resp = flask_client.get(
        f"{API_PREFIX}/test-results",
        query_string={
            "testId": str(fake_test.id),
            "startDate": "2025-01-01T00:00:00",
            "endDate": "2026-01-01T00:00:00",
        },
    )
    assert resp.status_code == 200, resp.data
    assert resp.json["status"] == "ok"


def test_test_results_missing_test_id(flask_client):
    resp = flask_client.get(f"{API_PREFIX}/test-results")
    assert resp.status_code == 200
    assert resp.json["status"] == "error"


def test_test_results_head_returns_404_when_no_results(flask_client, fake_test):
    resp = flask_client.head(
        f"{API_PREFIX}/test-results", query_string={"testId": str(fake_test.id)}
    )
    assert resp.status_code == 404
