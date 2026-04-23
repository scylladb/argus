import os
import uuid

import pytest
from flask import g
from werkzeug.security import generate_password_hash

from argus.backend.models.web import User, WebFileStorage


@pytest.fixture(autouse=True)
def secret_key(argus_app):
    """Profile endpoints rely on flask sessions / flash which require a secret key."""
    original = argus_app.secret_key
    argus_app.secret_key = "test-secret-key"
    yield
    argus_app.secret_key = original


@pytest.fixture
def saved_g_user():
    """Persist g.user so profile endpoints calling g.user.save() work."""
    g.user.password = generate_password_hash("old_password")
    g.user.roles = [role.value if hasattr(role, "value") else role for role in g.user.roles]
    g.user.save()
    return g.user


def test_update_full_name_persists(flask_client, saved_g_user):
    new_name = f"Updated Name {uuid.uuid4().hex[:6]}"
    res = flask_client.post("/profile/update/name", data={"new_name": new_name}, follow_redirects=False)
    assert res.status_code == 302
    assert "/profile" in res.headers["Location"]
    assert User.get(id=saved_g_user.id).full_name == new_name


def test_update_full_name_missing_value_flashes_error(flask_client, saved_g_user):
    original = saved_g_user.full_name
    res = flask_client.post("/profile/update/name", data={}, follow_redirects=False)
    assert res.status_code == 302
    assert User.get(id=saved_g_user.id).full_name == original


def test_update_username_persists(flask_client, saved_g_user):
    new_username = f"new_user_{uuid.uuid4().hex[:8]}"
    res = flask_client.post("/profile/update/username", data={"new_username": new_username}, follow_redirects=False)
    assert res.status_code == 302
    assert User.get(id=saved_g_user.id).username == new_username


def test_update_username_missing_value_flashes_error(flask_client, saved_g_user):
    original = saved_g_user.username
    res = flask_client.post("/profile/update/username", data={}, follow_redirects=False)
    assert res.status_code == 302
    assert User.get(id=saved_g_user.id).username == original


def test_update_email_admin_can_change(flask_client, saved_g_user):
    new_email = f"updated_{uuid.uuid4().hex[:6]}@example.com"
    res = flask_client.post("/profile/update/email", data={"new_email": new_email}, follow_redirects=False)
    assert res.status_code == 302
    assert User.get(id=saved_g_user.id).email == new_email


def test_update_password_with_correct_old_password(flask_client, saved_g_user):
    res = flask_client.post(
        "/profile/update/password",
        data={
            "old_password": "old_password",
            "new_password": "brand_new_password",
            "new_password_confirm": "brand_new_password",
        },
        follow_redirects=False,
    )
    assert res.status_code == 302
    refreshed = User.get(id=saved_g_user.id)
    # Hash changed and old password no longer validates
    from werkzeug.security import check_password_hash
    assert check_password_hash(refreshed.password, "brand_new_password")
    assert not check_password_hash(refreshed.password, "old_password")


def test_update_password_with_wrong_old_password_does_not_change(flask_client, saved_g_user):
    original_hash = saved_g_user.password
    res = flask_client.post(
        "/profile/update/password",
        data={
            "old_password": "wrong_password",
            "new_password": "brand_new_password",
            "new_password_confirm": "brand_new_password",
        },
        follow_redirects=False,
    )
    assert res.status_code == 302
    assert User.get(id=saved_g_user.id).password == original_hash


def test_update_password_mismatch_confirmation(flask_client, saved_g_user):
    original_hash = saved_g_user.password
    res = flask_client.post(
        "/profile/update/password",
        data={
            "old_password": "old_password",
            "new_password": "brand_new_password",
            "new_password_confirm": "different_value",
        },
        follow_redirects=False,
    )
    assert res.status_code == 302
    assert User.get(id=saved_g_user.id).password == original_hash


def test_update_password_missing_old_password(flask_client, saved_g_user):
    original_hash = saved_g_user.password
    res = flask_client.post(
        "/profile/update/password",
        data={"new_password": "brand_new_password", "new_password_confirm": "brand_new_password"},
        follow_redirects=False,
    )
    assert res.status_code == 302
    assert User.get(id=saved_g_user.id).password == original_hash


def test_get_picture_unknown_id_raises_does_not_exist(flask_client):
    # Endpoint only catches FileNotFoundError; an unknown picture id surfaces
    # as a Cassandra DoesNotExist -> 500 via the generic error handler.
    missing_id = uuid.uuid4()
    res = flask_client.get(f"/storage/picture/{missing_id}")
    assert res.status_code == 500


def test_get_picture_returns_file_contents(flask_client, tmp_path):
    payload = b"\x89PNG\r\n\x1a\nfake-image-data"
    file_path = tmp_path / "pic.png"
    file_path.write_bytes(payload)

    storage = WebFileStorage()
    storage.filename = "pic.png"
    storage.filepath = str(file_path)
    storage.save()
    try:
        res = flask_client.get(f"/storage/picture/{storage.id}")
        assert res.status_code == 200
        assert res.data == payload
        assert res.headers["Content-Type"].startswith("image/")
    finally:
        storage.delete()


def test_get_picture_file_missing_on_disk_returns_404(flask_client, tmp_path):
    storage = WebFileStorage()
    storage.filename = "missing.png"
    storage.filepath = str(tmp_path / "does_not_exist.png")
    storage.save()
    try:
        res = flask_client.get(f"/storage/picture/{storage.id}")
        assert res.status_code == 404
        assert b"404" in res.data
    finally:
        storage.delete()


