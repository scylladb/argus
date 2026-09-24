"""Controller-level integration tests for the user/jobs/poll/proxy endpoints
exposed by ``argus/backend/controller/api.py``.

Scope (iteration 6 of the controller coverage matrix):

- ``GET  /api/v1/users``
- ``POST /api/v1/user/token``
- ``GET  /api/v1/user/jobs``
- ``GET  /api/v1/user/planned_jobs``
- ``GET  /api/v1/test_runs/poll``
- ``GET  /api/v1/test_run/poll``
- ``GET  /api/v1/artifact/resolveSize``
- ``GET  /api/v1/s3/<bucket>/<path>``
- ``GET  /api/v1/zeus/<endpoint>``       (error path only — no real proxy target)
- ``GET  /api/v1/test_run/comment/get``  (deprecated companion endpoint, lives in api.py)
"""

import json
import uuid
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from argus.backend.tests.conftest import g, get_fake_test_run

from coodie.aio import execute_raw

from argus.backend.db import ScyllaCluster
from argus.backend.models.web import User, UserOauthToken, UserRoles
from argus.backend.service.user import API_TOKEN_KIND, UserService, hash_api_token


API_PREFIX = "/api/v1"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def saved_g_user():
    """Persist ``g.user`` so endpoints that call ``user.save()`` (e.g. token
    generation) succeed.  Mirrors the helper in ``tests/test_assignee.py``."""
    g.user.password = "test_password"
    g.user.roles = [r.value if hasattr(r, "value") else r for r in g.user.roles]
    await g.user.save()
    return g.user


@pytest.fixture
def submitted_sct_run(api_client, fake_test):
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
    resp = api_client.post(
        f"{API_PREFIX}/client/testrun/scylla-cluster-tests/submit",
        json=payload,
    )
    assert resp.status_code == 200, resp.content
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

async def test_user_token_issues_new_token_on_each_call(api_client, saved_g_user):
    """Only a digest is stored, so the endpoint cannot echo an existing token:
    each call issues an additional one and earlier ones keep resolving."""
    first = api_client.post(f"{API_PREFIX}/user/token")
    assert first.status_code == 200, first.content
    body = first.json()
    assert body["status"] == "ok"
    token = body["response"]["token"]
    assert isinstance(token, str) and token

    second = api_client.post(f"{API_PREFIX}/user/token")
    new_token = second.json()["response"]["token"]
    assert new_token != token

    stored = {t.token: t.kind for t in await UserOauthToken.find(user_id=saved_g_user.id).all()}
    assert stored[hash_api_token(token)] == API_TOKEN_KIND
    assert stored[hash_api_token(new_token)] == API_TOKEN_KIND


async def _row_ttl(row: UserOauthToken) -> int | None:
    keyspace = ScyllaCluster.get().config["SCYLLA_KEYSPACE_NAME"]
    rows = await execute_raw(
        f'SELECT TTL(kind) AS ttl FROM {keyspace}.{UserOauthToken.Settings.name} WHERE user_id = ? AND "token" = ?',
        [row.user_id, row.token],
    )
    return rows[0]["ttl"]


async def test_user_token_default_duration_is_one_year(api_client, saved_g_user):
    before = datetime.now(UTC).replace(tzinfo=None)
    body = api_client.post(f"{API_PREFIX}/user/token").json()
    assert body["status"] == "ok", body
    row = await UserOauthToken.get(user_id=saved_g_user.id, token=hash_api_token(body["response"]["token"]))
    assert abs(row.expiration_date - before - timedelta(days=365)) < timedelta(minutes=1)
    assert body["response"]["expiration_date"].startswith(row.expiration_date.strftime("%Y-%m-%dT%H:%M"))
    ttl = await _row_ttl(row)
    assert ttl is not None and timedelta(days=365) - timedelta(minutes=1) < timedelta(seconds=ttl) <= timedelta(days=365)


async def test_user_token_accepts_custom_duration(api_client, saved_g_user):
    before = datetime.now(UTC).replace(tzinfo=None)
    body = api_client.post(f"{API_PREFIX}/user/token", json={"duration": "24h"}).json()
    assert body["status"] == "ok", body
    row = await UserOauthToken.get(user_id=saved_g_user.id, token=hash_api_token(body["response"]["token"]))
    assert abs(row.expiration_date - before - timedelta(hours=24)) < timedelta(minutes=1)
    assert 0 < await _row_ttl(row) <= 24 * 3600


async def test_user_token_null_duration_is_non_expiring(api_client, saved_g_user):
    body = api_client.post(f"{API_PREFIX}/user/token", json={"duration": None}).json()
    assert body["status"] == "ok", body
    assert body["response"]["expiration_date"] is None
    row = await UserOauthToken.get(user_id=saved_g_user.id, token=hash_api_token(body["response"]["token"]))
    assert row.expiration_date is None
    assert await _row_ttl(row) is None


def test_user_token_rejects_invalid_duration(api_client, saved_g_user):
    body = api_client.post(f"{API_PREFIX}/user/token", json={"duration": "soon"}).json()
    assert body["status"] == "error"
    assert body["response"]["exception"] == "DataValidationError"
    assert "soon" in body["response"]["message"]


async def test_user_token_get_reports_expiration_of_calling_token(anon_client, saved_g_user):
    issued = await UserService().generate_token(saved_g_user, duration="14d")
    body = anon_client.get(f"{API_PREFIX}/user/token",
                           headers={"Authorization": f"token {issued.token}"}).json()
    assert body["status"] == "ok", body
    assert body["response"]["expiration_date"] == issued.expiration_date.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def test_user_token_get_requires_token_authentication(api_client, saved_g_user):
    """The session-authenticated client has no calling token to report on."""
    body = api_client.get(f"{API_PREFIX}/user/token").json()
    assert body["status"] == "error"
    assert body["response"]["exception"] == "APIException"


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


