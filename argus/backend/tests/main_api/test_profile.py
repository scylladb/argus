from datetime import UTC, datetime
import os
import uuid
from unittest.mock import ANY

import pytest
from werkzeug.security import check_password_hash, generate_password_hash

from argus.backend.models.web import User, UserRoles, WebFileStorage


@pytest.fixture
def db_user(argus_db) -> User:
    user = User(id=uuid.uuid4(), username=f"profile-user-{uuid.uuid4().hex[:8]}",
                full_name="Profile User", email="profile-user@scylladb.com",
                password=generate_password_hash("old_password"),
                roles=[UserRoles.User.value, UserRoles.Admin.value], registration_date=datetime.now(UTC))
    user.save()
    return user


@pytest.fixture
def profile_client(anon_client, db_user, make_session_cookie):
    """Anonymous client carrying a real session cookie for a persisted user."""
    anon_client.cookies.set("session", make_session_cookie(user_id=str(db_user.id)))
    return anon_client


def test_update_full_name_persists(profile_client, db_user):
    new_name = f"Updated Name {uuid.uuid4().hex[:6]}"
    res = profile_client.post("/profile/update/name", data={"new_name": new_name}, follow_redirects=False)
    assert res.status_code == 302
    assert "/profile" in res.headers["Location"]
    assert User.get(id=db_user.id).full_name == new_name


def test_update_full_name_missing_value_flashes_error(profile_client, db_user):
    original = db_user.full_name
    res = profile_client.post("/profile/update/name", data={}, follow_redirects=False)
    assert res.status_code == 302
    assert User.get(id=db_user.id).full_name == original


def test_update_username_persists(profile_client, db_user):
    new_username = f"new_user_{uuid.uuid4().hex[:8]}"
    res = profile_client.post("/profile/update/username", data={"new_username": new_username},
                              follow_redirects=False)
    assert res.status_code == 302
    assert User.get(id=db_user.id).username == new_username


def test_update_username_missing_value_flashes_error(profile_client, db_user):
    original = db_user.username
    res = profile_client.post("/profile/update/username", data={}, follow_redirects=False)
    assert res.status_code == 302
    assert User.get(id=db_user.id).username == original


def test_update_email_admin_can_change(profile_client, db_user):
    new_email = f"updated_{uuid.uuid4().hex[:6]}@example.com"
    res = profile_client.post("/profile/update/email", data={"new_email": new_email},
                              follow_redirects=False)
    assert res.status_code == 302
    assert User.get(id=db_user.id).email == new_email


def test_update_password_with_correct_old_password(profile_client, db_user):
    res = profile_client.post(
        "/profile/update/password",
        data={
            "old_password": "old_password",
            "new_password": "brand_new_password",
            "new_password_confirm": "brand_new_password",
        },
        follow_redirects=False,
    )
    assert res.status_code == 302
    refreshed = User.get(id=db_user.id)
    # Hash changed and old password no longer validates
    assert check_password_hash(refreshed.password, "brand_new_password")
    assert not check_password_hash(refreshed.password, "old_password")


def test_update_password_with_wrong_old_password_does_not_change(profile_client, db_user):
    original_hash = db_user.password
    res = profile_client.post(
        "/profile/update/password",
        data={
            "old_password": "wrong_password",
            "new_password": "brand_new_password",
            "new_password_confirm": "brand_new_password",
        },
        follow_redirects=False,
    )
    assert res.status_code == 302
    assert User.get(id=db_user.id).password == original_hash


def test_update_password_mismatch_confirmation(profile_client, db_user):
    original_hash = db_user.password
    res = profile_client.post(
        "/profile/update/password",
        data={
            "old_password": "old_password",
            "new_password": "brand_new_password",
            "new_password_confirm": "different_value",
        },
        follow_redirects=False,
    )
    assert res.status_code == 302
    assert User.get(id=db_user.id).password == original_hash


def test_update_password_missing_old_password(profile_client, db_user):
    original_hash = db_user.password
    res = profile_client.post(
        "/profile/update/password",
        data={"new_password": "brand_new_password", "new_password_confirm": "brand_new_password"},
        follow_redirects=False,
    )
    assert res.status_code == 302
    assert User.get(id=db_user.id).password == original_hash


def test_get_picture_unknown_id_surfaces_as_error_response(profile_client):
    # Endpoint only catches FileNotFoundError; an unknown picture id surfaces
    # as DocumentNotFound through the generic exception handler.
    missing_id = uuid.uuid4()
    res = profile_client.get(f"/storage/picture/{missing_id}")
    assert res.json()["status"] == "error"


def test_get_picture_returns_file_contents(profile_client, tmp_path):
    payload = b"\x89PNG\r\n\x1a\nfake-image-data"
    file_path = tmp_path / "pic.png"
    file_path.write_bytes(payload)

    storage = WebFileStorage.model_construct()
    storage.filename = "pic.png"
    storage.filepath = str(file_path)
    storage.save()
    try:
        res = profile_client.get(f"/storage/picture/{storage.id}")
        assert res.status_code == 200
        assert res.content == payload
        assert res.headers["Content-Type"].startswith("image/")
    finally:
        storage.delete()


def test_get_picture_file_missing_on_disk_returns_404(profile_client, tmp_path):
    storage = WebFileStorage.model_construct()
    storage.filename = "missing.png"
    storage.filepath = str(tmp_path / "does_not_exist.png")
    storage.save()
    try:
        res = profile_client.get(f"/storage/picture/{storage.id}")
        assert res.status_code == 404
        assert b"404" in res.content
    finally:
        storage.delete()


