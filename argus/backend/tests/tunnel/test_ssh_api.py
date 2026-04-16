"""
Flask integration tests for the SSH tunnel API (Step 4a routes).

Routes under test:
    GET   /api/v1/client/ssh/tunnel
    POST  /api/v1/client/ssh/tunnel
    GET   /api/v1/client/ssh/keys

Run with:
    uv run pytest argus/backend/tests/tunnel/test_ssh_api.py -m docker_required -v
"""
import json
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from flask import g
from flask.testing import FlaskClient

from argus.backend.models.ssh_key import ProxyTunnelConfig, SSHTunnelKey

API_PREFIX = "/api/v1/client/ssh"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_public_key() -> str:
    """Generate a fresh ed25519 public key in OpenSSH format."""
    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key()
    return pub.public_bytes(Encoding.OpenSSH, PublicFormat.OpenSSH).decode("utf-8")


def _make_active_config(**overrides) -> ProxyTunnelConfig:
    """Create and persist a ProxyTunnelConfig with is_active=True."""
    defaults = dict(
        id=uuid4(),
        host=f"proxy-{uuid4().hex[:6]}.example.com",
        port=22,
        proxy_user="argus-proxy",
        target_host="10.0.0.1",
        target_port=8080,
        host_key_fingerprint="SHA256:testfp",
        is_active=True,
    )
    defaults.update(overrides)
    return ProxyTunnelConfig.create(**defaults)


def _json_post(client: FlaskClient, url: str, payload: dict) -> object:
    return client.post(url, data=json.dumps(payload), content_type="application/json")


def _active_config_ids() -> list:
    return [cfg.id for cfg in ProxyTunnelConfig.objects.all() if cfg.is_active]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def active_config(argus_db) -> ProxyTunnelConfig:
    previous_active_ids = _active_config_ids()
    for cfg_id in previous_active_ids:
        cfg = ProxyTunnelConfig.get(id=cfg_id)
        cfg.update(is_active=False)

    config = _make_active_config(service_user_id=g.user.id)
    yield config
    try:
        config.delete()
    except Exception:
        pass

    for cfg_id in previous_active_ids:
        try:
            cfg = ProxyTunnelConfig.get(id=cfg_id)
            cfg.update(is_active=True)
        except Exception:
            pass


@pytest.fixture
def service_user_identity():
    previous = getattr(g.user, "service_user", False)
    g.user.service_user = True
    yield
    g.user.service_user = previous


@pytest.fixture
def normal_user_identity():
    previous = getattr(g.user, "service_user", False)
    g.user.service_user = False
    yield
    g.user.service_user = previous


def _deactivate_all_configs() -> list:
    cfg_ids = _active_config_ids()
    for cfg_id in cfg_ids:
        ProxyTunnelConfig.get(id=cfg_id).update(is_active=False)
    return cfg_ids


def _restore_active_configs(cfg_ids: list):
    for cfg_id in cfg_ids:
        try:
            ProxyTunnelConfig.get(id=cfg_id).update(is_active=True)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# GET /api/v1/client/ssh/tunnel
# ---------------------------------------------------------------------------

@pytest.mark.docker_required
def test_get_tunnel_connection_success(flask_client: FlaskClient, argus_db, active_config):
    resp = flask_client.get(f"{API_PREFIX}/tunnel")

    assert resp.status_code == 200
    body = resp.json
    assert body["status"] == "ok"
    data = body["response"]
    assert data["proxy_host"] == active_config.host
    assert data["proxy_port"] == active_config.port
    assert data["proxy_user"] == active_config.proxy_user
    assert data["target_host"] == active_config.target_host
    assert data["target_port"] == active_config.target_port
    assert data["host_key_fingerprint"] == active_config.host_key_fingerprint


@pytest.mark.docker_required
def test_get_tunnel_connection_no_active_config_returns_error(flask_client: FlaskClient, argus_db):
    previous_active_ids = _deactivate_all_configs()
    try:
        resp = flask_client.get(f"{API_PREFIX}/tunnel")
        assert resp.status_code == 200
        assert resp.json["status"] == "error"
        assert "No active proxy tunnel configuration" in resp.json["response"]["message"]
    finally:
        _restore_active_configs(previous_active_ids)


# ---------------------------------------------------------------------------
# POST /api/v1/client/ssh/tunnel
# ---------------------------------------------------------------------------

@pytest.mark.docker_required
def test_register_tunnel_success(flask_client: FlaskClient, argus_db, active_config):
    """A valid POST /ssh/tunnel should return 200 with proxy connection details."""
    payload = {"public_key": _make_public_key()}
    resp = _json_post(flask_client, f"{API_PREFIX}/tunnel", payload)

    assert resp.status_code == 200, resp.text
    body = resp.json
    assert body["status"] == "ok"
    data = body["response"]
    assert data["proxy_host"] == active_config.host
    assert data["proxy_port"] == active_config.port
    assert data["proxy_user"] == active_config.proxy_user
    assert data["target_host"] == active_config.target_host
    assert data["target_port"] == active_config.target_port
    assert data["host_key_fingerprint"] == active_config.host_key_fingerprint
    assert data["expires_at"].endswith("Z")
    assert "key_id" in data
    assert "tunnel_id" in data

    # Verify the key was actually persisted in the DB
    key = SSHTunnelKey.get(id=data["key_id"])
    assert key.fingerprint.startswith("SHA256:")


