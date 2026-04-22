import json
import time
import uuid

import pytest
from flask import g


def _create_view(flask_client, name, items=None, settings='{"widgets": []}',
                 description=None, display_name=None):
    payload = {
        "name": name,
        "items": items or [],
        "settings": settings,
    }
    if description is not None:
        payload["description"] = description
    if display_name is not None:
        payload["displayName"] = display_name
    return flask_client.post("/api/v1/views/create", json=payload).json


@pytest.fixture
def view_name():
    return f"view_{uuid.uuid4().hex[:12]}"


def test_index(flask_client):
    res = flask_client.get("/api/v1/views/").json
    assert res["status"] == "ok"
    assert res["response"] == {"version": "v1"}


def test_create_view_success(flask_client, view_name):
    res = _create_view(flask_client, view_name, settings='{"widgets": [1]}',
                       description="desc-1", display_name="Disp")
    assert res["status"] == "ok"
    view_id = res["response"]["id"]

    fetched = flask_client.get(f"/api/v1/views/get?viewId={view_id}").json
    assert fetched["status"] == "ok"
    assert fetched["response"]["name"] == view_name
    assert fetched["response"]["display_name"] == "Disp"
    assert fetched["response"]["description"] == "desc-1"
    assert fetched["response"]["widget_settings"] == '{"widgets": [1]}'
    assert fetched["response"]["user_id"] == str(g.user.id)


def test_create_view_with_release_and_group_items(flask_client, view_name, release, group, fake_test):
    res = _create_view(
        flask_client,
        view_name,
        items=[f"release:{release.id}", f"group:{group.id}", f"test:{fake_test.id}"],
    )
    assert res["status"] == "ok"
    view_id = res["response"]["id"]
    resolved = flask_client.get(f"/api/v1/views/{view_id}/resolve").json["response"]
    assert str(release.id) in [str(r) for r in resolved["release_ids"]]
    assert str(group.id) in [str(g_) for g_ in resolved["group_ids"]]
    test_ids = {str(t) for t in resolved["tests"]}
    assert str(fake_test.id) in test_ids


def test_create_view_duplicate_name_errors(flask_client, view_name):
    _create_view(flask_client, view_name)
    res = _create_view(flask_client, view_name)
    assert res["status"] == "error"
    assert "already exists" in res["response"]["arguments"][0]


def test_get_view_missing_id_errors(flask_client):
    res = flask_client.get("/api/v1/views/get").json
    assert res["status"] == "error"
    assert "No viewId" in res["response"]["arguments"][0]


def test_get_view_unknown_id_errors(flask_client):
    res = flask_client.get(f"/api/v1/views/get?viewId={uuid.uuid4()}").json
    assert res["status"] == "error"
    assert res["response"]["exception"] == "DoesNotExist"


def test_all_views_filters_by_user(flask_client, view_name):
    res = _create_view(flask_client, view_name)
    view_id = res["response"]["id"]

    from argus.backend.models.web import User, UserRoles
    other = User(
        id=uuid.uuid4(),
        username=f"viewuser_{uuid.uuid4().hex[:8]}",
        full_name="Other Viewer",
        email=f"viewuser_{uuid.uuid4().hex[:8]}@scylladb.com",
        password="pw",
        roles=[UserRoles.User.value],
    )
    other.save()
    other_listing = flask_client.get(f"/api/v1/views/all?userId={other.id}").json
    assert other_listing["status"] == "ok"
    assert view_id not in {v["id"] for v in other_listing["response"]}


def test_all_views_no_filter(flask_client, view_name):
    res = _create_view(flask_client, view_name)
    view_id = res["response"]["id"]
    listing = flask_client.get("/api/v1/views/all").json["response"]
    assert any(v["id"] == view_id for v in listing)


