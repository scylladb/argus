import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from flask import g
from flask.testing import FlaskClient

from argus.backend.models.ssh_key import ProxyTunnelConfig, SSHTunnelKey

API_PREFIX = "/admin/api/v1"


def _json_post(client: FlaskClient, url: str, payload: dict) -> object:
    return client.post(url, data=json.dumps(payload), content_type="application/json")


def _active_config_ids() -> list:
    return [cfg.id for cfg in ProxyTunnelConfig.objects.all() if cfg.is_active]


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


@pytest.fixture
def normal_user_identity():
    previous_roles = list(getattr(g.user, "roles", []))
    g.user.roles = ["ROLE_USER"]
    yield
    g.user.roles = previous_roles


@pytest.mark.docker_required
def test_admin_can_save_and_get_proxy_tunnel_config(flask_client: FlaskClient, argus_db):
    previous_active_ids = _deactivate_all_configs()
    created_config_id = None

    payload = {
        "host": f"proxy-admin-{uuid4().hex[:8]}.example.com",
        "port": 22,
        "proxy_user": "argus-proxy",
        "target_host": "10.0.0.99",
        "target_port": 8080,
        "host_key_fingerprint": "SHA256:admin-config",
    }

    try:
        save_resp = _json_post(flask_client, f"{API_PREFIX}/proxy-tunnel/config", payload)
        assert save_resp.status_code == 200
        assert save_resp.json["status"] == "ok"
        saved = save_resp.json["response"]

        assert saved["host"] == payload["host"]
        assert saved["port"] == payload["port"]
        assert saved["proxy_user"] == payload["proxy_user"]
        assert saved["target_host"] == payload["target_host"]
        assert saved["target_port"] == payload["target_port"]
        assert saved["host_key_fingerprint"] == payload["host_key_fingerprint"]
        assert saved["service_user_id"] is not None
        assert saved["api_token"] is not None
        created_config_id = saved["id"]

        get_resp = flask_client.get(f"{API_PREFIX}/proxy-tunnel/config")
        assert get_resp.status_code == 200
        assert get_resp.json["status"] == "ok"
        config = get_resp.json["response"]
        assert config is not None
        assert config["id"] == created_config_id
        assert config["host"] == payload["host"]
    finally:
        if created_config_id:
            try:
                ProxyTunnelConfig.get(id=created_config_id).delete()
            except Exception:
                pass
        _restore_active_configs(previous_active_ids)


@pytest.mark.docker_required
def test_admin_can_list_and_delete_ssh_key(flask_client: FlaskClient, argus_db):
    key_id = uuid4()
    tunnel_id = uuid4()
    now_utc = datetime.now(tz=UTC).replace(tzinfo=None)
    pub_key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFj+zV+Y9lW7eGLtQ+uY1M4NeC+YABN9nDl2sjp4rU0m"

    SSHTunnelKey.objects.ttl(86400).create(
        id=key_id,
        user_id=g.user.id,
        tunnel_id=tunnel_id,
        public_key=pub_key,
        fingerprint="SHA256:admin-key",
        created_at=now_utc,
        expires_at=now_utc,
    )

    list_resp = flask_client.get(f"{API_PREFIX}/ssh/keys")
    assert list_resp.status_code == 200
    assert list_resp.json["status"] == "ok"
    rows = list_resp.json["response"]
    assert any(row["id"] == str(key_id) for row in rows)

    delete_resp = flask_client.delete(f"{API_PREFIX}/ssh/keys/{key_id}")
    assert delete_resp.status_code == 200
    assert delete_resp.json["status"] == "ok"
    assert delete_resp.json["response"]["deleted"] is True

    with pytest.raises(SSHTunnelKey.DoesNotExist):
        SSHTunnelKey.get(id=key_id)


@pytest.mark.docker_required
@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("GET", f"{API_PREFIX}/proxy-tunnel/config", None),
        (
            "POST",
            f"{API_PREFIX}/proxy-tunnel/config",
            {
                "host": "proxy-non-admin.example.com",
                "port": 22,
                "proxy_user": "argus-proxy",
                "target_host": "10.0.0.88",
                "target_port": 8080,
                "host_key_fingerprint": "SHA256:non-admin",
            },
        ),
        ("GET", f"{API_PREFIX}/ssh/keys", None),
        ("DELETE", f"{API_PREFIX}/ssh/keys/{uuid4()}", None),
    ],
)
def test_admin_proxy_tunnel_endpoints_require_admin_role(
    flask_client: FlaskClient,
    argus_db,
    normal_user_identity,
    method: str,
    path: str,
    payload: dict | None,
):
    previous_secret = flask_client.application.secret_key
    flask_client.application.secret_key = "test-secret"
    try:
        if payload is None:
            resp = flask_client.open(path, method=method)
        else:
            resp = flask_client.open(path, method=method, json=payload)
    finally:
        flask_client.application.secret_key = previous_secret

    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/")
