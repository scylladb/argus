import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from flask import g
from flask.testing import FlaskClient

from argus.backend.models.ssh_key import ProxyTunnelConfig, SSHTunnelKey
from argus.backend.models.web import User
from argus.backend.service.tunnel_service import TunnelService

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


@pytest.fixture(autouse=True)
def mock_host_fingerprint(monkeypatch):
    monkeypatch.setattr(
        TunnelService,
        "_fetch_host_key",
        staticmethod(lambda host, _port: (f"{host} ssh-ed25519 AAAA{host}", f"SHA256:{host}")),
    )


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
        "host_key_fingerprint": None,
    }
    payload["host_key_fingerprint"] = f"SHA256:{payload['host']}"

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
        assert saved["host_key_fingerprint"] == f"SHA256:{payload['host']}"
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

        by_id_resp = flask_client.get(f"{API_PREFIX}/proxy-tunnel/config?tunnel_id={created_config_id}")
        assert by_id_resp.status_code == 200
        assert by_id_resp.json["status"] == "ok"
        assert by_id_resp.json["response"]["id"] == created_config_id
    finally:
        if created_config_id:
            try:
                ProxyTunnelConfig.get(id=created_config_id).delete()
            except Exception:
                pass
        _restore_active_configs(previous_active_ids)


@pytest.mark.docker_required
def test_admin_get_proxy_tunnel_config_without_id_is_non_mutating(flask_client: FlaskClient, argus_db):
    first_cfg = None
    second_cfg = None
    previous_active_ids = _deactivate_all_configs()
    try:
        first_payload = {
            "host": f"proxy-admin-first-{uuid4().hex[:8]}.example.com",
            "port": 22,
            "proxy_user": "argus-proxy",
            "target_host": "10.0.0.31",
            "target_port": 8080,
            "host_key_fingerprint": None,
        }
        first_payload["host_key_fingerprint"] = f"SHA256:{first_payload['host']}"
        second_payload = {
            "host": f"proxy-admin-second-{uuid4().hex[:8]}.example.com",
            "port": 22,
            "proxy_user": "argus-proxy",
            "target_host": "10.0.0.32",
            "target_port": 8080,
            "host_key_fingerprint": None,
        }
        second_payload["host_key_fingerprint"] = f"SHA256:{second_payload['host']}"

        first_resp = _json_post(flask_client, f"{API_PREFIX}/proxy-tunnel/config", first_payload)
        second_resp = _json_post(flask_client, f"{API_PREFIX}/proxy-tunnel/config", second_payload)
        assert first_resp.status_code == 200
        assert second_resp.status_code == 200
        first_cfg = first_resp.json["response"]["id"]
        second_cfg = second_resp.json["response"]["id"]

        read1 = flask_client.get(f"{API_PREFIX}/proxy-tunnel/config")
        read2 = flask_client.get(f"{API_PREFIX}/proxy-tunnel/config")
        assert read1.status_code == 200
        assert read2.status_code == 200
        assert read1.json["response"]["id"] == read2.json["response"]["id"]
        assert read1.json["response"]["id"] in {first_cfg, second_cfg}
    finally:
        if first_cfg:
            try:
                ProxyTunnelConfig.get(id=first_cfg).delete()
            except Exception:
                pass
        if second_cfg:
            try:
                ProxyTunnelConfig.get(id=second_cfg).delete()
            except Exception:
                pass
        _restore_active_configs(previous_active_ids)


@pytest.mark.docker_required
def test_admin_get_proxy_tunnel_config_ignores_inactive_tunnel_id(flask_client: FlaskClient, argus_db):
    cfg = ProxyTunnelConfig.create(
        id=uuid4(),
        host=f"proxy-inactive-id-{uuid4().hex[:8]}.example.com",
        port=22,
        proxy_user="argus-proxy",
        target_host="10.0.0.77",
        target_port=8080,
        host_key_fingerprint="SHA256:inactive-id",
        service_user_id=g.user.id,
        is_active=False,
    )
    try:
        resp = flask_client.get(f"{API_PREFIX}/proxy-tunnel/config?tunnel_id={cfg.id}")
        assert resp.status_code == 200
        assert resp.json["status"] == "ok"
        assert resp.json["response"] is None
    finally:
        try:
            cfg.delete()
        except Exception:
            pass


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
    assert any(row["key_id"] == str(key_id) for row in rows)

    delete_resp = flask_client.delete(f"{API_PREFIX}/ssh/keys/{key_id}")
    assert delete_resp.status_code == 200
    assert delete_resp.json["status"] == "ok"
    assert delete_resp.json["response"]["deleted"] is True

    with pytest.raises(SSHTunnelKey.DoesNotExist):
        SSHTunnelKey.get(id=key_id)


