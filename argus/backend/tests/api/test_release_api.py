"""Controller-level integration tests for release/group/test endpoints exposed by
``argus/backend/controller/api.py``.

Scope (iteration 5 of the controller coverage matrix):

- ``GET  /api/v1/version``
- ``GET  /api/v1/releases``
- ``GET  /api/v1/release/<id>/details``
- ``GET  /api/v1/release/<id>/versions``
- ``GET  /api/v1/release/<id>/images``
- ``GET  /api/v1/release/<id>/pytest/results``
- ``GET  /api/v1/release/activity?releaseName=``
- ``GET  /api/v1/release/planner/data?releaseId=``
- ``GET  /api/v1/release/planner/comment/get/test?id=``
- ``GET  /api/v1/release/schedules?releaseId=``
- ``POST /api/v1/release/schedules/submit``
- ``POST /api/v1/release/schedules/update``
- ``POST /api/v1/release/schedules/delete``
- ``POST /api/v1/release/schedules/comment/update``
- ``POST /api/v1/release/schedules/assignee/update``
- ``GET  /api/v1/release/assignees/groups``
- ``GET  /api/v1/release/assignees/tests``
- ``GET  /api/v1/release/stats/v2``
- ``POST /api/v1/release/create``
- ``GET  /api/v1/groups?releaseId=``
- ``GET  /api/v1/tests?groupId=``
- ``GET  /api/v1/group/<id>/details``
- ``GET  /api/v1/test/<id>/details``
- ``POST /api/v1/test/<id>/set_plugin``
- ``GET  /api/v1/test-info?testId=``

Verification is JSON-first (paired GET endpoints).  All mutations create
unique IDs/names so tests stay isolated.
"""

import json
import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from argus.backend.models.web import ArgusRelease, User, UserRoles


API_PREFIX = "/api/v1"


# ---------------------------------------------------------------------------
# Local helpers / fixtures
# ---------------------------------------------------------------------------

def _api_get(api_client, path: str, **params):
    return api_client.get(path, params=params)


def _api_post(api_client, path: str, payload: dict):
    return api_client.post(path, json=payload)


@pytest.fixture
def saved_user():
    """Create a real ``User`` row so assignee mutations have a valid receiver."""
    user = User(
        id=uuid.uuid4(),
        username=f"release_api_user_{uuid.uuid4().hex[:8]}",
        full_name="Release API User",
        email=f"release_api_{uuid.uuid4().hex[:8]}@scylladb.com",
        password="test_password",
        roles=[UserRoles.User.value],
    )
    user.save()
    return user


@pytest.fixture
def isolated_release(release_manager_service):
    """Function-scoped release used by mutation tests so they cannot pollute
    the session-scoped ``release`` fixture (which is shared with read-only
    assertions)."""
    name = f"release_api_iso_{time.time_ns()}"
    return release_manager_service.create_release(name, name, False)


@pytest.fixture
def isolated_group(release_manager_service, isolated_release):
    name = f"release_api_iso_group_{time.time_ns()}"
    return release_manager_service.create_group(
        name, name, build_system_id=isolated_release.name, release_id=str(
            isolated_release.id)
    )


@pytest.fixture
def isolated_test(release_manager_service, isolated_release, isolated_group):
    name = f"release_api_iso_test_{time.time_ns()}"
    return release_manager_service.create_test(
        name, name, name, name,
        group_id=str(isolated_group.id), release_id=str(isolated_release.id),
        plugin_name="scylla-cluster-tests",
    )


def test_version(api_client):
    resp = api_client.get(f"{API_PREFIX}/version")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "commit_id" in body["response"]
    assert isinstance(body["response"]["commit_id"], str)
    assert body["response"]["commit_id"]


# ---------------------------------------------------------------------------
# /releases + /release/<id>/details
# ---------------------------------------------------------------------------

def test_list_releases_includes_session_release(api_client, release):
    resp = api_client.get(f"{API_PREFIX}/releases")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["status"] == "ok"
    names = {r["name"] for r in body["response"]}
    assert release.name in names


def test_release_details(api_client, release):
    resp = api_client.get(f"{API_PREFIX}/release/{release.id}/details")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["status"] == "ok"
    assert body["response"]["id"] == str(release.id)
    assert body["response"]["name"] == release.name


