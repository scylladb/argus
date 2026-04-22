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
from datetime import datetime, timedelta

import pytest

from argus.backend.models.web import ArgusRelease, User, UserRoles


API_PREFIX = "/api/v1"


# ---------------------------------------------------------------------------
# Local helpers / fixtures
# ---------------------------------------------------------------------------

def _api_get(flask_client, path: str, **params):
    return flask_client.get(path, query_string=params)


def _api_post(flask_client, path: str, payload: dict):
    return flask_client.post(path, data=json.dumps(payload), content_type="application/json")


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
        name, name, build_system_id=isolated_release.name, release_id=str(isolated_release.id)
    )


@pytest.fixture
def isolated_test(release_manager_service, isolated_release, isolated_group):
    name = f"release_api_iso_test_{time.time_ns()}"
    return release_manager_service.create_test(
        name, name, name, name,
        group_id=str(isolated_group.id), release_id=str(isolated_release.id),
        plugin_name="scylla-cluster-tests",
    )


def _submit_schedule(flask_client, *, release, tests, assignees, comments=None,
                     group_ids=None, groups=None, tag="ci"):
    """Hit POST /release/schedules/submit and return the resulting schedule dict."""
    now = datetime.utcnow()
    payload = {
        "releaseId": str(release.id),
        "start": now.isoformat(),
        "end": (now + timedelta(days=7)).isoformat(),
        "tests": [str(t) for t in tests],
        "groups": [str(g) for g in (groups or [])],
        "assignees": [str(a) for a in assignees],
        "tag": tag,
        "comments": comments,
        "groupIds": group_ids,
    }
    resp = _api_post(flask_client, f"{API_PREFIX}/release/schedules/submit", payload)
    assert resp.status_code == 200, resp.data
    body = resp.json
    assert body["status"] == "ok", body
    return body["response"]


# ---------------------------------------------------------------------------
# /version
# ---------------------------------------------------------------------------

def test_version(flask_client):
    resp = flask_client.get(f"{API_PREFIX}/version")
    assert resp.status_code == 200
    body = resp.json
    assert body["status"] == "ok"
    assert "commit_id" in body["response"]
    assert isinstance(body["response"]["commit_id"], str)
    assert body["response"]["commit_id"]


# ---------------------------------------------------------------------------
# /releases + /release/<id>/details
# ---------------------------------------------------------------------------

def test_list_releases_includes_session_release(flask_client, release):
    resp = flask_client.get(f"{API_PREFIX}/releases")
    assert resp.status_code == 200, resp.data
    body = resp.json
    assert body["status"] == "ok"
    names = {r["name"] for r in body["response"]}
    assert release.name in names


def test_release_details(flask_client, release):
    resp = flask_client.get(f"{API_PREFIX}/release/{release.id}/details")
    assert resp.status_code == 200, resp.data
    body = resp.json
    assert body["status"] == "ok"
    assert body["response"]["id"] == str(release.id)
    assert body["response"]["name"] == release.name


def test_release_details_unknown_id_errors(flask_client):
    resp = flask_client.get(f"{API_PREFIX}/release/{uuid.uuid4()}/details")
    assert resp.status_code == 200
    assert resp.json["status"] == "error"


# ---------------------------------------------------------------------------
# /release/<id>/versions, /images, /pytest/results, /activity
# ---------------------------------------------------------------------------

def test_release_versions_returns_list(flask_client, release):
    resp = flask_client.get(f"{API_PREFIX}/release/{release.id}/versions")
    assert resp.status_code == 200, resp.data
    body = resp.json
    assert body["status"] == "ok"
    assert isinstance(body["response"], list)


def test_release_images_returns_list(flask_client, release):
    resp = flask_client.get(f"{API_PREFIX}/release/{release.id}/images")
    assert resp.status_code == 200, resp.data
    body = resp.json
    assert body["status"] == "ok"
    assert isinstance(body["response"], list)


def test_release_pytest_results_returns_list(flask_client, release):
    resp = flask_client.get(f"{API_PREFIX}/release/{release.id}/pytest/results")
    assert resp.status_code == 200, resp.data
    body = resp.json
    assert body["status"] == "ok"
    assert isinstance(body["response"], list)


