"""Controller-level integration tests for the user/jobs/poll/proxy endpoints
exposed by ``argus/backend/controller/api.py``.

Scope (iteration 6 of the controller coverage matrix):

- ``GET  /api/v1/users``
- ``GET  /api/v1/user/token``
- ``GET  /api/v1/user/jobs``
- ``GET  /api/v1/user/planned_jobs``
- ``GET  /api/v1/test_runs/poll``
- ``GET  /api/v1/test_run/poll``
- ``GET  /api/v1/artifact/resolveSize``
- ``GET  /api/v1/zeus/<endpoint>``       (error path only — no real proxy target)
- ``GET  /api/v1/test_run/comment/get``  (deprecated companion endpoint, lives in api.py)
"""

import json
import uuid
from unittest.mock import MagicMock, patch

import pytest
from flask import g

from argus.backend.models.web import User, UserRoles


API_PREFIX = "/api/v1"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def saved_g_user():
    """Persist ``g.user`` so endpoints that call ``user.save()`` (e.g. token
    generation) succeed.  Mirrors the helper in ``tests/test_assignee.py``."""
    g.user.password = "test_password"
    g.user.roles = [r.value if hasattr(r, "value") else r for r in g.user.roles]
    g.user.save()
    return g.user


@pytest.fixture
def submitted_sct_run(flask_client, fake_test):
    run_id = str(uuid.uuid4())
    payload = {
        "run_id": run_id,
        "job_name": fake_test.build_system_id,
        "job_url": "http://example.com/job/42",
        "started_by": "poll_user",
        "commit_id": "deadbeef",
        "origin_url": "http://example.com/repo.git",
        "branch_name": "main",
        "sct_config": {"cluster_backend": "aws"},
        "schema_version": "v8",
    }
    resp = flask_client.post(
        f"{API_PREFIX}/client/testrun/scylla-cluster-tests/submit",
        data=json.dumps(payload), content_type="application/json",
    )
    assert resp.status_code == 200, resp.data
    return run_id


# ---------------------------------------------------------------------------
# /users
# ---------------------------------------------------------------------------

def test_list_users_returns_dict(api_client, saved_g_user):
    resp = api_client.get(f"{API_PREFIX}/users")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["status"] == "ok"
    assert isinstance(body["response"], dict)
    assert str(saved_g_user.id) in body["response"]
    entry = body["response"][str(saved_g_user.id)]
    assert entry["username"] == saved_g_user.username


# ---------------------------------------------------------------------------
# /user/token
# ---------------------------------------------------------------------------

def test_user_token_is_stable_across_calls(api_client, saved_g_user):
    first = api_client.get(f"{API_PREFIX}/user/token")
    assert first.status_code == 200, first.content
    body = first.json()
    assert body["status"] == "ok"
    token = body["response"]["token"]
    assert isinstance(token, str) and token

    second = api_client.get(f"{API_PREFIX}/user/token")
    assert second.json()["response"]["token"] == token


# ---------------------------------------------------------------------------
# /user/jobs and /user/planned_jobs
# ---------------------------------------------------------------------------

def test_user_jobs_returns_list(api_client, saved_g_user):
    resp = api_client.get(f"{API_PREFIX}/user/jobs")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["status"] == "ok"
    assert isinstance(body["response"], list)


def test_user_planned_jobs_returns_list(api_client, saved_g_user):
    resp = api_client.get(f"{API_PREFIX}/user/planned_jobs")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["status"] == "ok"
    assert isinstance(body["response"], list)


# ---------------------------------------------------------------------------
# /test_runs/poll and /test_run/poll
# ---------------------------------------------------------------------------

