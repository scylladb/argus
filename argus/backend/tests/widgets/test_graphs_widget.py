import uuid

import pytest


@pytest.fixture
def empty_view(flask_client):
    name = f"graphs_view_{uuid.uuid4().hex[:8]}"
    res = flask_client.post(
        "/api/v1/views/create",
        json={"name": name, "items": [], "settings": "{}"},
    ).json
    return res["response"]


def test_graph_views_empty_view(flask_client, empty_view):
    res = flask_client.get(
        f"/api/v1/views/widgets/graphs/graph_views?view_id={empty_view['id']}"
    ).json
    assert res["status"] == "ok"
    assert res["response"] == {}
    assert res["tests_details"] == {}


def test_graph_views_with_test_no_graph_views(flask_client, fake_test):
    name = f"graphs_view_{uuid.uuid4().hex[:8]}"
    view = flask_client.post(
        "/api/v1/views/create",
        json={"name": name, "items": [f"test:{fake_test.id}"], "settings": "{}"},
    ).json["response"]
    res = flask_client.get(
        f"/api/v1/views/widgets/graphs/graph_views?view_id={view['id']}"
    ).json
    assert res["status"] == "ok"
    # test_id present in response, value is empty list because no graph_views
    assert res["response"][str(fake_test.id)] == []
    assert res["tests_details"] == {}


def test_graph_views_unknown_view_errors(flask_client):
    res = flask_client.get(
        f"/api/v1/views/widgets/graphs/graph_views?view_id={uuid.uuid4()}"
    ).json
    assert res["status"] == "error"
    assert res["response"]["exception"] == "DoesNotExist"


def test_graph_views_with_seeded_graph_view(flask_client, seeded_view_with_run, graph_view_for_test):
    """A test that has an ArgusGraphView attached surfaces in tests_details."""
    res = flask_client.get(
        f"/api/v1/views/widgets/graphs/graph_views?view_id={seeded_view_with_run.view_id}"
    ).json
    assert res["status"] == "ok"
    test_id = seeded_view_with_run.test_id
    # Even if no chart data is renderable, having any graph_view triggers
    # tests_details lookup for that test.
    assert test_id in res["tests_details"]
    assert "name" in res["tests_details"][test_id]
    assert test_id in res["response"]