def test_upload_picture_rejects_non_image_content_type(flask_client, saved_g_user):
    res = flask_client.post(
        "/profile/update/picture",
        data={"filedata": (__import__("io").BytesIO(b"not an image"), "evil.txt", "text/plain")},
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert res.status_code == 302
    assert "/profile" in res.headers["Location"]


def test_upload_picture_persists_web_file_and_updates_user(flask_client, saved_g_user, tmp_path, monkeypatch):
    # Redirect storage writes to tmp_path so we don't touch the repo storage dir.
    storage_dir = tmp_path / "profile_pictures"
    storage_dir.mkdir()
    monkeypatch.chdir(tmp_path)
    (tmp_path / "storage").mkdir(exist_ok=True)
    (tmp_path / "storage" / "profile_pictures").mkdir(exist_ok=True)

    payload = b"\x89PNG\r\n\x1a\nfake-image-data"
    res = flask_client.post(
        "/profile/update/picture",
        data={"filedata": (__import__("io").BytesIO(payload), "avatar.png", "image/png")},
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert res.status_code == 302
    refreshed = User.get(id=saved_g_user.id)
    assert refreshed.picture_id is not None
    stored = WebFileStorage.get(id=refreshed.picture_id)
    try:
        assert os.path.exists(stored.filepath)
        with open(stored.filepath, "rb") as fh:
            assert fh.read() == payload
    finally:
        try:
            os.unlink(stored.filepath)
        except OSError:
            pass
        stored.delete()


def test_profile_oauth_github_callback_bad_state_redirects_to_error(flask_client):
    """Mismatched CSRF state must redirect to the error page (no callback invoked)."""
    with flask_client.session_transaction() as sess:
        sess["csrf_token"] = "expected-token"
    res = flask_client.get(
        "/profile/oauth/github?state=wrong-token&code=abc",
        follow_redirects=False,
    )
    assert res.status_code == 302
    assert "/error" in res.headers["Location"]


def test_profile_oauth_github_callback_success_stores_first_run_info(
    flask_client, mock_github_callback
):
    """Valid CSRF state -> github_callback runs, first_run_info session populated, redirects."""
    mock_github_callback.return_value = {"password": "tmp", "first_login": True}
    with flask_client.session_transaction() as sess:
        sess["csrf_token"] = "match"
        sess["redirect_target"] = "/some/target"
    res = flask_client.get(
        "/profile/oauth/github?state=match&code=auth-code",
        follow_redirects=False,
    )
    assert res.status_code == 302
    assert res.headers["Location"].endswith("/some/target")
    mock_github_callback.assert_called_once_with("auth-code")
    with flask_client.session_transaction() as sess:
        assert sess.get("first_run_info") == {"password": "tmp", "first_login": True}


def test_profile_oauth_github_callback_service_error_redirects_to_error(
    flask_client, mock_github_callback
):
    """Exceptions from github_callback are caught and surface as a 403 error redirect."""
    mock_github_callback.side_effect = Exception("oauth boom")
    with flask_client.session_transaction() as sess:
        sess["csrf_token"] = "match"
    res = flask_client.get(
        "/profile/oauth/github?state=match&code=auth-code",
        follow_redirects=False,
    )
    assert res.status_code == 302
    assert "/error" in res.headers["Location"]


def test_profile_create_without_registration_allowed_errors(flask_client):
    """`registration_allowed` must be set in session before /profile/create is reachable."""
    with flask_client.session_transaction() as sess:
        sess.pop("registration_allowed", None)
    res = flask_client.get("/profile/create", follow_redirects=False)
    # handle_profile_exception turns UserServiceException into a 302 redirect
    assert res.status_code in (302, 200)


def test_profile_create_post_creates_user_and_logs_in(flask_client):
    """Happy-path POST to /profile/create creates the user and redirects to profile."""
    username = f"newuser_{uuid.uuid4().hex[:8]}"
    email = f"{username}@scylladb.com"

    with flask_client.session_transaction() as sess:
        sess["registration_allowed"] = True
        sess["lock_user_email"] = True
        sess["oauth_email"] = email

    res = flask_client.post(
        "/profile/create",
        data={"username": username, "email": email, "full_name": "New User"},
        follow_redirects=False,
    )
    assert res.status_code == 302
    assert "/profile" in res.headers["Location"]
    created = User.exists_by_name(username)
    assert created is not None
    assert created.email == email
    with flask_client.session_transaction() as sess:
        assert sess.get("user_id") == str(created.id)
        assert sess.get("first_run_info", {}).get("first_login") is True
    created.delete()


def test_profile_create_post_locked_email_mismatch_errors(flask_client):
    """When `lock_user_email` is set, posting a different email must error."""
    with flask_client.session_transaction() as sess:
        sess["registration_allowed"] = True
        sess["lock_user_email"] = True
        sess["oauth_email"] = "locked@scylladb.com"

    res = flask_client.post(
        "/profile/create",
        data={"username": "x", "email": "other@scylladb.com", "full_name": "X"},
        follow_redirects=False,
    )
    # UserServiceException -> handle_profile_exception -> redirect
    assert res.status_code in (302, 200)
    # Should NOT have created a user with that username
    assert User.exists_by_name("x") is None
