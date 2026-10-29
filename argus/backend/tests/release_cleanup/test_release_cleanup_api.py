"""Removal of groups, tests and runs on a user-editable release.

- ``DELETE /api/v1/group/{group_id}``
- ``DELETE /api/v1/test/{test_id}``
- ``DELETE /api/v1/test/{test_id}/run/{run_id}``
"""

import time
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from argus.backend.tests.util import client_post

ADMIN_PREFIX = "/admin/api/v1"
API_PREFIX = "/api/v1"
SCT = "scylla-cluster-tests"


@pytest.fixture
async def cleanup_release(release_manager_service):
    name = f"cleanup_rel_{time.time_ns()}"
    return await release_manager_service.create_release(name, name, False)


@pytest.fixture
async def cleanup_group(release_manager_service, cleanup_release):
    name = f"cleanup_grp_{time.time_ns()}"
    return await release_manager_service.create_group(name, name, name, cleanup_release.id)


async def _make_test(release_manager_service, group, release, plugin_name=SCT):
    name = f"cleanup_test_{uuid4().hex}"
    return await release_manager_service.create_test(name, name, name, f"http://ci.example.com/job/{name}/",
                                                     group.id, release.id, plugin_name)


@pytest.fixture
async def cleanup_test(release_manager_service, cleanup_group, cleanup_release):
    return await _make_test(release_manager_service, cleanup_group, cleanup_release)


@pytest.fixture
async def other_test(release_manager_service, cleanup_group, cleanup_release):
    return await _make_test(release_manager_service, cleanup_group, cleanup_release)


@pytest.fixture
async def generic_cleanup_test(release_manager_service, cleanup_group, cleanup_release):
    return await _make_test(release_manager_service, cleanup_group, cleanup_release, plugin_name="generic")


def _mark_editable(api_client, release, user_editable=True):
    resp = client_post(api_client, f"{ADMIN_PREFIX}/release/set_user_editable",
                       {"release_id": str(release.id), "user_editable": user_editable})
    assert resp.json()["status"] == "ok", resp.text


def _submit_sct_run(api_client, test, build_number=1) -> str:
    run_id = str(uuid4())
    payload = {
        "run_id": run_id,
        "job_name": test.build_system_id,
        "job_url": f"{test.build_system_url}{build_number}/",
        "started_by": "cleanup_user",
        "commit_id": "deadbeef",
        "origin_url": "http://example.com/repo.git",
        "branch_name": "main",
        "sct_config": {"cluster_backend": "aws", "n_db_nodes": "3"},
        "schema_version": "v8",
    }
    resp = api_client.post(f"{API_PREFIX}/client/testrun/{SCT}/submit", json=payload)
    assert resp.json()["status"] == "ok", resp.text
    return run_id


def _submit_generic_run(api_client, test) -> str:
    run_id = str(uuid4())
    payload = {
        "run_id": run_id,
        "build_id": test.build_system_id,
        "build_url": f"{test.build_system_url}1/",
        "started_by": "cleanup_user",
        "scylla_version": None,
        "sub_type": "pytest",
    }
    resp = api_client.post(f"{API_PREFIX}/client/testrun/generic/submit", json=payload)
    assert resp.json()["status"] == "ok", resp.text
    return run_id


def _post_comment(api_client, test, run_id):
    resp = client_post(api_client, f"{API_PREFIX}/test/{test.id}/run/{run_id}/comments/submit",
                       {"message": "to be removed", "reactions": {}, "mentions": []})
    assert resp.json()["status"] == "ok", resp.text


def _post_sct_event(api_client, run_id):
    event = {
        "run_id": run_id,
        "severity": "NORMAL",
        "ts": datetime.now(tz=UTC).timestamp(),
        "message": "cleanup event",
        "event_type": "InfoEvent",
    }
    resp = api_client.post(f"{API_PREFIX}/client/sct/{run_id}/event/submit", json={"data": [event]})
    assert resp.json()["status"] == "ok", resp.text


def _run_ids(api_client, test) -> set[str]:
    resp = api_client.get(f"{API_PREFIX}/test/{test.id}/runs")
    assert resp.json()["status"] == "ok", resp.text
    return {run["id"] for run in resp.json()["response"]}


def _run_exists(api_client, run_type, run_id) -> bool:
    resp = api_client.get(f"{API_PREFIX}/client/testrun/{run_type}/{run_id}/get")
    assert resp.json()["status"] == "ok", resp.text
    return resp.json()["response"] is not None


def _entity_exists(api_client, kind, entity_id) -> bool:
    resp = api_client.get(f"{API_PREFIX}/{kind}/{entity_id}/details")
    return resp.json()["status"] == "ok"


def _sct_event_count(api_client, run_id) -> int:
    resp = api_client.get(f"{API_PREFIX}/client/sct/{run_id}/events/NORMAL/count")
    assert resp.json()["status"] == "ok", resp.text
    return resp.json()["response"]


def test_delete_run_is_refused_while_the_release_is_not_user_editable(api_client, cleanup_test):
    run_id = _submit_sct_run(api_client, cleanup_test)

    resp = api_client.delete(f"{API_PREFIX}/test/{cleanup_test.id}/run/{run_id}")

    assert resp.status_code == 200
    assert resp.json()["status"] == "error"
    assert "not user editable" in resp.json()["response"]["arguments"][0]
    assert run_id in _run_ids(api_client, cleanup_test)


