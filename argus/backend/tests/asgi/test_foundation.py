"""Foundation tests for the FastAPI app.

Covers the pieces every controller relies on: the signed session cookie
(both directions), the auth dependencies' response shapes, the
APIException contract, and request context in log lines.
"""
import io
import logging
import uuid

from fastapi import APIRouter, Depends, Request
from pytest import fixture
from starlette.testclient import TestClient

from argus.backend.util.logsetup import LOG_FORMAT_REQUEST, ArgusRequestLogFormatter

from argus.backend.error_handlers import APIException
from argus.backend.service.user import api_current_user, require_roles
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
def probe_routes(asgi_app, include_router_before_fallback):
    include_router_before_fallback(asgi_app, probe)
    yield
    asgi_app.router.routes = [
        route for route in asgi_app.routes if not getattr(route, "path", "").startswith("/asgi-probe")
    ]


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


def test_unauthenticated_request_matches_flask_shape(anon_client):
    response = anon_client.get("/asgi-probe/me")
    assert response.status_code == 403
    assert response.json() == {"status": "error", "message": "Authorization required"}


def test_role_check_forbidden_matches_flask_shape(anon_client, db_user):
    response = anon_client.get("/asgi-probe/admin-only",
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


def test_token_header_authenticates_against_db(anon_client, db_user):
    response = anon_client.get("/asgi-probe/me",
                              headers={"Authorization": f"token {db_user.api_token}"})
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "response": "asgi_probe_user"}


def test_session_cookie_authenticates_route(anon_client, db_user, make_session_cookie):
    anon_client.cookies.set("session", make_session_cookie(user_id=str(db_user.id)))
    response = anon_client.get("/asgi-probe/me")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "response": "asgi_probe_user"}


def test_session_writes_produce_a_readable_signed_cookie(anon_client, read_session):
    response = anon_client.get("/asgi-probe/session-write")
    assert response.status_code == 200
    assert response.cookies.get("session"), "session cookie should be set when the session is mutated"
    assert read_session(anon_client) == {"probe": "value"}


def test_unknown_routes_return_404(anon_client):
    response = anon_client.get("/api/v1/definitely-not-a-route")
    assert response.status_code == 404


def test_log_lines_carry_request_context(api_client):
    """TraceId error lines must be correlatable: the formatter resolves
    url/remote_addr/endpoint from the live request scope."""
    logger = logging.getLogger("argus.backend.error_handlers")
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(ArgusRequestLogFormatter(LOG_FORMAT_REQUEST))
    logger.addHandler(handler)
    old_level = logger.level
    logger.setLevel(logging.INFO)
    try:
        api_client.get("/asgi-probe/boom", params={"marker": "ctx"})
    finally:
        logger.removeHandler(handler)
        logger.setLevel(old_level)
    output = stream.getvalue()
    assert "[TraceId:" in output
    assert "/asgi-probe/boom?marker=ctx" in output
    assert "probe_boom" in output
