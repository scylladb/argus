from datetime import UTC, datetime, timedelta
from io import StringIO
from unittest.mock import Mock
import os

import pytest

from argus.client.base import ArgusClient
from argus.client import tunnel_api
from argus.client import tunnel_ssh
from argus.client import tunnel_state
from argus.client.session import TunneledSession
from argus.client.tunnel import TunnelConfig


def _write_text(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _read_text(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class _DummyProcess:
    def __init__(self, stderr_text: str = ""):
        self._alive = True
        self.stderr = StringIO(stderr_text)

    def poll(self):
        return None if self._alive else 0

    def terminate(self):
        self._alive = False

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self._alive = False


@pytest.fixture
def tunnel_state_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("ARGUS_TUNNEL_STATE_DIR", str(tmp_path))
    return str(tmp_path)


def test_resolve_tunnel_config_registers_and_caches(tunnel_state_dir, monkeypatch):
    expires_at = datetime.now(tz=UTC) + timedelta(hours=6)
    config = TunnelConfig(
        proxy_host="proxy.example.com",
        proxy_port=22,
        proxy_user="argus-proxy",
        target_host="10.0.0.10",
        target_port=8080,
        host_key_fingerprint="SHA256:test",
        expires_at=expires_at,
        key_id="key-id",
        tunnel_id="tunnel-id",
    )

    def _fake_generate(paths):
        _write_text(paths.private_key, "private")
        _write_text(paths.public_key, "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITestKey")

    monkeypatch.setattr(tunnel_api, "generate_keypair_if_needed", _fake_generate)
    monkeypatch.setattr(tunnel_api, "_register_tunnel", lambda **kwargs: config)

    resolved = tunnel_api.resolve_tunnel_config(auth_token="token", base_url="https://argus.example.com")
    assert resolved is not None
    assert resolved.proxy_host == "proxy.example.com"

    paths = tunnel_state.get_tunnel_state_paths()
    assert os.path.exists(paths.config_cache)
    assert os.path.exists(paths.key_meta)

    monkeypatch.setattr(
        tunnel_api,
        "_get_tunnel_connection",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not call GET when cache is valid")),
    )
    cached = tunnel_api.resolve_tunnel_config(auth_token="token", base_url="https://argus.example.com")
    assert cached is not None
    assert cached.proxy_host == "proxy.example.com"


def test_tunnel_api_raises_on_connection_failure():
    mock_session = Mock(spec=tunnel_api.requests.Session)
    mock_session.get.side_effect = tunnel_api.requests.RequestException("connection refused")

    with pytest.raises(tunnel_api.TunnelClientError, match="Tunnel API call failed"):
        tunnel_api._call_tunnel_api(
            method="GET",
            url="https://argus.example.com/api/v1/client/ssh/tunnel",
            auth_token="token",
            payload=None,
            session=mock_session,
        )


def test_tunnel_api_succeeds_with_valid_response():
    class _Response:
        status_code = 200

        @staticmethod
        def json():
            return {
                "status": "ok",
                "response": {
                    "proxy_host": "proxy.example.com",
                    "proxy_port": 22,
                    "proxy_user": "argus-proxy",
                    "target_host": "10.0.0.10",
                    "target_port": 8080,
                    "host_key_fingerprint": "SHA256:test",
                },
            }

    mock_session = Mock(spec=tunnel_api.requests.Session)
    mock_session.get.return_value = _Response()

    data = tunnel_api._call_tunnel_api(
        method="GET",
        url="https://argus.example.com/api/v1/client/ssh/tunnel",
        auth_token="token",
        payload=None,
        session=mock_session,
    )
    assert data["proxy_host"] == "proxy.example.com"


def test_establish_uses_strict_host_options_and_temp_known_hosts(tunnel_state_dir, monkeypatch):
    paths = tunnel_state.get_tunnel_state_paths()
    _write_text(paths.private_key, "private")

    host_blob = "AQIDBA=="
    expected_fingerprint = tunnel_ssh.derive_fingerprint(f"ssh-ed25519 {host_blob}")
    config = TunnelConfig(
        proxy_host="proxy.example.com",
        proxy_port=22,
        proxy_user="argus-proxy",
        target_host="10.0.0.10",
        target_port=8080,
        host_key_fingerprint=expected_fingerprint,
    )

    monkeypatch.setattr(tunnel_ssh.shutil, "which", lambda cmd: f"/usr/bin/{cmd}")
    monkeypatch.setattr(
        tunnel_ssh,
        "scan_host_keys",
        lambda host, port: [f"{host} ssh-ed25519 {host_blob}"],
    )

    captured = {"commands": []}

    def _fake_popen(command, stdout, stderr, text):
        captured["commands"].append(command)
        return _DummyProcess()

    monkeypatch.setattr(tunnel_ssh.subprocess, "Popen", _fake_popen)
    monkeypatch.setattr(tunnel_ssh.SSHTunnel, "_wait_for_port_ready", staticmethod(lambda process, local_port: (True, "")))

    ssh_tunnel = tunnel_ssh.SSHTunnel(key_path=paths.private_key)
    local_port, reason = ssh_tunnel.establish(config)

    assert reason is None
    assert local_port is not None
    assert ssh_tunnel.local_port == local_port
    command = captured["commands"][0]
    command_text = " ".join(command)
    assert "StrictHostKeyChecking=yes" in command_text
    assert "GlobalKnownHostsFile=/dev/null" in command_text
    assert "HostKeyAlgorithms=ssh-ed25519,ecdsa-sha2-nistp256,ecdsa-sha2-nistp384,ecdsa-sha2-nistp521" in command_text
    assert "ssh-rsa" not in command_text

    known_hosts_path = ssh_tunnel._known_hosts_path
    assert known_hosts_path is not None
    assert os.path.exists(known_hosts_path)

    ssh_tunnel.shutdown()
    assert not os.path.exists(known_hosts_path)


def test_establish_retries_on_local_bind_conflict(tunnel_state_dir, monkeypatch):
    paths = tunnel_state.get_tunnel_state_paths()
    _write_text(paths.private_key, "private")

    config = TunnelConfig(
        proxy_host="proxy.example.com",
        proxy_port=22,
        proxy_user="argus-proxy",
        target_host="10.0.0.10",
        target_port=8080,
        host_key_fingerprint="SHA256:test",
    )

    monkeypatch.setattr(tunnel_ssh.shutil, "which", lambda cmd: f"/usr/bin/{cmd}")
    monkeypatch.setattr(
        tunnel_ssh.SSHTunnel,
        "_prepare_known_hosts_file",
        staticmethod(lambda cfg: tunnel_ssh.write_temp_known_hosts("proxy ssh-ed25519 AQIDBA==")),
    )

    call_state = {"calls": 0}

    def _fake_wait(process, local_port):
        call_state["calls"] += 1
        if call_state["calls"] == 1:
            return False, "Address already in use"
        return True, ""

    monkeypatch.setattr(tunnel_ssh.SSHTunnel, "_wait_for_port_ready", staticmethod(_fake_wait))
    monkeypatch.setattr(tunnel_ssh.subprocess, "Popen", lambda *args, **kwargs: _DummyProcess())

    ssh_tunnel = tunnel_ssh.SSHTunnel(key_path=paths.private_key)
    local_port, reason = ssh_tunnel.establish(config)

    assert reason is None
    assert local_port is not None
    assert call_state["calls"] == 2


def test_argus_client_warns_and_falls_back_when_tunnel_setup_fails(requests_mock, monkeypatch, caplog):
    requests_mock.get(
        "https://argus.scylladb.com/api/v1/client/testrun/test-type/test-id/get",
        json={"status": "ok", "response": {}},
        status_code=200,
    )

    monkeypatch.setattr("argus.client.session.resolve_tunnel_config_with_reason", lambda **kwargs: (None, "api unreachable"))

    client = ArgusClient(auth_token="token", base_url="https://argus.scylladb.com", use_tunnel=True)
    with caplog.at_level("WARNING"):
        response = client.get(
            endpoint=ArgusClient.Routes.GET,
            location_params={"type": "test-type", "id": "test-id"},
        )

    assert response.status_code == 200
    assert isinstance(client.session, TunneledSession)
    assert "api unreachable" in caplog.text
    assert "falling back to direct connection" in caplog.text


def test_argus_client_retries_tunnel_after_cooldown(requests_mock, monkeypatch):
    requests_mock.get(
        "https://argus.scylladb.com/api/v1/client/testrun/test-type/test-id/get",
        json={"status": "ok", "response": {}},
        status_code=200,
    )
    requests_mock.get(
        "http://127.0.0.1:9191/api/v1/client/testrun/test-type/test-id/get",
        json={"status": "ok", "response": {}},
        status_code=200,
    )

    config = TunnelConfig(
        proxy_host="proxy.example.com",
        proxy_port=22,
        proxy_user="argus-proxy",
        target_host="10.0.0.10",
        target_port=8080,
        host_key_fingerprint="SHA256:test",
    )
    resolve_state = {"calls": 0}

    def _resolve(**kwargs):
        resolve_state["calls"] += 1
        if resolve_state["calls"] == 1:
            return None, "first failure"
        return config, None

    class _FakeTunnel:
        def __init__(self):
            self.local_port = 9191

        def establish(self, cfg):
            return 9191, None

        def is_alive(self):
            return True

        def reconnect(self, cfg):
            return 9191, None

        def shutdown(self):
            return None

    monotonic_values = iter([1000.0, 1001.0, 1032.0])

    monkeypatch.setattr("argus.client.session.resolve_tunnel_config_with_reason", _resolve)
    monkeypatch.setattr("argus.client.session.SSHTunnel", _FakeTunnel)
    monkeypatch.setattr("argus.client.session.time.monotonic", lambda: next(monotonic_values))

    client = ArgusClient(auth_token="token", base_url="https://argus.scylladb.com", use_tunnel=True)

    client.get(endpoint=ArgusClient.Routes.GET, location_params={"type": "test-type", "id": "test-id"})
    assert client.session._tunnel_port is None
    assert client._base_url == "https://argus.scylladb.com"

    client.get(endpoint=ArgusClient.Routes.GET, location_params={"type": "test-type", "id": "test-id"})
    assert client.session._tunnel_port == 9191


def test_request_level_recovery_reconnects_and_retries_once(requests_mock, monkeypatch):
    old_tunnel_url = "http://127.0.0.1:9191/api/v1/client/testrun/test-type/test-id/get"
    new_tunnel_url = "http://127.0.0.1:9292/api/v1/client/testrun/test-type/test-id/get"

    requests_mock.get(old_tunnel_url, exc=tunnel_api.requests.ConnectionError("old tunnel is down"))
    requests_mock.get(new_tunnel_url, json={"status": "ok", "response": {}}, status_code=200)

    client = ArgusClient(auth_token="token", base_url="https://argus.scylladb.com", use_tunnel=True)
    client.session._tunnel_port = 9191

    ensure_state = {"calls": 0}

    def _fake_ensure_tunnel():
        ensure_state["calls"] += 1
        if ensure_state["calls"] >= 2:
            client.session._tunnel_port = 9292

    monkeypatch.setattr(client.session, "_ensure_tunnel", _fake_ensure_tunnel)

    response = client.get(
        endpoint=ArgusClient.Routes.GET,
        location_params={"type": "test-type", "id": "test-id"},
    )

    assert response.status_code == 200
    assert ensure_state["calls"] == 2
    assert client.session._tunnel_port == 9292


def test_request_level_recovery_falls_back_to_direct_when_retry_fails(requests_mock, monkeypatch):
    direct_url = "https://argus.scylladb.com/api/v1/client/testrun/test-type/test-id/get"
    tunnel_url = "http://127.0.0.1:9191/api/v1/client/testrun/test-type/test-id/get"

    requests_mock.get(tunnel_url, exc=tunnel_api.requests.ConnectionError("tunnel is dead"))
    requests_mock.get(direct_url, json={"status": "ok", "response": {}}, status_code=200)

    client = ArgusClient(auth_token="token", base_url="https://argus.scylladb.com", use_tunnel=True)
    client.session._tunnel_port = 9191

    def _ensure_keeps_tunnel():
        client.session._tunnel_port = 9191

    backoff_calls = {"count": 0}

    def _fake_backoff(reason):
        backoff_calls["count"] += 1
        client.session._tunnel_port = None

    monkeypatch.setattr(client.session, "_ensure_tunnel", _ensure_keeps_tunnel)
    monkeypatch.setattr(client.session, "_backoff", _fake_backoff)

    response = client.get(
        endpoint=ArgusClient.Routes.GET,
        location_params={"type": "test-type", "id": "test-id"},
    )

    assert response.status_code == 200
    assert backoff_calls["count"] == 1
    assert client.session._tunnel_port is None


def test_tunneled_session_starts_and_stops_monitor_thread():
    session = TunneledSession(auth_token="token", original_base_url="https://argus.scylladb.com")
    try:
        assert session._monitor_thread.is_alive()
    finally:
        session.close()

    session._monitor_thread.join(timeout=5)
    assert not session._monitor_thread.is_alive()


def test_tunneled_session_close_unregisters_atexit():
    import atexit as _atexit

    session = TunneledSession(auth_token="token", original_base_url="https://argus.scylladb.com")
    callback = session._atexit_close
    ref = session._atexit_ref
    session.close()
    # After close(), invoking the atexit callback must be a no-op (the session
    # was unregistered, and even if called manually it should not blow up).
    callback(ref)


def test_argus_client_works_as_context_manager(requests_mock, monkeypatch):
    requests_mock.get(
        "https://argus.scylladb.com/api/v1/client/testrun/test-type/test-id/get",
        json={"status": "ok", "response": {}},
        status_code=200,
    )
    monkeypatch.setattr(
        "argus.client.session.resolve_tunnel_config_with_reason",
        lambda **kwargs: (None, "api unreachable"),
    )

    with ArgusClient(auth_token="token", base_url="https://argus.scylladb.com", use_tunnel=True) as client:
        client.get(endpoint=ArgusClient.Routes.GET, location_params={"type": "test-type", "id": "test-id"})
        session = client.session
        assert session._monitor_thread.is_alive()

    session._monitor_thread.join(timeout=5)
    assert not session._monitor_thread.is_alive()


def test_backoff_does_not_wipe_cached_tunnel_state(tunnel_state_dir, monkeypatch):
    paths = tunnel_state.get_tunnel_state_paths()
    _write_text(paths.private_key, "private-key")
    _write_text(paths.public_key, "public-key")
    _write_text(paths.config_cache, '{"placeholder": "value"}')

    monkeypatch.setattr(
        "argus.client.session.resolve_tunnel_config_with_reason",
        lambda **kwargs: (None, "transient failure"),
    )

    session = TunneledSession(auth_token="token", original_base_url="https://argus.scylladb.com")
    try:
        session._ensure_tunnel()
        # Transient establish failure must NOT wipe the cached keypair —
        # otherwise every cooldown forces a fresh registration round-trip.
        assert os.path.exists(paths.private_key)
        assert os.path.exists(paths.public_key)
        assert os.path.exists(paths.config_cache)
    finally:
        session.close()


def test_call_tunnel_api_rejects_non_dict_payload():
    class _Response:
        status_code = 200

        @staticmethod
        def json():
            return ["unexpected", "list"]

    mock_session = Mock(spec=tunnel_api.requests.Session)
    mock_session.get.return_value = _Response()

    with pytest.raises(tunnel_api.TunnelClientError, match="invalid format"):
        tunnel_api._call_tunnel_api(
            method="GET",
            url="https://argus.example.com/api/v1/client/ssh/tunnel",
            auth_token="token",
            payload=None,
            session=mock_session,
        )


def test_prepare_known_hosts_file_accepts_full_known_hosts_entry(tunnel_state_dir):
    config = TunnelConfig(
        proxy_host="proxy.example.com",
        proxy_port=2222,
        proxy_user="argus-proxy",
        target_host="10.0.0.10",
        target_port=8080,
        host_key_fingerprint="some-other-name ssh-ed25519 AAAAdummybase64",
    )

    path = tunnel_ssh.SSHTunnel._prepare_known_hosts_file(config)
    try:
        contents = _read_text(path).strip()
        # Host token must be rewritten to the connection target with the
        # non-default port, not whatever the backend stored.
        assert contents.startswith("[proxy.example.com]:2222 ")
        assert "ssh-ed25519 AAAAdummybase64" in contents
    finally:
        tunnel_ssh._unlink(path)


def test_prepare_known_hosts_file_rejects_unknown_format(tunnel_state_dir):
    config = TunnelConfig(
        proxy_host="proxy.example.com",
        proxy_port=22,
        proxy_user="argus-proxy",
        target_host="10.0.0.10",
        target_port=8080,
        host_key_fingerprint="not-a-fingerprint",
    )

    with pytest.raises(tunnel_ssh.TunnelClientError, match="unrecognised format"):
        tunnel_ssh.SSHTunnel._prepare_known_hosts_file(config)
