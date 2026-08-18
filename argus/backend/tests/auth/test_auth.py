import uuid

import pytest
from werkzeug.security import generate_password_hash

from argus.backend.models.web import User, UserRoles


@pytest.fixture
def db_admin(argus_db) -> User:
    user = User(id=uuid.uuid4(), username=f"auth-admin-{uuid.uuid4().hex[:8]}",
                email="auth-admin@scylladb.com", password="irrelevant",
                roles=[UserRoles.User.value, UserRoles.Admin.value])
    user.save()
    return user


@pytest.fixture
def admin_client(anon_client, db_admin, make_session_cookie):
    """Anonymous client with a real session cookie for a persisted admin."""
    anon_client.cookies.set("session", make_session_cookie(user_id=str(db_admin.id)))
    return anon_client


def test_register_redirects_to_login(anon_client):
    res = anon_client.get("/auth/register", follow_redirects=False)
    assert res.status_code == 302
    assert "/auth/login" in res.headers["Location"]


def test_login_get_authenticated_redirects_to_home(admin_client):
    res = admin_client.get("/auth/login", follow_redirects=False)
    assert res.status_code == 302
    assert res.headers["Location"].endswith("/")


def test_login_get_authenticated_uses_redirect_target(anon_client, db_admin, make_session_cookie):
    anon_client.cookies.set("session", make_session_cookie(
        user_id=str(db_admin.id), redirect_target="/some/path"))
    res = anon_client.get("/auth/login", follow_redirects=False)
    assert res.status_code == 302
    assert res.headers["Location"].endswith("/some/path")


def test_login_get_anonymous_renders_login_page(anon_client, read_session):
    res = anon_client.get("/auth/login")
    assert res.status_code == 200
    assert read_session(anon_client).get("csrf_token")


def test_logout_clears_session_and_sets_manual_logout(anon_client, make_session_cookie, read_session):
    anon_client.cookies.set("session", make_session_cookie(user_id=str(uuid.uuid4())))

    res = anon_client.post("/auth/logout", follow_redirects=False)
    assert res.status_code == 302
    assert "/auth/login" in res.headers["Location"]
    session = read_session(anon_client)
    assert "user_id" not in session
    assert session.get("manual_logout") is True


def test_generate_api_token_persists_and_redirects_to_profile(admin_client, db_admin, read_session):
    res = admin_client.post("/auth/profile/api/token/generate", follow_redirects=False)
    assert res.status_code == 302
    assert "/profile" in res.headers["Location"]

    refreshed = User.get(id=db_admin.id)
    assert refreshed.api_token
    assert read_session(admin_client).get("token_generated") == refreshed.api_token


def test_cf_login_without_jwt_redirects_to_login_with_manual_logout(anon_client, read_session):
    res = anon_client.post("/auth/login/cf", follow_redirects=False)
    assert res.status_code == 302
    assert "/auth/login" in res.headers["Location"]
    assert read_session(anon_client).get("manual_logout") is True


def test_impersonate_get_renders_user_switch(admin_client):
    res = admin_client.get("/auth/admin/impersonate")
    assert res.status_code == 200
    assert b"user" in res.content.lower()


def test_impersonate_post_missing_user_id_flashes_and_redirects(admin_client):
    res = admin_client.post("/auth/admin/impersonate", data={}, follow_redirects=False)
    assert res.status_code == 302
    assert "/profile" in res.headers["Location"]


def test_stop_impersonation_without_active_session_errors(admin_client):
    # the UserServiceException handler converts it to a flash + redirect
    res = admin_client.post("/auth/admin/impersonate/stop", follow_redirects=False)
    assert res.status_code == 302
    assert "/profile" in res.headers["Location"]


def test_password_login_success_sets_user_id_in_session(anon_client, argus_app, argus_db, read_session):
    """Posting valid credentials with password login enabled stores user_id in session."""
    raw_password = "s3cret-pw"
    user = User(id=uuid.uuid4(), username=f"pw-user-{uuid.uuid4().hex[:8]}",
                password=generate_password_hash(raw_password), roles=["ROLE_USER"])
    user.email = f"{user.username}@scylladb.com"
    user.save()

    original_methods = argus_app.config.get("LOGIN_METHODS", [])
    argus_app.config["LOGIN_METHODS"] = ["password"]
    try:
        res = anon_client.post(
            "/auth/login",
            data={"username": user.username, "password": raw_password},
            follow_redirects=False,
        )
        assert res.status_code == 302
        assert res.headers["Location"].endswith("/")
        assert read_session(anon_client).get("user_id") == str(user.id)
    finally:
        argus_app.config["LOGIN_METHODS"] = original_methods


def test_password_login_disabled_flashes_error(anon_client, argus_app, read_session):
    """Password login posts redirect away without a session when disabled."""
    original_methods = argus_app.config.get("LOGIN_METHODS", [])
    argus_app.config["LOGIN_METHODS"] = ["cf"]
    try:
        res = anon_client.post(
            "/auth/login",
            data={"username": "anyone", "password": "x"},
            follow_redirects=False,
        )
        assert res.status_code == 302
        assert "user_id" not in read_session(anon_client)
    finally:
        argus_app.config["LOGIN_METHODS"] = original_methods


def test_cf_login_with_valid_jwt_logs_in_existing_user(anon_client, argus_db,
                                                       mock_cf_access_payload, read_session):
    """CF JWT happy path: /auth/login/cf logs in matching @scylladb.com user."""
    user = User(id=uuid.uuid4(), username=f"cf-user-{uuid.uuid4().hex[:8]}", roles=["ROLE_USER"])
    user.email = f"{user.username}@scylladb.com"
    user.save()
    mock_cf_access_payload.return_value = {"email": user.email}

    res = anon_client.post(
        "/auth/login/cf",
        headers={"Cf-Access-Jwt-Assertion": "fake-jwt"},
        follow_redirects=False,
    )
    assert res.status_code == 302
    # default redirect is main.profile when no redirect_target
    assert "/profile" in res.headers["Location"]
    session = read_session(anon_client)
    assert session.get("user_id") == str(user.id)
    assert session.get("auth_via_cf") is True


def test_full_impersonation_flow(admin_client, db_admin, argus_db, read_session):
    """Admin impersonates another user, then stops impersonation."""
    target = User(id=uuid.uuid4(), username=f"imp-{uuid.uuid4().hex[:8]}", roles=["ROLE_USER"])
    target.email = f"{target.username}@scylladb.com"
    target.save()

    res = admin_client.post(
        "/auth/admin/impersonate",
        data={"user_id": str(target.id)},
        follow_redirects=False,
    )
    assert res.status_code == 302
    assert "/profile" in res.headers["Location"]
    session = read_session(admin_client)
    assert session.get("original_user") == str(db_admin.id)
    assert session.get("user_id") == str(target.id)

    res = admin_client.post("/auth/admin/impersonate/stop", follow_redirects=False)
    assert res.status_code == 302
    session = read_session(admin_client)
    assert "original_user" not in session
    assert session.get("user_id") == str(db_admin.id)