def test_release_activity(flask_client, release):
    resp = _api_get(flask_client, f"{API_PREFIX}/release/activity", releaseName=release.name)
    assert resp.status_code == 200, resp.data
    body = resp.json
    assert body["status"] == "ok"
    assert body["response"]["release_id"] == str(release.id)
    assert "events" in body["response"]
    assert "raw_events" in body["response"]


def test_release_activity_missing_name(flask_client):
    resp = flask_client.get(f"{API_PREFIX}/release/activity")
    assert resp.status_code == 200
    assert resp.json["status"] == "error"


# ---------------------------------------------------------------------------
# /release/planner/data, /release/planner/comment/get/test
# ---------------------------------------------------------------------------

def test_release_planner_data(flask_client, release, group, fake_test):
    resp = _api_get(flask_client, f"{API_PREFIX}/release/planner/data", releaseId=str(release.id))
    assert resp.status_code == 200, resp.data
    body = resp.json
    assert body["status"] == "ok"
    response = body["response"]
    assert response["release"]["id"] == str(release.id)
    assert str(group.id) in response["groups"]
    test_ids = {t["id"] for t in response["tests"]}
    assert str(fake_test.id) in test_ids


def test_release_planner_data_missing_id(flask_client):
    resp = flask_client.get(f"{API_PREFIX}/release/planner/data")
    assert resp.status_code == 200
    assert resp.json["status"] == "error"


def test_planner_comment_for_test_without_comment_returns_empty(flask_client, fake_test):
    resp = _api_get(
        flask_client,
        f"{API_PREFIX}/release/planner/comment/get/test",
        id=str(fake_test.id),
    )
    assert resp.status_code == 200, resp.data
    body = resp.json
    assert body["status"] == "ok"
    assert body["response"] == ""


# ---------------------------------------------------------------------------
# /release/schedules*  + /release/assignees/{groups,tests}
# ---------------------------------------------------------------------------

def test_release_schedules_empty_when_no_schedules(flask_client, isolated_release):
    resp = _api_get(
        flask_client, f"{API_PREFIX}/release/schedules", releaseId=str(isolated_release.id)
    )
    assert resp.status_code == 200, resp.data
    body = resp.json
    assert body["status"] == "ok"
    assert body["response"] == {"schedules": []}


def test_release_schedules_missing_release_id(flask_client):
    resp = flask_client.get(f"{API_PREFIX}/release/schedules")
    assert resp.status_code == 200
    assert resp.json["status"] == "error"


def test_release_schedule_submit_and_round_trip(flask_client, isolated_release, isolated_test, saved_user):
    submitted = _submit_schedule(
        flask_client,
        release=isolated_release,
        tests=[isolated_test.id],
        assignees=[saved_user.id],
    )
    schedule_id = submitted["id"]
    assert schedule_id

    resp = _api_get(
        flask_client, f"{API_PREFIX}/release/schedules", releaseId=str(isolated_release.id)
    )
    assert resp.status_code == 200, resp.data
    schedules = resp.json["response"]["schedules"]
    matching = [s for s in schedules if s["id"] == schedule_id]
    assert len(matching) == 1, schedules
    sched = matching[0]
    assert sched["assignees"] == [str(saved_user.id)]
    assert sched["tests"] == [str(isolated_test.id)]


def test_release_schedule_submit_with_comments(flask_client, isolated_release, isolated_group,
                                                isolated_test, saved_user):
    test_id = str(isolated_test.id)
    submitted = _submit_schedule(
        flask_client,
        release=isolated_release,
        tests=[isolated_test.id],
        assignees=[saved_user.id],
        comments={test_id: "scheduled-during-test"},
        group_ids={test_id: str(isolated_group.id)},
    )
    assert submitted["id"]

    resp = _api_get(
        flask_client,
        f"{API_PREFIX}/release/planner/comment/get/test",
        id=test_id,
    )
    assert resp.json["response"] == "scheduled-during-test"