async def test_user_planned_jobs_reports_the_latest_run_of_an_owned_plan_test(api_client, saved_g_user, release,
                                                                            fake_test, client_service):
    plan_payload = {
        "name": f"planned_jobs_{uuid.uuid4().hex[:8]}",
        "description": "planned jobs test plan",
        "owner": str(saved_g_user.id),
        "participants": [],
        "target_version": "1.0",
        "release_id": str(release.id),
        "tests": [str(fake_test.id)],
        "groups": [],
        "assignments": {},
    }
    created = api_client.post(f"{API_PREFIX}/planning/plan/create", json=plan_payload).json()
    assert created["status"] == "ok", created
    plan_id = created["response"]["id"]
    try:
        run_type, older_run = get_fake_test_run(fake_test)
        await client_service.submit_run(run_type, asdict(older_run))
        run_type, latest_run = get_fake_test_run(fake_test)
        await client_service.submit_run(run_type, asdict(latest_run))

        body = api_client.get(f"{API_PREFIX}/user/planned_jobs").json()
        assert body["status"] == "ok", body
        jobs_by_test_id = {job["id"]: job for job in body["response"]}
        assert jobs_by_test_id[str(fake_test.id)]["last_run"]["id"] == latest_run.run_id
    finally:
        deleted = api_client.delete(f"{API_PREFIX}/planning/plan/{plan_id}/delete", params={"deleteView": "true"}).json()
        assert deleted["status"] == "ok", deleted


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

def test_zeus_proxy_without_host_errors(api_client, app_config):
    saved_host = app_config.pop("ZEUS_HOST", None)
    try:
        resp = api_client.get(f"{API_PREFIX}/zeus/anything")
        assert resp.status_code == 200
        assert resp.json()["status"] == "error"
    finally:
        if saved_host is not None:
            app_config["ZEUS_HOST"] = saved_host


def test_zeus_proxy_forwards_json_body_verbatim(api_client, app_config):
    """A Body(...) param made FastAPI JSON-parse the payload and reject every
    JSON request with RequestValidationError — the body must pass through raw."""
    saved_host = app_config.get("ZEUS_HOST")
    saved_token = app_config.get("ZEUS_TOKEN")
    app_config["ZEUS_HOST"] = "zeus.test"
    app_config["ZEUS_TOKEN"] = "zeus-token"
    upstream = MagicMock()
    upstream.content = b'{"zeus": "ok"}'
    upstream.status_code = 200
    upstream.headers = {"content-type": "application/json"}
    try:
        with patch("argus.backend.controller.api.requests.Session") as session_cls:
            session_cls.return_value.send.return_value = upstream
            resp = api_client.post(f"{API_PREFIX}/zeus/some/endpoint", json={"key": "value"})
        assert resp.status_code == 200
        assert resp.json() == {"zeus": "ok"}
        prepared = session_cls.return_value.send.call_args.args[0]
        assert prepared.body == b'{"key":"value"}'
    finally:
        if saved_host is None:
            app_config.pop("ZEUS_HOST", None)
        else:
            app_config["ZEUS_HOST"] = saved_host
        if saved_token is None:
            app_config.pop("ZEUS_TOKEN", None)
        else:
            app_config["ZEUS_TOKEN"] = saved_token


def test_zeus_proxy_without_token_errors(api_client, app_config):
    saved_host = app_config.get("ZEUS_HOST")
    saved_token = app_config.pop("ZEUS_TOKEN", None)
    app_config["ZEUS_HOST"] = "localhost:9999"
    try:
        resp = api_client.get(f"{API_PREFIX}/zeus/anything")
        assert resp.status_code == 200
        assert resp.json()["status"] == "error"
    finally:
        if saved_token is not None:
            app_config["ZEUS_TOKEN"] = saved_token
        if saved_host is None:
            app_config.pop("ZEUS_HOST", None)
        else:
            app_config["ZEUS_HOST"] = saved_host


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


def test_get_test_run_comment_existing_round_trip(api_client, fake_test, submitted_sct_run, saved_g_user):
    submit_resp = api_client.post(
        f"{API_PREFIX}/test/{fake_test.id}/run/{submitted_sct_run}/comments/submit",
        json={"message": "iteration6 comment", "mentions": [], "reactions": {}},
    )
    assert submit_resp.status_code == 200, submit_resp.content
    assert submit_resp.json()["status"] == "ok"

    list_resp = api_client.get(f"{API_PREFIX}/run/{submitted_sct_run}/comments")
    comments = list_resp.json()["response"]
    assert comments, list_resp.content
    comment_id = str(comments[0]["id"])

    fetch_resp = api_client.get(
        f"{API_PREFIX}/test_run/comment/get", params={"commentId": comment_id}
    )
    assert fetch_resp.status_code == 200, fetch_resp.content
    body = fetch_resp.json()
    assert body["status"] == "ok"
    assert str(body["response"]["id"]) == comment_id
    assert body["response"]["message"] == "iteration6 comment"


@pytest.mark.parametrize("method", ["get", "head"])
def test_s3_generic_proxy_redirects(api_client, mock_s3, method):
    mock_s3.proxy_s3_file.return_value = "https://test-bucket.s3.amazonaws.com/some/file?signed"
    resp = getattr(api_client, method)(
        f"{API_PREFIX}/s3/test-bucket/some/file",
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "test-bucket" in resp.headers["Location"]