@pytest.mark.docker_required
def test_register_tunnel_with_ttl_seconds(flask_client: FlaskClient, argus_db, active_config):
    """ttl_seconds should be honoured and reflected in expires_at."""
    from datetime import datetime, timezone

    ttl = 172800  # 2 days
    payload = {"public_key": _make_public_key(), "ttl_seconds": ttl}
    before = datetime.now(tz=timezone.utc)
    resp = _json_post(flask_client, f"{API_PREFIX}/tunnel", payload)
    after = datetime.now(tz=timezone.utc)

    assert resp.status_code == 200
    expires_at = datetime.fromisoformat(
        resp.json["response"]["expires_at"].rstrip("Z")
    ).replace(tzinfo=timezone.utc)
    assert (before.timestamp() + ttl - 5) <= expires_at.timestamp() <= (after.timestamp() + ttl + 5)


@pytest.mark.docker_required
def test_register_tunnel_invalid_ttl(flask_client: FlaskClient, argus_db, active_config):
    """TTL outside [24h, 30d] should return an error response."""
    for ttl in (0, 86399, 2592001):
        payload = {"public_key": _make_public_key(), "ttl_seconds": ttl}
        resp = _json_post(flask_client, f"{API_PREFIX}/tunnel", payload)

        assert resp.status_code == 200
        assert resp.json["status"] == "error"
        assert "ttl_seconds must be between 86400 and 2592000 seconds" in resp.json["response"]["message"]


@pytest.mark.docker_required
def test_register_tunnel_missing_public_key(flask_client: FlaskClient, argus_db, active_config):
    """A request without public_key should return an error response."""
    resp = _json_post(flask_client, f"{API_PREFIX}/tunnel", {})

    assert resp.status_code == 200  # Flask error handler returns 200 with status=error
    assert resp.json["status"] == "error"


@pytest.mark.docker_required
def test_register_tunnel_invalid_public_key(flask_client: FlaskClient, argus_db, active_config):
    """An unparseable public key should return an error response."""
    payload = {"public_key": "clearly-not-a-key"}
    resp = _json_post(flask_client, f"{API_PREFIX}/tunnel", payload)

    assert resp.status_code == 200
    assert resp.json["status"] == "error"
    assert "Invalid SSH public key" in resp.json["response"]["message"]


@pytest.mark.docker_required
def test_register_tunnel_unauthenticated(argus_db, active_config):
    """Requests without a valid auth token should be rejected with 403."""
    from argus_backend import argus_app

    previous_user = g.user
    try:
        g.user = None
        with argus_app.test_client() as unauthenticated_client:
            resp = unauthenticated_client.post(
                f"{API_PREFIX}/tunnel",
                data=json.dumps({"public_key": _make_public_key()}),
                content_type="application/json",
            )
    finally:
        g.user = previous_user

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /api/v1/client/ssh/keys
# ---------------------------------------------------------------------------

@pytest.mark.docker_required
def test_get_authorized_keys_success(flask_client: FlaskClient, argus_db, active_config, service_user_identity):
    """GET /ssh/keys should return 200 with plain-text content."""
    # Register a key first so there is something to return
    pub_key = _make_public_key()
    _json_post(flask_client, f"{API_PREFIX}/tunnel", {"public_key": pub_key})

    resp = flask_client.get(f"{API_PREFIX}/keys")

    assert resp.status_code == 200
    assert resp.content_type.startswith("text/plain")
    keys_text = resp.data.decode("utf-8")
    assert pub_key.strip() in keys_text


@pytest.mark.docker_required
def test_get_authorized_keys_forbidden_for_normal_user(flask_client: FlaskClient, argus_db, active_config, normal_user_identity):
    """GET /ssh/keys should fail for non-service users."""
    resp = flask_client.get(f"{API_PREFIX}/keys")
    assert resp.status_code == 200
    assert resp.json["status"] == "error"
    assert "Only service users can fetch SSH authorized keys" in resp.json["response"]["message"]


@pytest.mark.docker_required
def test_get_authorized_keys_empty_when_no_keys(flask_client: FlaskClient, argus_db, active_config, service_user_identity):
    """GET /ssh/keys for a tunnel with no registered keys should return empty text."""
    resp = flask_client.get(f"{API_PREFIX}/keys")
    assert resp.status_code == 200
    assert resp.data.decode("utf-8").strip() == ""


@pytest.mark.docker_required
def test_get_authorized_keys_unauthenticated(argus_db, active_config):
    """GET /ssh/keys without auth should return 403."""
    from argus_backend import argus_app

    previous_user = g.user
    try:
        g.user = None
        with argus_app.test_client() as unauthenticated_client:
            resp = unauthenticated_client.get(f"{API_PREFIX}/keys")
    finally:
        g.user = previous_user

    assert resp.status_code == 403
