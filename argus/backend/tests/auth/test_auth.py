import uuid

import pytest
from flask import current_app, g, session
from werkzeug.security import generate_password_hash

from argus.backend.models.web import User, UserRoles


@pytest.fixture(autouse=True)
def secret_key(argus_app):
    """auth endpoints rely on flask sessions which require a secret key."""
    original = argus_app.secret_key
    argus_app.secret_key = "test-secret-key"
    yield
    argus_app.secret_key = original


@pytest.fixture
def saved_g_user():
    """Persist g.user so endpoints calling g.user.save() work."""
    g.user.password = "test_password_hash"
    g.user.roles = [role.value if hasattr(role, "value") else role for role in g.user.roles]
    g.user.save()
    return g.user


def test_register_redirects_to_login(flask_client):
    res = flask_client.get("/auth/register", follow_redirects=False)
    assert res.status_code == 302
    assert "/auth/login" in res.headers["Location"]


def test_login_get_authenticated_redirects_to_home(flask_client):
    res = flask_client.get("/auth/login", follow_redirects=False)
    assert res.status_code == 302
    # g.user is set in the session-scoped app context => redirect to main.home
    assert res.headers["Location"].endswith("/")


def test_login_get_authenticated_uses_redirect_target(flask_client):
    with flask_client.session_transaction() as sess:
        sess["redirect_target"] = "/some/path"
    res = flask_client.get("/auth/login", follow_redirects=False)
    assert res.status_code == 302
    assert res.headers["Location"].endswith("/some/path")


def test_logout_clears_session_and_sets_manual_logout(flask_client):
    with flask_client.session_transaction() as sess:
        sess["user_id"] = str(uuid.uuid4())

    res = flask_client.post("/auth/logout", follow_redirects=False)
    assert res.status_code == 302
    assert "/auth/login" in res.headers["Location"]
    with flask_client.session_transaction() as sess:
        assert "user_id" not in sess
        assert sess.get("manual_logout") is True


def test_generate_api_token_persists_and_redirects_to_profile(flask_client, saved_g_user):
    res = flask_client.post("/auth/profile/api/token/generate", follow_redirects=False)
    assert res.status_code == 302
    assert "/profile" in res.headers["Location"]

    refreshed = User.get(id=saved_g_user.id)
    assert refreshed.api_token
    with flask_client.session_transaction() as sess:
        assert sess.get("token_generated") == refreshed.api_token


def test_cf_login_without_jwt_redirects_to_login_with_manual_logout(flask_client):
    res = flask_client.post("/auth/login/cf", follow_redirects=False)
    assert res.status_code == 302
    assert "/auth/login" in res.headers["Location"]
    with flask_client.session_transaction() as sess:
        assert sess.get("manual_logout") is True


def test_impersonate_get_renders_user_switch(flask_client):
    res = flask_client.get("/auth/admin/impersonate")
    assert res.status_code == 200
    # template renders user_switch.html.j2
    assert b"user" in res.data.lower()


def test_impersonate_post_missing_user_id_flashes_and_redirects(flask_client):
    res = flask_client.post("/auth/admin/impersonate", data={}, follow_redirects=False)
    assert res.status_code == 302
    assert "/profile" in res.headers["Location"]


def test_stop_impersonation_without_active_session_errors(flask_client):
    res = flask_client.post("/auth/admin/impersonate/stop", follow_redirects=False)
    # handle_profile_exception converts UserServiceException to a flash + redirect
    assert res.status_code in (302, 200)


