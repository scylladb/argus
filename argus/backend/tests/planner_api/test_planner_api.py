import datetime
import json
import uuid

import pytest
from flask import g

from argus.backend.models.plan import ArgusReleasePlan
from argus.backend.models.web import ArgusUserView, User, UserRoles


@pytest.fixture
def planner_user():
    user = User(
        id=uuid.uuid4(),
        username=f"planner_{uuid.uuid4().hex[:8]}",
        full_name="Planner User",
        email=f"planner_{uuid.uuid4().hex[:8]}@scylladb.com",
        password="pw",
        roles=[UserRoles.User.value],
    )
    user.save()
    return user


@pytest.fixture
def cleanup_plans():
    yield
    for plan in list(ArgusReleasePlan.all()):
        if plan.view_id:
            try:
                ArgusUserView.get(id=plan.view_id).delete()
            except ArgusUserView.DoesNotExist:
                pass
        plan.delete()


def _create_plan(flask_client, release, fake_test, name=None, target_version="1.0",
                 owner=None, tests=None, groups=None):
    payload = {
        "name": name or f"plan_{uuid.uuid4().hex[:8]}",
        "description": "test plan",
        "owner": str(owner or g.user.id),
        "participants": [],
        "target_version": target_version,
        "release_id": str(release.id),
        "tests": [str(t) for t in (tests if tests is not None else [fake_test.id])],
        "groups": [str(gid) for gid in (groups or [])],
        "assignments": {},
    }
    return flask_client.post("/api/v1/planning/plan/create", json=payload).json


def test_version(flask_client):
    res = flask_client.get("/api/v1/planning/").json
    assert res["status"] == "ok"
    assert res["response"] == "v1"


def test_create_plan_success(flask_client, release, fake_test, cleanup_plans):
    res = _create_plan(flask_client, release, fake_test)
    assert res["status"] == "ok"
    plan_id = res["response"]["id"]

    fetched = flask_client.get(f"/api/v1/planning/plan/{plan_id}/get").json
    assert fetched["status"] == "ok"
    body = fetched["response"]
    assert body["release_id"] == str(release.id)
    assert body["target_version"] == "1.0"
    assert str(fake_test.id) in [str(t) for t in body["tests"]]
    assert body["view_id"]  # Auto-created view


def test_create_plan_duplicate_name_version_errors(flask_client, release, fake_test, cleanup_plans):
    name = f"plan_{uuid.uuid4().hex[:8]}"
    first = _create_plan(flask_client, release, fake_test, name=name, target_version="2.0")
    assert first["status"] == "ok"
    dup = _create_plan(flask_client, release, fake_test, name=name, target_version="2.0")
    assert dup["status"] == "error"
    assert "existing plan" in dup["response"]["arguments"][0]


def test_get_plan_unknown_id_errors(flask_client):
    res = flask_client.get(f"/api/v1/planning/plan/{uuid.uuid1()}/get").json
    assert res["status"] == "error"
    assert res["response"]["exception"] == "DoesNotExist"


def test_plans_for_release(flask_client, release, fake_test, cleanup_plans):
    a = _create_plan(flask_client, release, fake_test, target_version="3.1")["response"]["id"]
    b = _create_plan(flask_client, release, fake_test, target_version="3.2")["response"]["id"]
    res = flask_client.get(f"/api/v1/planning/release/{release.id}/all").json
    assert res["status"] == "ok"
    ids = {p["id"] for p in res["response"]}
    assert {a, b}.issubset(ids)


def test_update_plan(flask_client, release, fake_test, cleanup_plans):
    created = _create_plan(flask_client, release, fake_test)["response"]
    plan_id = created["id"]

    update_payload = {
        "id": plan_id,
        "name": created["name"],
        "completed": False,
        "description": "updated description",
        "owner": str(g.user.id),
        "participants": [],
        "target_version": "9.9",
        "assignee_mapping": {},
        "release_id": str(release.id),
        "tests": [str(fake_test.id)],
        "groups": [],
        "creation_time": datetime.datetime.now(tz=datetime.UTC).isoformat(),
        "last_updated": datetime.datetime.now(tz=datetime.UTC).isoformat(),
        "ends_at": datetime.datetime.now(tz=datetime.UTC).isoformat(),
        "created_from": None,
        "view_id": created["view_id"],
    }
    res = flask_client.post("/api/v1/planning/plan/update", json=update_payload).json
    assert res["status"] == "ok"
    assert res["response"] is True

    fetched = flask_client.get(f"/api/v1/planning/plan/{plan_id}/get").json["response"]
    assert fetched["description"] == "updated description"
    assert fetched["target_version"] == "9.9"


