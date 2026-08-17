"""Foundation tests for the FastAPI strangler shell.

Covers the pieces every migrated blueprint will rely on: the shared
Flask-format session cookie (both directions), the auth dependencies'
response shapes, the APIException contract, and the Flask fall-through.
"""
import uuid

from fastapi import APIRouter, Depends, Request
from flask.sessions import SecureCookieSessionInterface
from pytest import fixture
from starlette.testclient import TestClient

from argus.backend.asgi import include_router_before_fallback
from argus.backend.asgi.auth import api_current_user, load_user, require_roles
from argus.backend.error_handlers import APIException
from argus.backend.models.web import User, UserRoles

probe = APIRouter(prefix="/asgi-probe")


@probe.get("/me")
def probe_me(user: User = Depends(api_current_user)):
    return {"status": "ok", "response": user.username}


@probe.get("/admin-only")
def probe_admin(user: User = Depends(require_roles(UserRoles.Admin))):
    return {"status": "ok", "response": user.username}


@probe.get("/boom")
def probe_boom():
    raise APIException("probe exploded", "with-argument")


@probe.get("/session-write")
def probe_session_write(request: Request):
    request.session["probe"] = "value"
    return {"status": "ok"}


@fixture(scope="module", autouse=True)
def probe_routes(argus_app):
    import argus_asgi
    include_router_before_fallback(argus_asgi.app, probe)
    yield
    argus_asgi.app.router.routes = [
        route for route in argus_asgi.app.routes if not getattr(route, "path", "").startswith("/asgi-probe")
    ]


@fixture
def raw_client(argus_app):
    """TestClient without dependency overrides — exercises real auth.

    api_client's session-scoped load_user override lives on the shared app
    object, so it is stashed away for the duration of each raw test.
    """
    import argus_asgi
    saved = dict(argus_asgi.app.dependency_overrides)
    argus_asgi.app.dependency_overrides.clear()
    yield TestClient(argus_asgi.app, raise_server_exceptions=False)
    argus_asgi.app.dependency_overrides.update(saved)


@fixture(scope="module")
def db_user(argus_db) -> User:
    user = User(id=uuid.uuid4(), username="asgi_probe_user", full_name="ASGI Probe",
                email="asgi-probe@scylladb.com", api_token=f"probe-token-{uuid.uuid4()}",
                roles=[UserRoles.User])
    user.save()
    return user


def test_authenticated_request_via_override(api_client):
    response = api_client.get("/asgi-probe/me")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "response": "test_user"}


def test_unauthenticated_request_matches_flask_shape(raw_client):
    response = raw_client.get("/asgi-probe/me")
    assert response.status_code == 403
    assert response.json() == {"status": "error", "message": "Authorization required"}


def test_role_check_forbidden_matches_flask_shape(raw_client, db_user):
    response = raw_client.get("/asgi-probe/admin-only",
                              headers={"Authorization": f"token {db_user.api_token}"})
    assert response.status_code == 403
    assert response.json() == {"status": "error", "message": "Forbidden"}


def test_api_exception_keeps_flask_contract(api_client):
    response = api_client.get("/asgi-probe/boom")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "error"
    assert body["response"]["exception"] == "APIException"
    assert body["response"]["message"] == "('probe exploded', 'with-argument')"
    assert body["response"]["arguments"] == ["probe exploded", "with-argument"]
    assert body["response"]["trace_id"]


def test_token_header_authenticates_against_db(raw_client, db_user):
    response = raw_client.get("/asgi-probe/me",
                              headers={"Authorization": f"token {db_user.api_token}"})
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "response": "asgi_probe_user"}


def test_flask_session_cookie_authenticates_fastapi_route(raw_client, flask_client, db_user):
    with flask_client.session_transaction() as flask_session:
        flask_session["user_id"] = str(db_user.id)
    cookie = flask_client.get_cookie("session")
    raw_client.cookies.set("session", cookie.value)
    response = raw_client.get("/asgi-probe/me")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "response": "asgi_probe_user"}


def test_fastapi_session_writes_are_readable_by_flask(raw_client, argus_app):
    response = raw_client.get("/asgi-probe/session-write")
    assert response.status_code == 200
    cookie_value = response.cookies.get("session")
    assert cookie_value, "session cookie should be set when the session is mutated"
    serializer = SecureCookieSessionInterface().get_signing_serializer(argus_app)
    assert serializer.loads(cookie_value) == {"probe": "value"}


def test_unmigrated_routes_fall_through_to_flask(raw_client):
    response = raw_client.get("/api/v1/definitely-not-a-route")
    assert response.status_code == 404