def test_test_runs_poll_is_removed(api_client, fake_test, submitted_sct_run):
    resp = api_client.get(
        f"{API_PREFIX}/test_runs/poll",
        params={"testId": str(fake_test.id), "limit": 10},
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["status"] == "error"
    assert body["response"]["exception"] == "APIException"
    assert "removed" in body["response"]["message"]


def test_test_run_poll_single_is_removed(api_client, submitted_sct_run):
    resp = api_client.get(
        f"{API_PREFIX}/test_run/poll", params={"runs": submitted_sct_run}
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["status"] == "error"
    assert body["response"]["exception"] == "APIException"
    assert "removed" in body["response"]["message"]


# ---------------------------------------------------------------------------
# /artifact/resolveSize  (S3 + plain-HTTP variants)
# ---------------------------------------------------------------------------

def test_resolve_artifact_size_non_s3_uses_http_head(api_client):
    fake_response = MagicMock(status_code=200, headers={"Content-Length": "4242"})
    with patch("argus.backend.service.testrun.requests.head", return_value=fake_response) as mock_head:
        resp = api_client.get(
            f"{API_PREFIX}/artifact/resolveSize",
            params={"l": "http://example.com/some/file.tar.gz"},
        )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["status"] == "ok"
    assert body["response"] == {"artifactSize": 4242}
    mock_head.assert_called_once()


def test_resolve_artifact_size_missing_link(api_client):
    resp = api_client.get(f"{API_PREFIX}/artifact/resolveSize")
    assert resp.status_code == 200
    assert resp.json()["status"] == "error"


def test_resolve_artifact_size_http_error(api_client):
    fake_response = MagicMock(status_code=500, headers={})
    with patch("argus.backend.service.testrun.requests.head", return_value=fake_response):
        resp = api_client.get(
            f"{API_PREFIX}/artifact/resolveSize",
            params={"l": "http://example.com/missing"},
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "error"


# ---------------------------------------------------------------------------
# /zeus/<endpoint>  (error path only — no real Zeus target)
# ---------------------------------------------------------------------------

def test_zeus_proxy_without_host_errors(api_client, argus_app):
    saved_host = argus_app.config.pop("ZEUS_HOST", None)
    try:
        resp = api_client.get(f"{API_PREFIX}/zeus/anything")
        assert resp.status_code == 200
        assert resp.json()["status"] == "error"
    finally:
        if saved_host is not None:
            argus_app.config["ZEUS_HOST"] = saved_host


def test_zeus_proxy_without_token_errors(api_client, argus_app):
    saved_host = argus_app.config.get("ZEUS_HOST")
    saved_token = argus_app.config.pop("ZEUS_TOKEN", None)
    argus_app.config["ZEUS_HOST"] = "localhost:9999"
    try:
        resp = api_client.get(f"{API_PREFIX}/zeus/anything")
        assert resp.status_code == 200
        assert resp.json()["status"] == "error"
    finally:
        if saved_token is not None:
            argus_app.config["ZEUS_TOKEN"] = saved_token
        if saved_host is None:
            argus_app.config.pop("ZEUS_HOST", None)
        else:
            argus_app.config["ZEUS_HOST"] = saved_host


# ---------------------------------------------------------------------------
# /test_run/comment/get  (deprecated, lives in api.py — covers happy + miss)
# ---------------------------------------------------------------------------

def test_get_test_run_comment_unknown_returns_false(api_client):
    resp = api_client.get(
        f"{API_PREFIX}/test_run/comment/get", params={"commentId": str(uuid.uuid4())}
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["status"] == "ok"
    assert body["response"] is False


def test_get_test_run_comment_missing_id(api_client):
    resp = api_client.get(f"{API_PREFIX}/test_run/comment/get")
    assert resp.status_code == 200
    assert resp.json()["status"] == "error"


def test_get_test_run_comment_existing_round_trip(flask_client, api_client, fake_test, submitted_sct_run, saved_g_user):
    submit_resp = flask_client.post(
        f"{API_PREFIX}/test/{fake_test.id}/run/{submitted_sct_run}/comments/submit",
        data=json.dumps({"message": "iteration6 comment", "mentions": [], "reactions": {}}),
        content_type="application/json",
    )
    assert submit_resp.status_code == 200, submit_resp.data
    assert submit_resp.json["status"] == "ok"

    list_resp = flask_client.get(f"{API_PREFIX}/run/{submitted_sct_run}/comments")
    comments = list_resp.json["response"]
    assert comments, list_resp.data
    comment_id = str(comments[0]["id"])

    fetch_resp = api_client.get(
        f"{API_PREFIX}/test_run/comment/get", params={"commentId": comment_id}
    )
    assert fetch_resp.status_code == 200, fetch_resp.content
    body = fetch_resp.json()
    assert body["status"] == "ok"
    assert str(body["response"]["id"]) == comment_id
    assert body["response"]["message"] == "iteration6 comment"