def test_upload_picture_rejects_non_image_content_type(profile_client):
    res = profile_client.post(
        "/profile/update/picture",
        files={"filedata": ("evil.txt", b"not an image", "text/plain")},
        follow_redirects=False,
    )
    assert res.status_code == 302
    assert "/profile" in res.headers["Location"]


def test_upload_picture_persists_web_file_and_updates_user(profile_client, db_user, tmp_path, monkeypatch):
    # Redirect storage writes to tmp_path so we don't touch the repo storage dir.
    monkeypatch.chdir(tmp_path)
    (tmp_path / "storage" / "profile_pictures").mkdir(parents=True, exist_ok=True)

    payload = b"\x89PNG\r\n\x1a\nfake-image-data"
    res = profile_client.post(
        "/profile/update/picture",
        files={"filedata": ("avatar.png", payload, "image/png")},
        follow_redirects=False,
    )
    assert res.status_code == 302
    refreshed = User.get(id=db_user.id)
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


def test_profile_oauth_github_callback_bad_state_redirects_to_error(anon_client, db_user, make_session_cookie):
    """Mismatched CSRF state must redirect to the error page (no callback invoked)."""
    anon_client.cookies.set("session", make_session_cookie(
        user_id=str(db_user.id), csrf_token="expected-token"))
    res = anon_client.get(
        "/profile/oauth/github?state=wrong-token&code=abc",
        follow_redirects=False,
    )
    assert res.status_code == 302
    assert "/error" in res.headers["Location"]


def test_profile_oauth_github_callback_success_stores_first_run_info(
    anon_client, db_user, make_session_cookie, read_session, mock_github_callback
):
    """Valid CSRF state -> github_callback runs, first_run_info session populated, redirects."""
    mock_github_callback.return_value = {"password": "tmp", "first_login": True}
    anon_client.cookies.set("session", make_session_cookie(
        user_id=str(db_user.id), csrf_token="match", redirect_target="/some/target"))
    res = anon_client.get(
        "/profile/oauth/github?state=match&code=auth-code",
        follow_redirects=False,
    )
    assert res.status_code == 302
    assert res.headers["Location"].endswith("/some/target")
    mock_github_callback.assert_called_once_with("auth-code", ANY, ANY)
    assert read_session(anon_client).get("first_run_info") == {"password": "tmp", "first_login": True}


def test_profile_oauth_github_callback_service_error_redirects_to_error(
    anon_client, db_user, make_session_cookie, mock_github_callback
):
    """Exceptions from github_callback are caught and surface as a 403 error redirect."""
    mock_github_callback.side_effect = Exception("oauth boom")
    anon_client.cookies.set("session", make_session_cookie(
        user_id=str(db_user.id), csrf_token="match"))
    res = anon_client.get(
        "/profile/oauth/github?state=match&code=auth-code",
        follow_redirects=False,
    )
    assert res.status_code == 302
    assert "/error" in res.headers["Location"]


def test_profile_create_without_registration_allowed_errors(anon_client):
    """`registration_allowed` must be set in session before /profile/create is reachable."""
    res = anon_client.get("/profile/create", follow_redirects=False)
    # the UserServiceException handler turns it into a 302 redirect
    assert res.status_code == 302
    assert "/profile" in res.headers["Location"]


def test_profile_create_post_creates_user_and_logs_in(anon_client, make_session_cookie, read_session):
    """Happy-path POST to /profile/create creates the user and redirects to profile."""
    username = f"newuser_{uuid.uuid4().hex[:8]}"
    email = f"{username}@scylladb.com"

    anon_client.cookies.set("session", make_session_cookie(
        registration_allowed=True, lock_user_email=True, oauth_email=email))

    res = anon_client.post(
        "/profile/create",
        data={"username": username, "email": email, "full_name": "New User"},
        follow_redirects=False,
    )
    assert res.status_code == 302
    assert "/profile" in res.headers["Location"]
    created = User.exists_by_name(username)
    assert created is not None
    assert created.email == email
    session = read_session(anon_client)
    assert session.get("user_id") == str(created.id)
    assert session.get("first_run_info", {}).get("first_login") is True
    created.delete()


def test_profile_create_post_locked_email_mismatch_errors(anon_client, make_session_cookie):
    """When `lock_user_email` is set, posting a different email must error."""
    anon_client.cookies.set("session", make_session_cookie(
        registration_allowed=True, lock_user_email=True, oauth_email="locked@scylladb.com"))

    res = anon_client.post(
        "/profile/create",
        data={"username": "x", "email": "other@scylladb.com", "full_name": "X"},
        follow_redirects=False,
    )
    # the UserServiceException handler turns it into a redirect
    assert res.status_code == 302
    # Should NOT have created a user with that username
    assert User.exists_by_name("x") is None


def test_error_page_shows_logged_in_nav_for_authenticated_user(anon_client, db_user, make_session_cookie):
    """main.error must resolve the visitor (load_user) so a logged-in user
    redirected to /error/ keeps the logged-in nav bar."""
    anon_client.cookies.set("session", make_session_cookie(user_id=str(db_user.id)))
    res = anon_client.get("/error/", params={"type": "404"})
    assert res.status_code == 200
    assert db_user.username in res.text
    assert "fa-sign-in-alt" not in res.text  # no Login link


def test_error_page_shows_logged_out_nav_for_anonymous_user(anon_client):
    res = anon_client.get("/error/", params={"type": "404"})
    assert res.status_code == 200
    assert "fa-sign-in-alt" in res.text  # Login link present