def test_release_schedule_submit_requires_assignees(flask_client, isolated_release, isolated_test):
    payload = {
        "releaseId": str(isolated_release.id),
        "start": datetime.utcnow().isoformat(),
        "end": (datetime.utcnow() + timedelta(days=1)).isoformat(),
        "tests": [str(isolated_test.id)],
        "groups": [],
        "assignees": [],
        "tag": "ci",
    }
    resp = _api_post(flask_client, f"{API_PREFIX}/release/schedules/submit", payload)
    assert resp.status_code == 200
    assert resp.json["status"] == "error"


def test_release_schedule_submit_requires_objects(flask_client, isolated_release, saved_user):
    payload = {
        "releaseId": str(isolated_release.id),
        "start": datetime.utcnow().isoformat(),
        "end": (datetime.utcnow() + timedelta(days=1)).isoformat(),
        "tests": [],
        "groups": [],
        "assignees": [str(saved_user.id)],
        "tag": "ci",
    }
    resp = _api_post(flask_client, f"{API_PREFIX}/release/schedules/submit", payload)
    assert resp.status_code == 200
    assert resp.json["status"] == "error"


def test_release_schedule_comment_update(flask_client, isolated_release, isolated_group, isolated_test):
    test_id = str(isolated_test.id)
    payload = {
        "releaseId": str(isolated_release.id),
        "groupId": str(isolated_group.id),
        "testId": test_id,
        "newComment": "manually-set",
    }
    resp = _api_post(flask_client, f"{API_PREFIX}/release/schedules/comment/update", payload)
    assert resp.status_code == 200, resp.data
    assert resp.json["status"] == "ok"
    assert resp.json["response"]["newComment"] == "manually-set"

    get_resp = _api_get(
        flask_client,
        f"{API_PREFIX}/release/planner/comment/get/test",
        id=test_id,
    )
    assert get_resp.json["response"] == "manually-set"


def test_release_schedule_assignee_update(flask_client, isolated_release, isolated_test, saved_user,
                                           release_manager_service):
    submitted = _submit_schedule(
        flask_client,
        release=isolated_release,
        tests=[isolated_test.id],
        assignees=[saved_user.id],
    )
    schedule_id = submitted["id"]

    new_user = User(
        id=uuid.uuid4(),
        username=f"new_assignee_{uuid.uuid4().hex[:8]}",
        full_name="New Assignee",
        email=f"new_assignee_{uuid.uuid4().hex[:8]}@scylladb.com",
        password="x",
        roles=[UserRoles.User.value],
    )
    new_user.save()

    payload = {
        "releaseId": str(isolated_release.id),
        "scheduleId": schedule_id,
        "newAssignees": [str(new_user.id)],
    }
    resp = _api_post(flask_client, f"{API_PREFIX}/release/schedules/assignee/update", payload)
    assert resp.status_code == 200, resp.data
    assert resp.json["status"] == "ok"
    assert resp.json["response"]["newAssignees"] == [str(new_user.id)]

    # Verify via GET
    get_resp = _api_get(
        flask_client, f"{API_PREFIX}/release/schedules", releaseId=str(isolated_release.id)
    )
    schedules = get_resp.json["response"]["schedules"]
    sched = next(s for s in schedules if s["id"] == schedule_id)
    assert sched["assignees"] == [str(new_user.id)]


def test_release_schedule_delete(flask_client, isolated_release, isolated_test, saved_user):
    submitted = _submit_schedule(
        flask_client,
        release=isolated_release,
        tests=[isolated_test.id],
        assignees=[saved_user.id],
    )
    schedule_id = submitted["id"]

    payload = {
        "releaseId": str(isolated_release.id),
        "scheduleId": schedule_id,
        "deleteComments": False,
    }
    resp = _api_post(flask_client, f"{API_PREFIX}/release/schedules/delete", payload)
    assert resp.status_code == 200, resp.data
    body = resp.json
    assert body["status"] == "ok"
    assert body["response"]["result"] == "deleted"

    get_resp = _api_get(
        flask_client, f"{API_PREFIX}/release/schedules", releaseId=str(isolated_release.id)
    )
    schedule_ids = [s["id"] for s in get_resp.json["response"]["schedules"]]
    assert schedule_id not in schedule_ids