@pytest.mark.docker_required
def test_admin_can_list_and_toggle_proxy_tunnel_configs(flask_client: FlaskClient, argus_db):
    payload_active = {
        "host": f"proxy-list-active-{uuid4().hex[:8]}.example.com",
        "port": 22,
        "proxy_user": "argus-proxy",
        "target_host": "10.0.0.90",
        "target_port": 8080,
        "host_key_fingerprint": None,
    }
    payload_active["host_key_fingerprint"] = f"SHA256:{payload_active['host']}"
    payload_inactive = {
        "host": f"proxy-list-inactive-{uuid4().hex[:8]}.example.com",
        "port": 22,
        "proxy_user": "argus-proxy",
        "target_host": "10.0.0.91",
        "target_port": 8080,
        "host_key_fingerprint": None,
        "is_active": False,
    }
    payload_inactive["host_key_fingerprint"] = f"SHA256:{payload_inactive['host']}"

    active_id = None
    inactive_id = None
    try:
        active_resp = _json_post(flask_client, f"{API_PREFIX}/proxy-tunnel/config", payload_active)
        inactive_resp = _json_post(flask_client, f"{API_PREFIX}/proxy-tunnel/config", payload_inactive)
        assert active_resp.status_code == 200
        assert inactive_resp.status_code == 200
        active_id = active_resp.json["response"]["id"]
        inactive_id = inactive_resp.json["response"]["id"]

        list_all = flask_client.get(f"{API_PREFIX}/proxy-tunnel/configs")
        assert list_all.status_code == 200
        all_ids = {row["id"] for row in list_all.json["response"]}
        assert active_id in all_ids
        assert inactive_id in all_ids

        list_active = flask_client.get(f"{API_PREFIX}/proxy-tunnel/configs?active_only=true")
        assert list_active.status_code == 200
        active_ids = {row["id"] for row in list_active.json["response"]}
        assert active_id in active_ids
        assert inactive_id not in active_ids

        toggle_resp = _json_post(
            flask_client,
            f"{API_PREFIX}/proxy-tunnel/config/{inactive_id}/active",
            {"is_active": True},
        )
        assert toggle_resp.status_code == 200
        assert toggle_resp.json["response"]["is_active"] is True

        list_active_after = flask_client.get(f"{API_PREFIX}/proxy-tunnel/configs?active_only=true")
        assert list_active_after.status_code == 200
        active_ids_after = {row["id"] for row in list_active_after.json["response"]}
        assert inactive_id in active_ids_after
    finally:
        if active_id:
            try:
                ProxyTunnelConfig.get(id=active_id).delete()
            except Exception:
                pass
        if inactive_id:
            try:
                ProxyTunnelConfig.get(id=inactive_id).delete()
            except Exception:
                pass


@pytest.mark.docker_required
def test_admin_save_proxy_tunnel_config_rejects_username_collision(flask_client: FlaskClient, argus_db):
    host = f"proxy-collision-{uuid4().hex[:8]}.example.com"
    payload = {
        "host": host,
        "port": 22,
        "proxy_user": "argus-proxy",
        "target_host": "10.0.0.33",
        "target_port": 8080,
        "host_key_fingerprint": f"SHA256:{host}",
    }

    username = f"proxy-tunnel-{host}"
    now_utc = datetime.now(tz=UTC).replace(tzinfo=None)
    collision_user = User.create(
        id=uuid4(),
        username=username,
        full_name="Conflicting User",
        password="",
        email=f"{username}@example.com",
        registration_date=now_utc,
        roles=["ROLE_USER"],
        api_token="",
        service_user=False,
    )
    try:
        resp = _json_post(flask_client, f"{API_PREFIX}/proxy-tunnel/config", payload)
        assert resp.status_code == 200
        assert resp.json["status"] == "error"
        assert "already exists and is not a dedicated SSH tunnel service user" in resp.json["response"]["message"]
    finally:
        try:
            collision_user.delete()
        except Exception:
            pass


@pytest.mark.docker_required
@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("GET", f"{API_PREFIX}/proxy-tunnel/config", None),
        ("GET", f"{API_PREFIX}/proxy-tunnel/configs", None),
        (
            "POST",
            f"{API_PREFIX}/proxy-tunnel/config",
            {
                "host": "proxy-non-admin.example.com",
                "port": 22,
                "proxy_user": "argus-proxy",
                "target_host": "10.0.0.88",
                "target_port": 8080,
                "host_key_fingerprint": "SHA256:proxy-non-admin.example.com",
            },
        ),
        ("POST", f"{API_PREFIX}/proxy-tunnel/config/{uuid4()}/active", {"is_active": False}),
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
