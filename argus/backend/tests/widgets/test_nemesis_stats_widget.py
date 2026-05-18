import uuid

import pytest


@pytest.fixture
def empty_view(flask_client):
    name = f"nemesis_view_{uuid.uuid4().hex[:8]}"
    res = flask_client.post(
        "/api/v1/views/create",
        json={"name": name, "items": [], "settings": "{}"},
    ).json
    return res["response"]


def test_nemesis_data_empty_view(flask_client, empty_view):
    res = flask_client.get(
        f"/api/v1/views/widgets/nemesis_data?view_id={empty_view['id']}"
    ).json
    assert res["status"] == "ok"
    assert res["response"] == {"nemesis_data": []}


def test_nemesis_data_unknown_view_errors(flask_client):
    res = flask_client.get(
        f"/api/v1/views/widgets/nemesis_data?view_id={uuid.uuid4()}"
    ).json
    assert res["status"] == "error"
    assert res["response"]["exception"] == "DoesNotExist"


def test_nemesis_data_missing_view_id_errors(flask_client):
    res = flask_client.get("/api/v1/views/widgets/nemesis_data").json
    assert res["status"] == "error"


def test_nemesis_data_with_seeded_run(flask_client, seeded_view_with_run, sct_run_with_nemesis):
    """Seeded SCT run + finalized nemesis appear in the nemesis_data list."""
    res = flask_client.get(
        f"/api/v1/views/widgets/nemesis_data?view_id={seeded_view_with_run.view_id}"
    ).json
    assert res["status"] == "ok"
    items = res["response"]["nemesis_data"]
    assert len(items) == 1, items
    entry = items[0]
    assert entry["status"] == "succeeded"
    assert entry["version"] == sct_run_with_nemesis.package_version
    assert str(entry["run_id"]) == sct_run_with_nemesis.run_id
