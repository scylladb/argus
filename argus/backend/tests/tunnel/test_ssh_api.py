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

from argus.backend.models.runtime_store import RuntimeStore
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

    _clear_proxy_rr_state()

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
def ssh_tunnel_server_identity():
    previous_roles = list(getattr(g.user, "roles", []))
    g.user.roles = ["ROLE_SSH_TUNNEL_SERVER"]
    yield
    g.user.roles = previous_roles


@pytest.fixture
def normal_user_identity():
    previous_roles = list(getattr(g.user, "roles", []))
    g.user.roles = ["ROLE_USER"]
    yield
    g.user.roles = previous_roles


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


def _clear_proxy_rr_state() -> None:
    try:
        RuntimeStore.get(key="ssh_tunnel_proxy_rr_index").delete()
    except RuntimeStore.DoesNotExist:
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
def test_get_tunnel_connection_select_specific_host(flask_client: FlaskClient, argus_db, active_config):
    second = _make_active_config(is_active=True)
    try:
        resp = flask_client.get(f"{API_PREFIX}/tunnel?proxy_host={second.host}")
        assert resp.status_code == 200
        body = resp.json
        assert body["status"] == "ok"
        assert body["response"]["proxy_host"] == second.host
    finally:
        try:
            second.delete()
        except Exception:
            pass


@pytest.mark.docker_required
def test_get_tunnel_connection_round_robin(flask_client: FlaskClient, argus_db, active_config):
    second = _make_active_config(is_active=True)
    try:
        _clear_proxy_rr_state()
        resp1 = flask_client.get(f"{API_PREFIX}/tunnel")
        resp2 = flask_client.get(f"{API_PREFIX}/tunnel")
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        host1 = resp1.json["response"]["proxy_host"]
        host2 = resp2.json["response"]["proxy_host"]
        assert host1 != host2
        assert {host1, host2} == {active_config.host, second.host}
    finally:
        try:
            second.delete()
        except Exception:
            pass


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
    """TTL outside [1h, 30d] should return an error response."""
    for ttl in (0, 3599, 2592001):
        payload = {"public_key": _make_public_key(), "ttl_seconds": ttl}
        resp = _json_post(flask_client, f"{API_PREFIX}/tunnel", payload)

        assert resp.status_code == 200
        assert resp.json["status"] == "error"
        assert "ttl_seconds must be between 3600 and 2592000 seconds" in resp.json["response"]["message"]


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
def test_get_authorized_keys_success(flask_client: FlaskClient, argus_db, active_config, ssh_tunnel_server_identity):
    """GET /ssh/keys should return 200 with plain-text content."""
    # Insert a key directly so scoped role does not call other endpoints.
    from datetime import UTC, datetime

    pub_key = _make_public_key()
    now_utc = datetime.now(tz=UTC).replace(tzinfo=None)
    SSHTunnelKey.objects.ttl(86400).create(
        id=uuid4(),
        user_id=g.user.id,
        tunnel_id=active_config.id,
        public_key=pub_key,
        fingerprint="SHA256:test-one",
        created_at=now_utc,
        expires_at=now_utc,
    )

    resp = flask_client.get(f"{API_PREFIX}/keys")

    assert resp.status_code == 200
    assert resp.content_type.startswith("text/plain")
    keys_text = resp.data.decode("utf-8")
    assert pub_key.strip() in keys_text


@pytest.mark.docker_required
def test_get_authorized_keys_forbidden_for_normal_user(flask_client: FlaskClient, argus_db, active_config, normal_user_identity):
    """GET /ssh/keys should fail for users without SSH tunnel server role."""
    previous_secret = flask_client.application.secret_key
    flask_client.application.secret_key = "test-secret"
    try:
        resp = flask_client.get(f"{API_PREFIX}/keys")
    finally:
        flask_client.application.secret_key = previous_secret

    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/")


