"""Controller-level integration tests for group + test endpoints in
``argus/backend/controller/admin_api.py``.

URL prefix: ``/admin/api/v1`` (admin_api blueprint nested under admin).

Scope (iteration 9 of the controller coverage matrix):

- ``POST /admin/api/v1/group/create``
- ``POST /admin/api/v1/group/update``
- ``POST /admin/api/v1/group/delete``
- ``POST /admin/api/v1/test/create``
- ``POST /admin/api/v1/test/update``
- ``POST /admin/api/v1/test/delete``
- ``POST /admin/api/v1/test/batch_move``
- ``GET  /admin/api/v1/groups/get``
- ``GET  /admin/api/v1/tests/get``
- ``POST /admin/api/v1/release/group/state/toggle``
- ``POST /admin/api/v1/release/test/state/toggle``
"""

import json
import time
import uuid

import pytest


ADMIN_PREFIX = "/admin/api/v1"
API_PREFIX = "/api/v1"


def _post(flask_client, path: str, payload: dict):
    return flask_client.post(path, data=json.dumps(payload), content_type="application/json")


def _group_details(flask_client, group_id: str) -> dict:
    resp = flask_client.get(f"{API_PREFIX}/group/{group_id}/details")
    assert resp.status_code == 200
    body = resp.json
    assert body["status"] == "ok", body
    return body["response"]


def _test_details(flask_client, test_id: str) -> dict:
    resp = flask_client.get(f"{API_PREFIX}/test/{test_id}/details")
    assert resp.status_code == 200
    body = resp.json
    assert body["status"] == "ok", body
    return body["response"]


# ---------------------------------------------------------------------------
# Local function-scoped release/group/test fixtures so each test mutates its
# own isolated hierarchy.
# ---------------------------------------------------------------------------

@pytest.fixture
def admin_release(release_manager_service):
    name = f"adm9_rel_{time.time_ns()}"
    return release_manager_service.create_release(name, name, False)


@pytest.fixture
def admin_group_via_api(flask_client, admin_release):
    name = f"adm9_grp_{time.time_ns()}"
    payload = {
        "group_name": name,
        "pretty_name": name,
        "build_system_id": f"bsid_{time.time_ns()}",
        "release_id": str(admin_release.id),
    }
    resp = _post(flask_client, f"{ADMIN_PREFIX}/group/create", payload)
    assert resp.status_code == 200, resp.data
    body = resp.json
    assert body["status"] == "ok"
    return body["response"]["new_group"]


@pytest.fixture
def admin_test_via_api(flask_client, admin_release, admin_group_via_api):
    name = f"adm9_test_{time.time_ns()}"
    payload = {
        "test_name": name,
        "pretty_name": name,
        "build_id": f"buildid_{time.time_ns()}",
        "build_url": "http://example.com/job/1",
        "group_id": str(admin_group_via_api["id"]),
        "release_id": str(admin_release.id),
        "plugin_name": "scylla-cluster-tests",
    }
    resp = _post(flask_client, f"{ADMIN_PREFIX}/test/create", payload)
    assert resp.status_code == 200, resp.data
    body = resp.json
    assert body["status"] == "ok"
    return body["response"]["new_test"]


# ---------------------------------------------------------------------------
# /group/create + /groups/get + /group/details (round-trip)
# ---------------------------------------------------------------------------

def test_admin_create_group_round_trip(flask_client, admin_release, admin_group_via_api):
    details = _group_details(flask_client, admin_group_via_api["id"])
    assert details["name"] == admin_group_via_api["name"]
    assert str(details["release_id"]) == str(admin_release.id)


def test_admin_get_groups_includes_created(flask_client, admin_release, admin_group_via_api):
    resp = flask_client.get(
        f"{ADMIN_PREFIX}/groups/get", query_string={"releaseId": str(admin_release.id)}
    )
    assert resp.status_code == 200, resp.data
    body = resp.json
    assert body["status"] == "ok"
    ids = {g["id"] for g in body["response"]}
    assert admin_group_via_api["id"] in ids


def test_admin_get_groups_missing_release_id(flask_client):
    resp = flask_client.get(f"{ADMIN_PREFIX}/groups/get")
    assert resp.status_code == 200
    assert resp.json["status"] == "error"