def test_release_details_unknown_id_errors(api_client):
    resp = api_client.get(f"{API_PREFIX}/release/{uuid.uuid4()}/details")
    assert resp.status_code == 200
    assert resp.json()["status"] == "error"


# ---------------------------------------------------------------------------
# /release/<id>/versions, /images, /pytest/results, /activity
# ---------------------------------------------------------------------------

def test_release_versions_returns_list(api_client, release):
    resp = api_client.get(f"{API_PREFIX}/release/{release.id}/versions")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["status"] == "ok"
    assert isinstance(body["response"], list)


def test_release_images_returns_list(api_client, release):
    resp = api_client.get(f"{API_PREFIX}/release/{release.id}/images")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["status"] == "ok"
    assert isinstance(body["response"], list)


def test_release_pytest_results_returns_list(api_client, release):
    resp = api_client.get(
        f"{API_PREFIX}/release/{release.id}/pytest/results")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["status"] == "ok"
    assert isinstance(body["response"], list)


def test_release_activity(api_client, release):
    resp = _api_get(api_client, f"{
                    API_PREFIX}/release/activity", releaseName=release.name)
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["status"] == "ok"
    assert body["response"]["release_id"] == str(release.id)
    assert "events" in body["response"]
    assert "raw_events" in body["response"]


def test_release_activity_missing_name(api_client):
    resp = api_client.get(f"{API_PREFIX}/release/activity")
    assert resp.status_code == 200
    assert resp.json()["status"] == "error"


# ---------------------------------------------------------------------------
# /release/planner/data, /release/planner/comment/get/test
# ---------------------------------------------------------------------------

def test_release_planner_data(api_client, release, group, fake_test):
    resp = _api_get(api_client, f"{
                    API_PREFIX}/release/planner/data", releaseId=str(release.id))
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["status"] == "ok"
    response = body["response"]
    assert response["release"]["id"] == str(release.id)
    assert str(group.id) in response["groups"]
    test_ids = {t["id"] for t in response["tests"]}
    assert str(fake_test.id) in test_ids


def test_release_planner_data_missing_id(api_client):
    resp = api_client.get(f"{API_PREFIX}/release/planner/data")
    assert resp.status_code == 200
    assert resp.json()["status"] == "error"


