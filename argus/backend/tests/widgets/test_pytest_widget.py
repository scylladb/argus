import uuid
from datetime import datetime, timezone

import pytest


def test_pytest_view_returns_zero(flask_client):
    res = flask_client.get("/api/v1/views/widgets/pytest/view").json
    assert res["status"] == "ok"
    assert res["response"] == 0


def _bracket_params() -> str:
    # result_filter requires before/after to avoid IndexError on empty results
    after = int(datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp())
    before = int(datetime(2030, 1, 1, tzinfo=timezone.utc).timestamp())
    return f"after={after}&before={before}"


def test_pytest_view_results_empty(flask_client):
    view_id = uuid.uuid4()
    res = flask_client.get(
        f"/api/v1/views/widgets/pytest/view/{view_id}/results?{_bracket_params()}"
    ).json
    assert res["status"] == "ok"
    body = res["response"]
    assert body["total"] == 0
    assert body["hits"] == []
    assert body["pieChart"] == {}
    assert "labels" in body["barChart"] and "datasets" in body["barChart"]


def test_pytest_release_results_empty(flask_client):
    release_id = uuid.uuid4()
    res = flask_client.get(
        f"/api/v1/views/widgets/pytest/release/{release_id}/results?{_bracket_params()}"
    ).json
    assert res["status"] == "ok"
    body = res["response"]
    assert body["total"] == 0
    assert body["hits"] == []


def test_pytest_user_fields_for_unknown_returns_empty(flask_client):
    test_name = "tests/some_test.py::test_thing"
    iso_id = datetime(2024, 1, 1, tzinfo=timezone.utc).isoformat()
    res = flask_client.get(
        f"/api/v1/views/widgets/pytest/{test_name}/{iso_id}/fields"
    ).json
    assert res["status"] == "ok"
    assert res["response"] == {}


def test_pytest_user_fields_invalid_id_errors(flask_client):
    res = flask_client.get(
        "/api/v1/views/widgets/pytest/foo.py::bar/not-a-date/fields"
    ).json
    assert res["status"] == "error"


def test_pytest_view_results_with_seeded_row(flask_client, seeded_pytest_row):
    """A seeded pytest row appears in result_filter output (via barChart/pieChart)."""
    view_id = uuid.uuid4()
    # status[] is required when filtering by id range -- pytest_v2 has status as
    # a clustering key before id, so unrestricted id filtering would error.
    res = flask_client.get(
        f"/api/v1/views/widgets/pytest/view/{view_id}/results?{_bracket_params()}&status[]=passed"
    ).json
    assert res["status"] == "ok"
    body = res["response"]
    # The seeded row should be visible somewhere in the unfiltered hits list
    assert any(hit["name"] == seeded_pytest_row["name"] for hit in body["hits"]), body["hits"][:3]
    assert body["pieChart"].get("passed", 0) >= 1


def test_pytest_user_fields_for_seeded_row(flask_client, seeded_pytest_row):
    """get_user_fields_for_result returns the user_fields submitted with the row."""
    res = flask_client.get(
        f"/api/v1/views/widgets/pytest/{seeded_pytest_row['name']}/{seeded_pytest_row['iso_id']}/fields"
    ).json
    assert res["status"] == "ok"
    assert res["response"] == {"SCYLLA_MODE": "release"}