# ---------------------------------------------------------------------------
# /group/update
# ---------------------------------------------------------------------------

def test_admin_update_group(flask_client, admin_group_via_api):
    payload = {
        "group_id": admin_group_via_api["id"],
        "name": admin_group_via_api["name"] + "_upd",
        "pretty_name": "updated-pretty",
        "enabled": False,
        "build_system_id": "updated-bsid",
    }
    resp = _post(flask_client, f"{ADMIN_PREFIX}/group/update", payload)
    assert resp.status_code == 200, resp.data
    assert resp.json["status"] == "ok"

    details = _group_details(flask_client, admin_group_via_api["id"])
    assert details["pretty_name"] == "updated-pretty"
    assert details["enabled"] is False
    assert details["build_system_id"] == "updated-bsid"


# ---------------------------------------------------------------------------
# /release/group/state/toggle
# ---------------------------------------------------------------------------

def test_admin_toggle_group_enabled(flask_client, admin_group_via_api):
    payload = {"entityId": admin_group_via_api["id"], "state": False}
    resp = _post(flask_client, f"{ADMIN_PREFIX}/release/group/state/toggle", payload)
    assert resp.status_code == 200, resp.data
    assert resp.json["status"] == "ok"
    assert _group_details(flask_client, admin_group_via_api["id"])["enabled"] is False


# ---------------------------------------------------------------------------
# /test/create + /tests/get + /test/details (round-trip)
# ---------------------------------------------------------------------------

def test_admin_create_test_round_trip(flask_client, admin_group_via_api, admin_test_via_api):
    details = _test_details(flask_client, admin_test_via_api["id"])
    assert details["name"] == admin_test_via_api["name"]
    assert str(details["group_id"]) == str(admin_group_via_api["id"])
    assert details["plugin_name"] == "scylla-cluster-tests"


def test_admin_get_tests_includes_created(flask_client, admin_group_via_api, admin_test_via_api):
    resp = flask_client.get(
        f"{ADMIN_PREFIX}/tests/get", query_string={"groupId": admin_group_via_api["id"]}
    )
    assert resp.status_code == 200, resp.data
    body = resp.json
    assert body["status"] == "ok"
    ids = {t["id"] for t in body["response"]}
    assert admin_test_via_api["id"] in ids


def test_admin_get_tests_missing_group_id(flask_client):
    resp = flask_client.get(f"{ADMIN_PREFIX}/tests/get")
    assert resp.status_code == 200
    assert resp.json["status"] == "error"


# ---------------------------------------------------------------------------
# /test/update
# ---------------------------------------------------------------------------

def test_admin_update_test(flask_client, admin_group_via_api, admin_test_via_api):
    payload = {
        "test_id": admin_test_via_api["id"],
        "name": admin_test_via_api["name"] + "_upd",
        "pretty_name": "updated-test-pretty",
        "plugin_name": "driver-matrix-tests",
        "enabled": False,
        "build_system_id": admin_test_via_api["build_system_id"],
        "build_system_url": "http://example.com/job/2",
        "group_id": admin_group_via_api["id"],
    }
    resp = _post(flask_client, f"{ADMIN_PREFIX}/test/update", payload)
    assert resp.status_code == 200, resp.data
    assert resp.json["status"] == "ok"

    details = _test_details(flask_client, admin_test_via_api["id"])
    assert details["pretty_name"] == "updated-test-pretty"
    assert details["plugin_name"] == "driver-matrix-tests"
    assert details["enabled"] is False
    assert details["build_system_url"] == "http://example.com/job/2"


# ---------------------------------------------------------------------------
# /release/test/state/toggle
# ---------------------------------------------------------------------------

def test_admin_toggle_test_enabled(flask_client, admin_test_via_api):
    payload = {"entityId": admin_test_via_api["id"], "state": False}
    resp = _post(flask_client, f"{ADMIN_PREFIX}/release/test/state/toggle", payload)
    assert resp.status_code == 200, resp.data
    assert resp.json["status"] == "ok"
    assert _test_details(flask_client, admin_test_via_api["id"])["enabled"] is False


# ---------------------------------------------------------------------------
# /test/batch_move
# ---------------------------------------------------------------------------

