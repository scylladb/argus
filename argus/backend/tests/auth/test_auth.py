import uuid

import pytest
from flask import g, session

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
