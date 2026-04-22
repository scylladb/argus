"""Controller-level integration tests for release endpoints in
``argus/backend/controller/admin_api.py``.

URL prefix: ``/admin/api/v1`` (admin_api blueprint nested under admin).

Scope (iteration 8 of the controller coverage matrix):

- ``POST /admin/api/v1/release/create``
- ``POST /admin/api/v1/release/set_perpetual``
- ``POST /admin/api/v1/release/set_state``
- ``POST /admin/api/v1/release/set_dormant``
- ``POST /admin/api/v1/release/edit``
- ``POST /admin/api/v1/release/delete``
- ``GET  /admin/api/v1/releases/get``
"""

import json
import time
import uuid

import pytest


ADMIN_PREFIX = "/admin/api/v1"
API_PREFIX = "/api/v1"


def _post(flask_client, path: str, payload: dict):
    return flask_client.post(path, data=json.dumps(payload), content_type="application/json")


def _get_release_details(flask_client, release_id: str) -> dict:
    resp = flask_client.get(f"{API_PREFIX}/release/{release_id}/details")
    assert resp.status_code == 200, resp.data
    body = resp.json
    assert body["status"] == "ok", body
    return body["response"]


@pytest.fixture
def admin_release(flask_client):
    name = f"admin_iter8_{time.time_ns()}"
    payload = {"release_name": name, "pretty_name": name, "perpetual": False}
    resp = _post(flask_client, f"{ADMIN_PREFIX}/release/create", payload)
    assert resp.status_code == 200, resp.data
    body = resp.json
    assert body["status"] == "ok"
    return body["response"]["new_release"]


# ---------------------------------------------------------------------------
# /release/create
# ---------------------------------------------------------------------------

def test_admin_create_release_round_trip(flask_client):
    name = f"create_release_{time.time_ns()}"
    payload = {"release_name": name, "pretty_name": "Pretty Name", "perpetual": True}
    resp = _post(flask_client, f"{ADMIN_PREFIX}/release/create", payload)
    assert resp.status_code == 200, resp.data
    body = resp.json
    assert body["status"] == "ok"
    new_release = body["response"]["new_release"]
    assert new_release["name"] == name
    assert new_release["pretty_name"] == "Pretty Name"
    assert new_release["perpetual"] is True

    details = _get_release_details(flask_client, new_release["id"])
    assert details["name"] == name
    assert details["perpetual"] is True


def test_admin_create_release_duplicate_errors(flask_client, admin_release):
    payload = {
        "release_name": admin_release["name"],
        "pretty_name": admin_release["name"],
        "perpetual": False,
    }
    resp = _post(flask_client, f"{ADMIN_PREFIX}/release/create", payload)
    assert resp.status_code == 200
    assert resp.json["status"] == "error"


# ---------------------------------------------------------------------------
# /release/set_perpetual, /release/set_state, /release/set_dormant
# ---------------------------------------------------------------------------

def test_admin_set_release_perpetual(flask_client, admin_release):
    payload = {"release_id": admin_release["id"], "perpetual": True}
    resp = _post(flask_client, f"{ADMIN_PREFIX}/release/set_perpetual", payload)
    assert resp.status_code == 200, resp.data
    assert resp.json["status"] == "ok"
    assert _get_release_details(flask_client, admin_release["id"])["perpetual"] is True

    resp = _post(
        flask_client,
        f"{ADMIN_PREFIX}/release/set_perpetual",
        {"release_id": admin_release["id"], "perpetual": False},
    )
    assert resp.json["status"] == "ok"
    assert _get_release_details(flask_client, admin_release["id"])["perpetual"] is False


def test_admin_set_release_state(flask_client, admin_release):
    payload = {"release_id": admin_release["id"], "state": False}
    resp = _post(flask_client, f"{ADMIN_PREFIX}/release/set_state", payload)
    assert resp.status_code == 200, resp.data
    assert resp.json["status"] == "ok"
    assert _get_release_details(flask_client, admin_release["id"])["enabled"] is False


def test_admin_set_release_dormant(flask_client, admin_release):
    payload = {"release_id": admin_release["id"], "dormant": True}
    resp = _post(flask_client, f"{ADMIN_PREFIX}/release/set_dormant", payload)
    assert resp.status_code == 200, resp.data
    assert resp.json["status"] == "ok"
    assert _get_release_details(flask_client, admin_release["id"])["dormant"] is True


# ---------------------------------------------------------------------------
# /release/edit
# ---------------------------------------------------------------------------

def test_admin_edit_release(flask_client, admin_release):
    payload = {
        "id": admin_release["id"],
        "pretty_name": "edited-pretty",
        "description": "edited-desc",
        "valid_version_regex": r"^\d+\.\d+$",
        "enabled": False,
        "perpetual": True,
        "dormant": True,
    }
    resp = _post(flask_client, f"{ADMIN_PREFIX}/release/edit", payload)
    assert resp.status_code == 200, resp.data
    body = resp.json
    assert body["status"] == "ok"
    assert body["response"]["updated"] is True

    details = _get_release_details(flask_client, admin_release["id"])
    assert details["pretty_name"] == "edited-pretty"
    assert details["description"] == "edited-desc"
    assert details["valid_version_regex"] == r"^\d+\.\d+$"
    assert details["enabled"] is False
    assert details["perpetual"] is True
    assert details["dormant"] is True


def test_admin_edit_release_unknown_id_errors(flask_client):
    payload = {
        "id": str(uuid.uuid4()),
        "pretty_name": "x", "description": "x", "valid_version_regex": None,
        "enabled": True, "perpetual": False, "dormant": False,
    }
    resp = _post(flask_client, f"{ADMIN_PREFIX}/release/edit", payload)
    assert resp.status_code == 200
    assert resp.json["status"] == "error"


# ---------------------------------------------------------------------------
# /release/delete
# ---------------------------------------------------------------------------

def test_admin_delete_release(flask_client, admin_release):
    resp = _post(flask_client, f"{ADMIN_PREFIX}/release/delete",
                 {"releaseId": admin_release["id"]})
    assert resp.status_code == 200, resp.data
    body = resp.json
    assert body["status"] == "ok"
    assert body["response"]["deleted"] is True

    # Verify gone via details endpoint (raises DoesNotExist → error envelope)
    miss = flask_client.get(f"{API_PREFIX}/release/{admin_release['id']}/details")
    assert miss.status_code == 200
    assert miss.json["status"] == "error"


def test_admin_delete_release_unknown_id_errors(flask_client):
    resp = _post(flask_client, f"{ADMIN_PREFIX}/release/delete",
                 {"releaseId": str(uuid.uuid4())})
    assert resp.status_code == 200
    assert resp.json["status"] == "error"


# ---------------------------------------------------------------------------
# /releases/get
# ---------------------------------------------------------------------------

def test_admin_get_releases_includes_created(flask_client, admin_release):
    resp = flask_client.get(f"{ADMIN_PREFIX}/releases/get")
    assert resp.status_code == 200, resp.data
    body = resp.json
    assert body["status"] == "ok"
    assert isinstance(body["response"], list)
    names = {r["name"] for r in body["response"]}
    assert admin_release["name"] in names


# ---------------------------------------------------------------------------
# Content-Type / body validation
# ---------------------------------------------------------------------------

def test_admin_create_release_requires_json_content_type(flask_client):
    resp = flask_client.post(
        f"{ADMIN_PREFIX}/release/create", data="not-json", content_type="text/plain"
    )
    assert resp.status_code == 200
    assert resp.json["status"] == "error"