def test_release_schedule_update(flask_client, isolated_release, isolated_test, saved_user,
                                  release_manager_service, isolated_group):
    submitted = _submit_schedule(
        flask_client,
        release=isolated_release,
        tests=[isolated_test.id],
        assignees=[saved_user.id],
    )
    schedule_id = submitted["id"]

    second_test = release_manager_service.create_test(
        f"upd_test_{time.time_ns()}",
        f"upd_test_{time.time_ns()}",
        f"upd_test_{time.time_ns()}",
        f"upd_test_{time.time_ns()}",
        group_id=str(isolated_group.id),
        release_id=str(isolated_release.id),
        plugin_name="scylla-cluster-tests",
    )

    payload = {
        "release_id": str(isolated_release.id),
        "schedule_id": schedule_id,
        "assignee": str(saved_user.id),
        "old_tests": [str(isolated_test.id)],
        "new_tests": [str(second_test.id)],
        "comments": {},
    }
    resp = _api_post(flask_client, f"{API_PREFIX}/release/schedules/update", payload)
    assert resp.status_code == 200, resp.data
    assert resp.json["status"] == "ok"
    assert resp.json["response"] is True

    get_resp = _api_get(
        flask_client, f"{API_PREFIX}/release/schedules", releaseId=str(isolated_release.id)
    )
    sched = next(s for s in get_resp.json["response"]["schedules"] if s["id"] == schedule_id)
    assert str(second_test.id) in [str(t) for t in sched["tests"]]
    assert str(isolated_test.id) not in [str(t) for t in sched["tests"]]


def test_release_assignees_groups_returns_dict(flask_client, isolated_release, isolated_group,
                                                 isolated_test, saved_user):
    _submit_schedule(
        flask_client,
        release=isolated_release,
        tests=[],
        groups=[isolated_group.id],
        assignees=[saved_user.id],
    )
    resp = _api_get(
        flask_client,
        f"{API_PREFIX}/release/assignees/groups",
        releaseId=str(isolated_release.id),
    )
    assert resp.status_code == 200, resp.data
    body = resp.json
    assert body["status"] == "ok"
    assert isinstance(body["response"], dict)
    assert str(isolated_group.id) in body["response"]
    assert str(saved_user.id) in body["response"][str(isolated_group.id)]


def test_release_assignees_groups_missing_release(flask_client):
    resp = flask_client.get(f"{API_PREFIX}/release/assignees/groups")
    assert resp.status_code == 200
    assert resp.json["status"] == "error"


def test_release_assignees_tests_returns_dict(flask_client, isolated_release, isolated_group,
                                                isolated_test, saved_user):
    _submit_schedule(
        flask_client,
        release=isolated_release,
        tests=[isolated_test.id],
        assignees=[saved_user.id],
    )
    resp = _api_get(
        flask_client,
        f"{API_PREFIX}/release/assignees/tests",
        groupId=str(isolated_group.id),
    )
    assert resp.status_code == 200, resp.data
    body = resp.json
    assert body["status"] == "ok"
    assert str(isolated_test.id) in body["response"]
    assert str(saved_user.id) in body["response"][str(isolated_test.id)]


def test_release_assignees_tests_missing_group(flask_client):
    resp = flask_client.get(f"{API_PREFIX}/release/assignees/tests")
    assert resp.status_code == 200
    assert resp.json["status"] == "error"


# ---------------------------------------------------------------------------
# /release/stats/v2
# ---------------------------------------------------------------------------

def test_release_stats_v2_returns_dict(flask_client, release):
    resp = _api_get(
        flask_client,
        f"{API_PREFIX}/release/stats/v2",
        release=release.name,
        limited=0,
        force=1,
        includeNoVersion=1,
    )
    assert resp.status_code == 200, resp.data
    body = resp.json
    assert body["status"] == "ok"
    assert isinstance(body["response"], dict)


# ---------------------------------------------------------------------------
# /release/create
# ---------------------------------------------------------------------------