def test_password_login_success_sets_user_id_in_session(flask_client, argus_db):
    """Posting valid credentials with password login enabled stores user_id in session."""
    raw_password = "s3cret-pw"
    user = User()
    user.id = uuid.uuid4()
    user.username = f"pw-user-{uuid.uuid4().hex[:8]}"
    user.email = f"{user.username}@scylladb.com"
    user.password = generate_password_hash(raw_password)
    user.roles = ["ROLE_USER"]
    user.save()

    original_methods = current_app.config.get("LOGIN_METHODS", [])
    current_app.config["LOGIN_METHODS"] = ["password"]
    original_g_user = g.user
    g.user = None  # force the unauthenticated branch in /auth/login
    try:
        res = flask_client.post(
            "/auth/login",
            data={"username": user.username, "password": raw_password},
            follow_redirects=False,
        )
        assert res.status_code == 302
        assert res.headers["Location"].endswith("/")
        with flask_client.session_transaction() as sess:
            assert sess.get("user_id") == str(user.id)
    finally:
        current_app.config["LOGIN_METHODS"] = original_methods
        g.user = original_g_user


def test_password_login_disabled_flashes_error(flask_client):
    """Password login posts redirect to /auth/login when password method disabled."""
    original_methods = current_app.config.get("LOGIN_METHODS", [])
    current_app.config["LOGIN_METHODS"] = ["cf"]
    original_g_user = g.user
    g.user = None
    try:
        with flask_client.session_transaction() as sess:
            sess.pop("user_id", None)
        res = flask_client.post(
            "/auth/login",
            data={"username": "anyone", "password": "x"},
            follow_redirects=False,
        )
        assert res.status_code == 302
        with flask_client.session_transaction() as sess:
            assert "user_id" not in sess
    finally:
        current_app.config["LOGIN_METHODS"] = original_methods
        g.user = original_g_user


def test_cf_login_with_valid_jwt_logs_in_existing_user(flask_client, mock_cf_access_payload):
    """CF JWT happy path: /auth/login/cf logs in matching @scylladb.com user."""
    user = User()
    user.id = uuid.uuid4()
    user.username = f"cf-user-{uuid.uuid4().hex[:8]}"
    user.email = f"{user.username}@scylladb.com"
    user.roles = ["ROLE_USER"]
    user.save()
    mock_cf_access_payload.return_value = {"email": user.email}

    original_methods = current_app.config.get("LOGIN_METHODS", [])
    current_app.config["LOGIN_METHODS"] = ["cf"]
    try:
        res = flask_client.post(
            "/auth/login/cf",
            headers={"Cf-Access-Jwt-Assertion": "fake-jwt"},
            follow_redirects=False,
        )
        assert res.status_code == 302
        # default redirect is main.profile when no redirect_target
        assert "/profile" in res.headers["Location"]
        with flask_client.session_transaction() as sess:
            assert sess.get("user_id") == str(user.id)
            assert sess.get("auth_via_cf") is True
    finally:
        current_app.config["LOGIN_METHODS"] = original_methods


def test_full_impersonation_flow(flask_client):
    """Admin impersonates another user, then stops impersonation."""
    target = User()
    target.id = uuid.uuid4()
    target.username = f"imp-{uuid.uuid4().hex[:8]}"
    target.email = f"{target.username}@scylladb.com"
    target.roles = ["ROLE_USER"]
    target.save()

    # Persist the admin (g.user) so stop_impersonation can re-fetch it.
    g.user.password = "irrelevant"
    g.user.save()
    admin_id = g.user.id

    with flask_client.session_transaction() as sess:
        sess.pop("original_user", None)

    res = flask_client.post(
        "/auth/admin/impersonate",
        data={"user_id": str(target.id)},
        follow_redirects=False,
    )
    assert res.status_code == 302
    assert "/profile" in res.headers["Location"]
    with flask_client.session_transaction() as sess:
        assert sess.get("original_user") == str(admin_id)
        assert sess.get("user_id") == str(target.id)

    res = flask_client.post("/auth/admin/impersonate/stop", follow_redirects=False)
    assert res.status_code == 302
    with flask_client.session_transaction() as sess:
        assert "original_user" not in sess
        assert sess.get("user_id") == str(admin_id)

    # restore g.user for downstream tests
    g.user = User.get(id=admin_id)