def test_delete_test_is_refused_while_the_release_is_not_user_editable(api_client, cleanup_test):
    run_id = _submit_sct_run(api_client, cleanup_test)

    resp = api_client.delete(f"{API_PREFIX}/test/{cleanup_test.id}")

    assert resp.json()["status"] == "error"
    assert _entity_exists(api_client, "test", cleanup_test.id)
    assert run_id in _run_ids(api_client, cleanup_test)


def test_delete_group_is_refused_while_the_release_is_not_user_editable(api_client, cleanup_group, cleanup_test):
    resp = api_client.delete(f"{API_PREFIX}/group/{cleanup_group.id}")

    assert resp.json()["status"] == "error"
    assert _entity_exists(api_client, "group", cleanup_group.id)
    assert _entity_exists(api_client, "test", cleanup_test.id)


def test_delete_run_removes_the_run_and_its_rows(api_client, cleanup_release, cleanup_test):
    _mark_editable(api_client, cleanup_release)
    run_id = _submit_sct_run(api_client, cleanup_test)
    kept_run_id = _submit_sct_run(api_client, cleanup_test, build_number=2)
    _post_comment(api_client, cleanup_test, run_id)
    _post_sct_event(api_client, run_id)
    assert _sct_event_count(api_client, run_id) == 1

    resp = api_client.delete(f"{API_PREFIX}/test/{cleanup_test.id}/run/{run_id}")

    assert resp.json()["status"] == "ok", resp.text
    assert resp.json()["response"]["deleted"] == run_id
    assert _run_ids(api_client, cleanup_test) == {kept_run_id}
    assert not _run_exists(api_client, SCT, run_id)
    assert api_client.get(f"{API_PREFIX}/run/{run_id}/comments").json()["response"] == []
    assert api_client.get(f"{API_PREFIX}/run/{run_id}/activity").json()["response"]["raw_events"] == []
    assert _sct_event_count(api_client, run_id) == 0
    assert _entity_exists(api_client, "test", cleanup_test.id)


def test_delete_run_of_another_test_is_refused(api_client, cleanup_release, cleanup_test, other_test):
    _mark_editable(api_client, cleanup_release)
    run_id = _submit_sct_run(api_client, other_test)

    resp = api_client.delete(f"{API_PREFIX}/test/{cleanup_test.id}/run/{run_id}")

    assert resp.json()["status"] == "error"
    assert "not a run of test" in resp.json()["response"]["arguments"][0]
    assert run_id in _run_ids(api_client, other_test)


def test_delete_run_that_does_not_exist_is_an_error(api_client, cleanup_release, cleanup_test):
    _mark_editable(api_client, cleanup_release)

    resp = api_client.delete(f"{API_PREFIX}/test/{cleanup_test.id}/run/{uuid4()}")

    assert resp.json()["status"] == "error"
    assert "does not exist" in resp.json()["response"]["arguments"][0]


def test_delete_test_removes_its_runs_and_the_test(api_client, cleanup_release, cleanup_test, other_test):
    _mark_editable(api_client, cleanup_release)
    run_ids = [_submit_sct_run(api_client, cleanup_test, build_number=n) for n in (1, 2)]
    other_run_id = _submit_sct_run(api_client, other_test)
    _post_comment(api_client, cleanup_test, run_ids[0])

    resp = api_client.delete(f"{API_PREFIX}/test/{cleanup_test.id}")

    assert resp.json()["status"] == "ok", resp.text
    assert resp.json()["response"]["deleted"] == str(cleanup_test.id)
    assert not _entity_exists(api_client, "test", cleanup_test.id)
    assert all(not _run_exists(api_client, SCT, run_id) for run_id in run_ids)
    assert api_client.get(f"{API_PREFIX}/run/{run_ids[0]}/comments").json()["response"] == []
    assert _run_ids(api_client, other_test) == {other_run_id}


def test_delete_group_removes_its_tests_runs_and_the_group(api_client, cleanup_release, cleanup_group,
                                                          cleanup_test, other_test):
    _mark_editable(api_client, cleanup_release)
    run_ids = [_submit_sct_run(api_client, cleanup_test), _submit_sct_run(api_client, other_test)]

    resp = api_client.delete(f"{API_PREFIX}/group/{cleanup_group.id}")

    assert resp.json()["status"] == "ok", resp.text
    assert resp.json()["response"]["deleted"] == str(cleanup_group.id)
    assert not _entity_exists(api_client, "group", cleanup_group.id)
    assert not _entity_exists(api_client, "test", cleanup_test.id)
    assert not _entity_exists(api_client, "test", other_test.id)
    assert all(not _run_exists(api_client, SCT, run_id) for run_id in run_ids)
    assert api_client.get(f"{API_PREFIX}/groups?releaseId={cleanup_release.id}").json()["response"] == []


def test_delete_generic_run_uses_the_default_plugin_hook(api_client, cleanup_release, generic_cleanup_test):
    _mark_editable(api_client, cleanup_release)
    run_id = _submit_generic_run(api_client, generic_cleanup_test)
    assert _run_exists(api_client, "generic", run_id)

    resp = api_client.delete(f"{API_PREFIX}/test/{generic_cleanup_test.id}/run/{run_id}")

    assert resp.json()["status"] == "ok", resp.text
    assert not _run_exists(api_client, "generic", run_id)