def test_release_create_creates_release_with_groups_and_tests(flask_client):
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
    resp = _api_post(flask_client, f"{API_PREFIX}/release/create", payload)
    assert resp.status_code == 200, resp.data
    body = resp.json
    assert body["status"] == "ok"
    assert body["response"][rel_name]["groups"][grp_name]["status"] == "created"
    assert body["response"][rel_name]["groups"][grp_name]["tests"][test_name] == "created"

    listing = flask_client.get(f"{API_PREFIX}/releases").json["response"]
    assert rel_name in {r["name"] for r in listing}


def test_release_create_duplicate_returns_error_per_release(flask_client, release):
    payload = {release.name: {"groups": {}}}
    resp = _api_post(flask_client, f"{API_PREFIX}/release/create", payload)
    assert resp.status_code == 200, resp.data
    body = resp.json
    assert body["status"] == "ok"
    assert body["response"][release.name]["status"] == "error"


# ---------------------------------------------------------------------------
# /groups, /tests, /group/<id>/details, /test/<id>/details
# ---------------------------------------------------------------------------

def test_list_groups_for_release(flask_client, release, group):
    resp = _api_get(flask_client, f"{API_PREFIX}/groups", releaseId=str(release.id))
    assert resp.status_code == 200, resp.data
    body = resp.json
    assert body["status"] == "ok"
    ids = {g["id"] for g in body["response"]}
    assert str(group.id) in ids


def test_list_groups_missing_release_id(flask_client):
    resp = flask_client.get(f"{API_PREFIX}/groups")
    assert resp.status_code == 200
    assert resp.json["status"] == "error"


def test_list_tests_for_group(flask_client, group, fake_test):
    resp = _api_get(flask_client, f"{API_PREFIX}/tests", groupId=str(group.id))
    assert resp.status_code == 200, resp.data
    body = resp.json
    assert body["status"] == "ok"
    ids = {t["id"] for t in body["response"]}
    assert str(fake_test.id) in ids


def test_list_tests_missing_group_id(flask_client):
    resp = flask_client.get(f"{API_PREFIX}/tests")
    assert resp.status_code == 200
    assert resp.json["status"] == "error"


def test_group_details(flask_client, group):
    resp = flask_client.get(f"{API_PREFIX}/group/{group.id}/details")
    assert resp.status_code == 200, resp.data
    body = resp.json
    assert body["status"] == "ok"
    assert body["response"]["id"] == str(group.id)
    assert body["response"]["name"] == group.name


def test_test_details(flask_client, fake_test):
    resp = flask_client.get(f"{API_PREFIX}/test/{fake_test.id}/details")
    assert resp.status_code == 200, resp.data
    body = resp.json
    assert body["status"] == "ok"
    assert body["response"]["id"] == str(fake_test.id)
    assert body["response"]["name"] == fake_test.name


# ---------------------------------------------------------------------------
# /test-info, /test/<id>/set_plugin
# ---------------------------------------------------------------------------

def test_test_info(flask_client, release, group, fake_test):
    resp = _api_get(flask_client, f"{API_PREFIX}/test-info", testId=str(fake_test.id))
    assert resp.status_code == 200, resp.data
    body = resp.json
    assert body["status"] == "ok"
    assert body["response"]["test"]["id"] == str(fake_test.id)
    assert body["response"]["group"]["id"] == str(group.id)
    assert body["response"]["release"]["id"] == str(release.id)


def test_test_info_missing_id(flask_client):
    resp = flask_client.get(f"{API_PREFIX}/test-info")
    assert resp.status_code == 200
    assert resp.json["status"] == "error"


def test_set_test_plugin_round_trip(flask_client, isolated_test):
    payload = {"plugin_name": "driver-matrix-tests"}
    resp = _api_post(flask_client, f"{API_PREFIX}/test/{isolated_test.id}/set_plugin", payload)
    assert resp.status_code == 200, resp.data
    body = resp.json
    assert body["status"] == "ok"
    assert body["response"]["plugin_name"] == "driver-matrix-tests"

    get_resp = flask_client.get(f"{API_PREFIX}/test/{isolated_test.id}/details")
    assert get_resp.json["response"]["plugin_name"] == "driver-matrix-tests"
