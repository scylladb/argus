"""Controller-level integration tests for user endpoints in
``argus/backend/controller/admin_api.py``.

URL prefix: ``/admin/api/v1`` (admin_api blueprint nested under admin).

Scope (iteration 10 of the controller coverage matrix):

- ``GET  /admin/api/v1/users``
- ``POST /admin/api/v1/user/<id>/email/set``
- ``POST /admin/api/v1/user/<id>/delete``
- ``POST /admin/api/v1/user/<id>/password/set``
- ``POST /admin/api/v1/user/<id>/admin/toggle``
"""

import json
import uuid

import pytest
from flask import g

from argus.backend.models.web import User, UserRoles


ADMIN_PREFIX = "/admin/api/v1"


def _post(flask_client, path: str, payload: dict | None = None):
    return flask_client.post(
        path,
        data=json.dumps(payload or {}),
        content_type="application/json",
    )


def _get_admin_user(flask_client, user_id: str) -> dict | None:
    resp = flask_client.get(f"{ADMIN_PREFIX}/users")
    assert resp.status_code == 200, resp.data
    body = resp.json
    assert body["status"] == "ok", body
    return body["response"].get(user_id)


@pytest.fixture
def saved_g_user():
    """Persist ``g.user`` so admin self-protection paths can compare ids."""
    g.user.password = "test_password"
    g.user.roles = [r.value if hasattr(r, "value") else r for r in g.user.roles]
    g.user.save()
    return g.user


@pytest.fixture
def regular_user():
    user = User(
        id=uuid.uuid4(),
        username=f"adm10_user_{uuid.uuid4().hex[:8]}",
        full_name="Admin10 Test User",
        email=f"adm10_{uuid.uuid4().hex[:8]}@scylladb.com",
        password="hash:placeholder",
        roles=[UserRoles.User.value],
    )
    user.save()
    return user


# ---------------------------------------------------------------------------
# /users (privileged listing)
# ---------------------------------------------------------------------------

def test_admin_users_returns_dict_without_password(flask_client, regular_user):
    resp = flask_client.get(f"{ADMIN_PREFIX}/users")
    assert resp.status_code == 200, resp.data
    body = resp.json
    assert body["status"] == "ok"
    assert isinstance(body["response"], dict)
    assert str(regular_user.id) in body["response"]
    entry = body["response"][str(regular_user.id)]
    assert "password" not in entry
    assert "api_token" not in entry
    assert entry["username"] == regular_user.username
    assert entry["email"] == regular_user.email


# ---------------------------------------------------------------------------
# /user/<id>/email/set
# ---------------------------------------------------------------------------

def test_admin_user_change_email(flask_client, regular_user):
    new_email = f"new_{uuid.uuid4().hex[:8]}@scylladb.com"
    resp = _post(
        flask_client,
        f"{ADMIN_PREFIX}/user/{regular_user.id}/email/set",
        {"newEmail": new_email},
    )
    assert resp.status_code == 200, resp.data
    body = resp.json
    assert body["status"] == "ok"
    assert body["response"] is True

    listed = _get_admin_user(flask_client, str(regular_user.id))
    assert listed is not None
    assert listed["email"] == new_email


def test_admin_user_change_email_invalid_format_errors(flask_client, regular_user):
    resp = _post(
        flask_client,
        f"{ADMIN_PREFIX}/user/{regular_user.id}/email/set",
        {"newEmail": "not-a-valid-email"},
    )
    assert resp.status_code == 200
    assert resp.json["status"] == "error"


def test_admin_user_change_email_duplicate_errors(flask_client, regular_user, saved_g_user):
    resp = _post(
        flask_client,
        f"{ADMIN_PREFIX}/user/{regular_user.id}/email/set",
        {"newEmail": saved_g_user.email},
    )
    assert resp.status_code == 200
    assert resp.json["status"] == "error"


# ---------------------------------------------------------------------------
# /user/<id>/password/set
# ---------------------------------------------------------------------------

def test_admin_user_change_password(flask_client, regular_user):
    resp = _post(
        flask_client,
        f"{ADMIN_PREFIX}/user/{regular_user.id}/password/set",
        {"newPassword": "newSecret123"},
    )
    assert resp.status_code == 200, resp.data
    body = resp.json
    assert body["status"] == "ok"
    assert body["response"] is True


def test_admin_user_change_password_too_short_errors(flask_client, regular_user):
    resp = _post(
        flask_client,
        f"{ADMIN_PREFIX}/user/{regular_user.id}/password/set",
        {"newPassword": "abc"},
    )
    assert resp.status_code == 200
    assert resp.json["status"] == "error"


def test_admin_user_change_password_empty_errors(flask_client, regular_user):
    resp = _post(
        flask_client,
        f"{ADMIN_PREFIX}/user/{regular_user.id}/password/set",
        {"newPassword": ""},
    )
    assert resp.status_code == 200
    assert resp.json["status"] == "error"


# ---------------------------------------------------------------------------
# /user/<id>/admin/toggle
# ---------------------------------------------------------------------------

def test_admin_toggle_admin_grants_then_revokes(flask_client, regular_user):
    resp = _post(flask_client, f"{ADMIN_PREFIX}/user/{regular_user.id}/admin/toggle")
    assert resp.status_code == 200, resp.data
    assert resp.json["status"] == "ok"
    assert UserRoles.Admin.value in _get_admin_user(flask_client, str(regular_user.id))["roles"]

    resp = _post(flask_client, f"{ADMIN_PREFIX}/user/{regular_user.id}/admin/toggle")
    assert resp.status_code == 200, resp.data
    assert resp.json["status"] == "ok"
    assert UserRoles.Admin.value not in _get_admin_user(flask_client, str(regular_user.id))["roles"]


def test_admin_toggle_admin_self_forbidden(flask_client, saved_g_user):
    resp = _post(flask_client, f"{ADMIN_PREFIX}/user/{saved_g_user.id}/admin/toggle")
    assert resp.status_code == 200
    assert resp.json["status"] == "error"


# ---------------------------------------------------------------------------
# /user/<id>/delete
# ---------------------------------------------------------------------------

def test_admin_delete_user(flask_client, regular_user):
    resp = _post(flask_client, f"{ADMIN_PREFIX}/user/{regular_user.id}/delete")
    assert resp.status_code == 200, resp.data
    body = resp.json
    assert body["status"] == "ok"
    assert body["response"] is True
    assert _get_admin_user(flask_client, str(regular_user.id)) is None


def test_admin_delete_user_self_forbidden(flask_client, saved_g_user):
    resp = _post(flask_client, f"{ADMIN_PREFIX}/user/{saved_g_user.id}/delete")
    assert resp.status_code == 200
    assert resp.json["status"] == "error"


def test_admin_delete_admin_user_forbidden(flask_client, regular_user):
    # Promote, then try to delete — must error per service rule.
    _post(flask_client, f"{ADMIN_PREFIX}/user/{regular_user.id}/admin/toggle")
    resp = _post(flask_client, f"{ADMIN_PREFIX}/user/{regular_user.id}/delete")
    assert resp.status_code == 200
    assert resp.json["status"] == "error"


def test_admin_delete_user_unknown_id_errors(flask_client):
    resp = _post(flask_client, f"{ADMIN_PREFIX}/user/{uuid.uuid4()}/delete")
    assert resp.status_code == 200
    assert resp.json["status"] == "error"