def test_update_view_success(flask_client, view_name, fake_test):
    created = _create_view(flask_client, view_name)
    view_id = created["response"]["id"]

    update_payload = {
        "viewId": view_id,
        "updateData": {
            "name": view_name,
            "description": "updated",
            "display_name": "Updated",
            "items": [f"test:{fake_test.id}"],
            "widget_settings": '{"widgets": [42]}',
            "plan_id": None,
        },
    }
    res = flask_client.post("/api/v1/views/update", json=update_payload).json
    assert res["status"] == "ok"
    assert res["response"] is True

    fetched = flask_client.get(f"/api/v1/views/get?viewId={view_id}").json["response"]
    assert fetched["description"] == "updated"
    assert fetched["display_name"] == "Updated"
    assert fetched["widget_settings"] == '{"widgets": [42]}'
    assert str(fake_test.id) in [str(t) for t in fetched["tests"]]


def test_delete_view_success(flask_client, view_name):
    created = _create_view(flask_client, view_name)
    view_id = created["response"]["id"]
    res = flask_client.post("/api/v1/views/delete", json={"viewId": view_id}).json
    assert res["status"] == "ok"
    assert res["response"] is True

    after = flask_client.get(f"/api/v1/views/get?viewId={view_id}").json
    assert after["status"] == "error"
    assert after["response"]["exception"] == "DoesNotExist"


def test_delete_view_unknown_id_errors(flask_client):
    res = flask_client.post("/api/v1/views/delete", json={"viewId": str(uuid.uuid4())}).json
    assert res["status"] == "error"
    assert res["response"]["exception"] == "DoesNotExist"


def test_search_no_query(flask_client):
    res = flask_client.get("/api/v1/views/search").json
    assert res["status"] == "ok"
    assert res["response"] == {"hits": [], "total": 0}


def test_search_finds_release_by_name(flask_client, release):
    res = flask_client.get(f"/api/v1/views/search?query={release.name}").json
    assert res["status"] == "ok"
    types = {h.get("type") for h in res["response"]["hits"]}
    # Special "Add all..." entry is always prepended.
    assert "special" in types
    names = {h.get("name") for h in res["response"]["hits"]}
    assert release.name in names


def test_view_resolve_tests_returns_serialized_tests(flask_client, view_name, fake_test):
    created = _create_view(flask_client, view_name, items=[f"test:{fake_test.id}"])
    view_id = created["response"]["id"]
    res = flask_client.get(f"/api/v1/views/{view_id}/resolve/tests").json
    assert res["status"] == "ok"
    test_ids = {t["id"] for t in res["response"]}
    assert str(fake_test.id) in test_ids


def test_view_resolve_for_edit_includes_items(flask_client, view_name, release, group):
    created = _create_view(
        flask_client, view_name,
        items=[f"release:{release.id}", f"group:{group.id}"],
    )
    view_id = created["response"]["id"]
    res = flask_client.get(f"/api/v1/views/{view_id}/resolve").json
    assert res["status"] == "ok"
    items = res["response"]["items"]
    item_ids = {item.get("id") for item in items}
    assert str(release.id) in item_ids
    assert str(group.id) in item_ids


def test_view_versions_for_empty_view(flask_client, view_name):
    created = _create_view(flask_client, view_name)
    view_id = created["response"]["id"]
    res = flask_client.get(f"/api/v1/views/{view_id}/versions").json
    assert res["status"] == "ok"
    assert isinstance(res["response"], list)


def test_view_images_for_empty_view(flask_client, view_name):
    created = _create_view(flask_client, view_name)
    view_id = created["response"]["id"]
    res = flask_client.get(f"/api/v1/views/{view_id}/images").json
    assert res["status"] == "ok"
    assert isinstance(res["response"], list)


def test_view_pytest_results_empty(flask_client, view_name):
    created = _create_view(flask_client, view_name)
    view_id = created["response"]["id"]
    res = flask_client.get(f"/api/v1/views/{view_id}/pytest/results").json
    assert res["status"] == "ok"
    assert res["response"] == []