def test_admin_batch_move_tests(flask_client, admin_release, admin_group_via_api,
                                  admin_test_via_api):
    # Create a second group and move the test into it.
    second_group_name = f"adm9_grp2_{time.time_ns()}"
    create_resp = _post(
        flask_client,
        f"{ADMIN_PREFIX}/group/create",
        {
            "group_name": second_group_name,
            "pretty_name": second_group_name,
            "build_system_id": f"bsid2_{time.time_ns()}",
            "release_id": str(admin_release.id),
        },
    )
    assert create_resp.status_code == 200, create_resp.data
    second_group = create_resp.json["response"]["new_group"]

    payload = {"new_group_id": second_group["id"], "tests": [admin_test_via_api["id"]]}
    resp = _post(flask_client, f"{ADMIN_PREFIX}/test/batch_move", payload)
    assert resp.status_code == 200, resp.data
    body = resp.json
    assert body["status"] == "ok"
    assert body["response"]["moved"] is True

    details = _test_details(flask_client, admin_test_via_api["id"])
    assert str(details["group_id"]) == str(second_group["id"])


# ---------------------------------------------------------------------------
# /test/delete + /group/delete
# ---------------------------------------------------------------------------

def test_admin_delete_test(flask_client, admin_test_via_api):
    resp = _post(
        flask_client, f"{ADMIN_PREFIX}/test/delete", {"test_id": admin_test_via_api["id"]}
    )
    assert resp.status_code == 200, resp.data
    body = resp.json
    assert body["status"] == "ok"
    assert body["response"]["deleted"] is True

    miss = flask_client.get(f"{API_PREFIX}/test/{admin_test_via_api['id']}/details")
    assert miss.status_code == 200
    assert miss.json["status"] == "error"


def test_admin_delete_group_cascades_tests(flask_client, admin_group_via_api,
                                            admin_test_via_api):
    payload = {"group_id": admin_group_via_api["id"], "delete_tests": True}
    resp = _post(flask_client, f"{ADMIN_PREFIX}/group/delete", payload)
    assert resp.status_code == 200, resp.data
    body = resp.json
    assert body["status"] == "ok"
    assert body["response"]["deleted"] is True

    miss_group = flask_client.get(f"{API_PREFIX}/group/{admin_group_via_api['id']}/details")
    assert miss_group.json["status"] == "error"
    miss_test = flask_client.get(f"{API_PREFIX}/test/{admin_test_via_api['id']}/details")
    assert miss_test.json["status"] == "error"


def test_admin_delete_group_relocates_tests(flask_client, admin_release, admin_group_via_api,
                                              admin_test_via_api):
    # Create a target group, then delete the source group with delete_tests=False.
    target_name = f"adm9_target_{time.time_ns()}"
    create_resp = _post(
        flask_client,
        f"{ADMIN_PREFIX}/group/create",
        {
            "group_name": target_name,
            "pretty_name": target_name,
            "build_system_id": f"target_bsid_{time.time_ns()}",
            "release_id": str(admin_release.id),
        },
    )
    target = create_resp.json["response"]["new_group"]

    payload = {
        "group_id": admin_group_via_api["id"],
        "delete_tests": False,
        "new_group_id": target["id"],
    }
    resp = _post(flask_client, f"{ADMIN_PREFIX}/group/delete", payload)
    assert resp.status_code == 200, resp.data
    assert resp.json["status"] == "ok"

    details = _test_details(flask_client, admin_test_via_api["id"])
    assert str(details["group_id"]) == str(target["id"])


# ---------------------------------------------------------------------------
# Negative paths
# ---------------------------------------------------------------------------

def test_admin_delete_test_unknown_id_errors(flask_client):
    resp = _post(
        flask_client, f"{ADMIN_PREFIX}/test/delete", {"test_id": str(uuid.uuid4())}
    )
    assert resp.status_code == 200
    assert resp.json["status"] == "error"


def test_admin_create_test_requires_json(flask_client):
    resp = flask_client.post(
        f"{ADMIN_PREFIX}/test/create", data="not-json", content_type="text/plain"
    )
    assert resp.status_code == 200
    assert resp.json["status"] == "error"