def test_change_plan_owner(flask_client, release, fake_test, planner_user, cleanup_plans):
    plan_id = _create_plan(flask_client, release, fake_test)["response"]["id"]
    res = flask_client.post(
        f"/api/v1/planning/plan/{plan_id}/owner/set",
        json={"newOwner": str(planner_user.id)},
    ).json
    assert res["status"] == "ok"
    fetched = flask_client.get(f"/api/v1/planning/plan/{plan_id}/get").json["response"]
    assert fetched["owner"] == str(planner_user.id)


def test_resolve_plan_entities(flask_client, release, fake_test, cleanup_plans):
    plan_id = _create_plan(flask_client, release, fake_test)["response"]["id"]
    res = flask_client.get(f"/api/v1/planning/plan/{plan_id}/resolve_entities").json
    assert res["status"] == "ok"
    test_ids = {item.get("id") for item in res["response"]}
    assert str(fake_test.id) in test_ids


def test_delete_plan_removes_view(flask_client, release, fake_test, cleanup_plans):
    created = _create_plan(flask_client, release, fake_test)["response"]
    plan_id = created["id"]
    view_id = created["view_id"]
    res = flask_client.delete(f"/api/v1/planning/plan/{plan_id}/delete?deleteView=1").json
    assert res["status"] == "ok"
    assert res["response"] is True

    after = flask_client.get(f"/api/v1/planning/plan/{plan_id}/get").json
    assert after["status"] == "error"
    view_after = flask_client.get(f"/api/v1/views/get?viewId={view_id}").json
    assert view_after["status"] == "error"


def test_delete_plan_keeps_view(flask_client, release, fake_test, cleanup_plans):
    created = _create_plan(flask_client, release, fake_test)["response"]
    plan_id = created["id"]
    view_id = created["view_id"]
    res = flask_client.delete(f"/api/v1/planning/plan/{plan_id}/delete?deleteView=0").json
    assert res["status"] == "ok"
    view_after = flask_client.get(f"/api/v1/views/get?viewId={view_id}").json
    assert view_after["status"] == "ok"
    assert view_after["response"]["plan_id"] is None


def test_grid_view_for_release(flask_client, release, group, fake_test):
    res = flask_client.get(f"/api/v1/planning/release/{release.id}/gridview").json
    assert res["status"] == "ok"
    body = res["response"]
    assert str(group.id) in body["groups"]
    assert str(fake_test.id) in body["tests"]
    assert body["tests"][str(fake_test.id)]["release"] == release.name


def test_search_no_query_returns_empty(flask_client):
    res = flask_client.get("/api/v1/planning/search").json
    assert res["status"] == "ok"
    assert res["response"] == {"hits": [], "total": 0}


def test_search_finds_test_name(flask_client, release, fake_test):
    res = flask_client.get(
        f"/api/v1/planning/search?query={fake_test.name}&releaseId={release.id}"
    ).json
    assert res["status"] == "ok"
    names = {h.get("name") for h in res["response"]["hits"]}
    assert fake_test.name in names


def test_explode_group(flask_client, group, fake_test):
    res = flask_client.get(f"/api/v1/planning/group/{group.id}/explode").json
    assert res["status"] == "ok"
    test_ids = {str(t["id"]) for t in res["response"]}
    assert str(fake_test.id) in test_ids


def test_check_plan_copy_eligibility_missing_release_id_errors(flask_client, release, fake_test, cleanup_plans):
    plan_id = _create_plan(flask_client, release, fake_test)["response"]["id"]
    res = flask_client.get(f"/api/v1/planning/plan/{plan_id}/copy/check").json
    assert res["status"] == "error"
    assert "Missing release id" in res["response"]["arguments"][0]


def test_check_plan_copy_eligibility_returns_failed_for_missing_tests(
    flask_client, release_manager_service, release, fake_test, cleanup_plans
):
    plan_id = _create_plan(flask_client, release, fake_test)["response"]["id"]
    # Create empty target release with no tests => copy will be missing
    target_release = release_manager_service.create_release(
        f"target_rel_{uuid.uuid4().hex[:8]}", "Target", False
    )
    res = flask_client.get(
        f"/api/v1/planning/plan/{plan_id}/copy/check?releaseId={target_release.id}"
    ).json
    assert res["status"] == "ok"
    assert res["response"]["status"] == "failed"
    missing_test_ids = {t.get("id") for t in res["response"]["missing"]["tests"]}
    assert str(fake_test.id) in missing_test_ids