@pytest.mark.docker_required
def test_get_authorized_keys_with_multiple_active_configs(flask_client: FlaskClient, argus_db, active_config, ssh_tunnel_server_identity):
    """API should still return keys when multiple active tunnel configs are present."""
    from datetime import UTC, datetime

    second = _make_active_config(is_active=True)
    try:
        key_one = _make_public_key()
        key_two = _make_public_key()
        now_utc = datetime.now(tz=UTC).replace(tzinfo=None)
        SSHTunnelKey.objects.ttl(86400).create(
            id=uuid4(),
            user_id=g.user.id,
            tunnel_id=active_config.id,
            public_key=key_one,
            fingerprint="SHA256:test-first",
            created_at=now_utc,
            expires_at=now_utc,
        )
        SSHTunnelKey.objects.ttl(86400).create(
            id=uuid4(),
            user_id=g.user.id,
            tunnel_id=second.id,
            public_key=key_two,
            fingerprint="SHA256:test-second",
            created_at=now_utc,
            expires_at=now_utc,
        )

        now_resp = flask_client.get(f"{API_PREFIX}/keys")
        assert now_resp.status_code == 200
        keys_text = now_resp.data.decode("utf-8")
        assert key_one.strip() in keys_text
        assert key_two.strip() in keys_text
    finally:
        try:
            second.delete()
        except Exception:
            pass


@pytest.mark.docker_required
def test_get_authorized_keys_empty_when_no_keys(flask_client: FlaskClient, argus_db, active_config, ssh_tunnel_server_identity):
    """GET /ssh/keys for an empty database should return empty text."""
    for row in SSHTunnelKey.objects.all():
        row.delete()
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


@pytest.mark.docker_required
def test_ssh_tunnel_server_role_cannot_call_other_api(flask_client: FlaskClient, argus_db, ssh_tunnel_server_identity):
    """ROLE_SSH_TUNNEL_SERVER should be hard-scoped to GET /client/ssh/keys only."""
    resp = flask_client.get("/api/v1/releases")
    assert resp.status_code == 403
    assert resp.json["status"] == "error"
    assert resp.json["message"] == "Authorization required"


# ---------------------------------------------------------------------------
# GET /api/v1/client/ssh/tunnel/keys
# ---------------------------------------------------------------------------

@pytest.mark.docker_required
def test_get_user_keys_returns_only_current_user(flask_client: FlaskClient, argus_db, active_config):
    from datetime import UTC, datetime

    own_key = _make_public_key()
    _json_post(flask_client, f"{API_PREFIX}/tunnel", {"public_key": own_key})

    foreign_key = _make_public_key()
    now_utc = datetime.now(tz=UTC).replace(tzinfo=None)
    SSHTunnelKey.objects.ttl(86400).create(
        id=uuid4(),
        user_id=uuid4(),
        tunnel_id=active_config.id,
        public_key=foreign_key,
        fingerprint="SHA256:foreign",
        created_at=now_utc,
        expires_at=now_utc,
    )

    resp = flask_client.get(f"{API_PREFIX}/tunnel/keys")
    assert resp.status_code == 200
    assert resp.json["status"] == "ok"

    rows = resp.json["response"]
    public_keys = {row["public_key"] for row in rows}
    assert own_key.strip() in public_keys
    assert foreign_key.strip() not in public_keys


@pytest.mark.docker_required
def test_get_user_keys_can_filter_by_tunnel(flask_client: FlaskClient, argus_db, active_config):
    from datetime import UTC, datetime

    own_key = _make_public_key()
    _json_post(flask_client, f"{API_PREFIX}/tunnel", {"public_key": own_key})

    second = _make_active_config(is_active=True)
    try:
        other_tunnel_key = _make_public_key()
        now_utc = datetime.now(tz=UTC).replace(tzinfo=None)
        SSHTunnelKey.objects.ttl(86400).create(
            id=uuid4(),
            user_id=g.user.id,
            tunnel_id=second.id,
            public_key=other_tunnel_key,
            fingerprint="SHA256:second-tunnel",
            created_at=now_utc,
            expires_at=now_utc,
        )

        resp = flask_client.get(f"{API_PREFIX}/tunnel/keys?tunnel_id={active_config.id}")
        assert resp.status_code == 200
        rows = resp.json["response"]
        keys = {row["public_key"] for row in rows}
        assert own_key.strip() in keys
        assert other_tunnel_key.strip() not in keys
    finally:
        try:
            second.delete()
        except Exception:
            pass