def test_planner_comment_for_test_without_comment_returns_empty(api_client, fake_test):
    resp = _api_get(
        api_client,
        f"{API_PREFIX}/release/planner/comment/get/test",
        id=str(fake_test.id),
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["status"] == "ok"
    assert body["response"] == ""


# ---------------------------------------------------------------------------
# /release/schedules*  + /release/assignees/{groups,tests}
# ---------------------------------------------------------------------------

def test_release_schedules_empty_when_no_schedules(api_client, isolated_release):
    resp = _api_get(
        api_client, f"{API_PREFIX}/release/schedules", releaseId=str(isolated_release.id)
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["status"] == "ok"
    assert body["response"] == {"schedules": []}


def test_release_schedules_missing_release_id(api_client):
    resp = api_client.get(f"{API_PREFIX}/release/schedules")
    assert resp.status_code == 200
    assert resp.json()["status"] == "error"


def test_release_schedule_comment_update(api_client, isolated_release, isolated_group, isolated_test):
    test_id = str(isolated_test.id)
    payload = {
        "releaseId": str(isolated_release.id),
        "groupId": str(isolated_group.id),
        "testId": test_id,
        "newComment": "manually-set",
    }
    resp = _api_post(api_client, f"{
                     API_PREFIX}/release/schedules/comment/update", payload)
    assert resp.status_code == 200, resp.content
    assert resp.json()["status"] == "ok"
    assert resp.json()["response"]["newComment"] == "manually-set"

    get_resp = _api_get(
        api_client,
        f"{API_PREFIX}/release/planner/comment/get/test",
        id=test_id,
    )
    assert get_resp.json()["response"] == "manually-set"


def test_release_assignees_tests_missing_group(api_client):
    resp = api_client.get(f"{API_PREFIX}/release/assignees/tests")
    assert resp.status_code == 200
    assert resp.json()["status"] == "error"


# ---------------------------------------------------------------------------
# /release/stats/v2
# ---------------------------------------------------------------------------

def test_release_stats_v2_returns_dict(api_client, release):
    resp = _api_get(
        api_client,
        f"{API_PREFIX}/release/stats/v2",
        release=release.name,
        limited=0,
        force=1,
        includeNoVersion=1,
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["status"] == "ok"
    assert isinstance(body["response"], dict)


# ---------------------------------------------------------------------------
# /release/create
# ---------------------------------------------------------------------------

def test_release_create_creates_release_with_groups_and_tests(api_client):
    rel_name = f"created_release_{time.time_ns()}"
    grp_name = f"created_group_{time.time_ns()}"
    test_name = f"created_test_{time.time_ns()}"
    payload = {
        rel_name: {
            "groups": {
                grp_name: {
                    "pretty_name": grp_name,
                    "tests": [test_name],
                }
            }
        }
    }
    resp = _api_post(api_client, f"{API_PREFIX}/release/create", payload)
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["status"] == "ok"
    assert body["response"][rel_name]["groups"][grp_name]["status"] == "created"
    assert body["response"][rel_name]["groups"][grp_name]["tests"][test_name] == "created"

    listing = api_client.get(f"{API_PREFIX}/releases").json()["response"]
    assert rel_name in {r["name"] for r in listing}


def test_release_create_duplicate_returns_error_per_release(api_client, release):
    payload = {release.name: {"groups": {}}}
    resp = _api_post(api_client, f"{API_PREFIX}/release/create", payload)
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["status"] == "ok"
    assert body["response"][release.name]["status"] == "error"


# ---------------------------------------------------------------------------
# /groups, /tests, /group/<id>/details, /test/<id>/details
# ---------------------------------------------------------------------------

def test_list_groups_for_release(api_client, release, group):
    resp = _api_get(api_client, f"{
                    API_PREFIX}/groups", releaseId=str(release.id))
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["status"] == "ok"
    ids = {g["id"] for g in body["response"]}
    assert str(group.id) in ids


def test_list_groups_missing_release_id(api_client):
    resp = api_client.get(f"{API_PREFIX}/groups")
    assert resp.status_code == 200
    assert resp.json()["status"] == "error"


def test_list_tests_for_group(api_client, group, fake_test):
    resp = _api_get(api_client, f"{API_PREFIX}/tests", groupId=str(group.id))
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["status"] == "ok"
    ids = {t["id"] for t in body["response"]}
    assert str(fake_test.id) in ids


def test_list_tests_missing_group_id(api_client):
    resp = api_client.get(f"{API_PREFIX}/tests")
    assert resp.status_code == 200
    assert resp.json()["status"] == "error"


def test_group_details(api_client, group):
    resp = api_client.get(f"{API_PREFIX}/group/{group.id}/details")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["status"] == "ok"
    assert body["response"]["id"] == str(group.id)
    assert body["response"]["name"] == group.name


def test_test_details(api_client, fake_test):
    resp = api_client.get(f"{API_PREFIX}/test/{fake_test.id}/details")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["status"] == "ok"
    assert body["response"]["id"] == str(fake_test.id)
    assert body["response"]["name"] == fake_test.name


# ---------------------------------------------------------------------------
# /test-info, /test/<id>/set_plugin
# ---------------------------------------------------------------------------

def test_test_info(api_client, release, group, fake_test):
    resp = _api_get(api_client, f"{
                    API_PREFIX}/test-info", testId=str(fake_test.id))
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["status"] == "ok"
    assert body["response"]["test"]["id"] == str(fake_test.id)
    assert body["response"]["group"]["id"] == str(group.id)
    assert body["response"]["release"]["id"] == str(release.id)


def test_test_info_missing_id(api_client):
    resp = api_client.get(f"{API_PREFIX}/test-info")
    assert resp.status_code == 200
    assert resp.json()["status"] == "error"


def test_set_test_plugin_round_trip(api_client, isolated_test):
    payload = {"plugin_name": "driver-matrix-tests"}
    resp = _api_post(api_client, f"{
                     API_PREFIX}/test/{isolated_test.id}/set_plugin", payload)
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["status"] == "ok"
    assert body["response"]["plugin_name"] == "driver-matrix-tests"

    get_resp = api_client.get(
        f"{API_PREFIX}/test/{isolated_test.id}/details")
    assert get_resp.json()["response"]["plugin_name"] == "driver-matrix-tests"
