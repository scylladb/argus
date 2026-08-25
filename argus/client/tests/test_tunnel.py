from datetime import datetime, timedelta, timezone
from io import StringIO
from unittest.mock import Mock
import atexit
import os
import time

import pytest

from argus.client.base import ArgusClient
from argus.client.tunnel import api as tunnel_api
from argus.client.tunnel import ssh as tunnel_ssh
from argus.client.tunnel import state as tunnel_state
from argus.client import session as session_mod
from argus.client.session import TunneledSession
from argus.client.tunnel import TunnelConfig
from argus.client.tunnel.models import parse_datetime


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


@pytest.fixture
def atexit_hooks(monkeypatch):
    """Record only the hooks registered inside the test.

    ``atexit._ncallbacks()`` counts the whole process. A monitor thread left
    running by another module registers a hook of its own mid-assertion, so a
    count taken around one ``close()`` measures the wrong thing.
    """
    hooks = []

    def register(func, *args, **kwargs):
        hooks.append(func)
        return func

    def unregister(func):
        while func in hooks:
            hooks.remove(func)

    monkeypatch.setattr(atexit, "register", register)
    monkeypatch.setattr(atexit, "unregister", unregister)
    return hooks


@pytest.fixture(autouse=True)
def offline_tunnel_resolver(monkeypatch):
    """Keep the monitor thread off the network.

    ``TunneledSession`` starts a monitor that tries to register a tunnel as
    soon as it is constructed. Tests that care about resolution override this
    with their own ``monkeypatch.setattr`` in the test body.
    """
    monkeypatch.setenv("ARGUS_TUNNEL_MIN_REQUESTS", "0")
    monkeypatch.setattr(
        "argus.client.session.resolve_tunnel_config_with_reason",
        lambda **kwargs: (None, None, "tunnel resolution disabled in tests"),
    )


def _write_key_dir(dir_path: str) -> None:
    os.makedirs(dir_path, mode=0o700, exist_ok=True)
    _write_text(os.path.join(dir_path, "key"), "private")
    _write_text(os.path.join(dir_path, "key.pub"), "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITestKey")
    _write_text(os.path.join(dir_path, "tunnel_config.json"), "{}")


def test_resolve_tunnel_config_registers_and_caches(tunnel_state_dir, monkeypatch):
    expires_at = datetime.now(tz=timezone.utc) + timedelta(hours=6)
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

    monkeypatch.setattr(tunnel_api, "_register_tunnel", lambda **kwargs: config)

    resolved, key_path = tunnel_api.resolve_tunnel_config(
        auth_token="token", base_url="https://argus.example.com", run_id="test-run-id"
    )
    assert resolved is not None
    assert resolved.proxy_host == "proxy.example.com"
    assert key_path is not None
    assert os.path.exists(key_path)

    key_dir = tunnel_state.find_existing_key_dir("test-run-id")
    assert key_dir is not None
    assert os.path.exists(key_dir.config_cache)

    monkeypatch.setattr(
        tunnel_api,
        "_get_tunnel_connection",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not call GET when cache is valid")),
    )
    cached, cached_key_path = tunnel_api.resolve_tunnel_config(
        auth_token="token", base_url="https://argus.example.com", run_id="test-run-id"
    )
    assert cached is not None
    assert cached.proxy_host == "proxy.example.com"
    assert cached_key_path == key_path


def test_resolve_tunnel_config_with_reason_rejects_an_empty_run_id(tunnel_state_dir):
    config, key_path, reason = tunnel_api.resolve_tunnel_config_with_reason(
        auth_token="token", base_url="https://argus.example.com", run_id=""
    )

    assert config is None
    assert key_path is None
    assert reason is not None


def test_resolve_tunnel_config_refreshes_an_existing_key_via_get(tunnel_state_dir, monkeypatch):
    root = tunnel_state.tunneling_root()
    future = datetime.now(tz=timezone.utc) + timedelta(hours=6)
    key_dir = os.path.join(root, tunnel_state._dirname_for("test-run-id", future))
    _write_key_dir(key_dir)

    refreshed = TunnelConfig(
        proxy_host="proxy.example.com",
        proxy_port=22,
        proxy_user="argus-proxy",
        target_host="10.0.0.10",
        target_port=8080,
        host_key_fingerprint="SHA256:test",
        expires_at=future,
    )
    monkeypatch.setattr(tunnel_api, "_get_tunnel_connection", lambda **kwargs: refreshed)

    config, key_path = tunnel_api.resolve_tunnel_config(
        auth_token="token", base_url="https://argus.example.com", run_id="test-run-id", force_refresh=True
    )

    assert config == refreshed
    assert key_path == os.path.join(key_dir, "key")


def test_resolve_tunnel_config_reregisters_when_the_get_refresh_fails(tunnel_state_dir, monkeypatch):
    root = tunnel_state.tunneling_root()
    future = datetime.now(tz=timezone.utc) + timedelta(hours=6)
    key_dir = os.path.join(root, tunnel_state._dirname_for("test-run-id", future))
    _write_key_dir(key_dir)

    registered = TunnelConfig(
        proxy_host="proxy.example.com",
        proxy_port=22,
        proxy_user="argus-proxy",
        target_host="10.0.0.10",
        target_port=8080,
        host_key_fingerprint="SHA256:test",
        expires_at=future + timedelta(hours=1),
    )
    monkeypatch.setattr(
        tunnel_api,
        "_get_tunnel_connection",
        lambda **kwargs: (_ for _ in ()).throw(tunnel_api.TunnelClientError("proxy unreachable")),
    )
    monkeypatch.setattr(tunnel_api, "_register_tunnel", lambda **kwargs: registered)

    config, key_path = tunnel_api.resolve_tunnel_config(
        auth_token="token", base_url="https://argus.example.com", run_id="test-run-id", force_refresh=True
    )

    assert config == registered
    assert key_path != os.path.join(key_dir, "key")


def test_resolve_tunnel_config_reports_a_registration_failure(tunnel_state_dir, monkeypatch):
    monkeypatch.setattr(
        tunnel_api,
        "_register_tunnel",
        lambda **kwargs: (_ for _ in ()).throw(tunnel_api.TunnelClientError("registration rejected")),
    )

    config, key_path, reason = tunnel_api.resolve_tunnel_config_with_reason(
        auth_token="token", base_url="https://argus.example.com", run_id="test-run-id"
    )

    assert config is None
    assert key_path is None
    assert "registration rejected" in reason


def test_find_existing_key_dir_scopes_by_run_id(tunnel_state_dir):
    root = tunnel_state.tunneling_root()
    future = datetime.now(tz=timezone.utc) + timedelta(hours=6)
    _write_key_dir(os.path.join(root, tunnel_state._dirname_for("run-aaa", future)))
    _write_key_dir(os.path.join(root, tunnel_state._dirname_for("run-bbb", future)))

    first = tunnel_state.find_existing_key_dir("run-aaa")
    second = tunnel_state.find_existing_key_dir("run-bbb")

    assert first is not None
    assert second is not None
    assert first.private_key != second.private_key
    assert os.path.basename(first.private_key) == "key"
    assert first.public_key == f"{first.private_key}.pub"
    assert first.config_cache == os.path.join(os.path.dirname(first.private_key), "tunnel_config.json")


def test_find_existing_key_dir_ignores_an_expired_directory(tunnel_state_dir):
    root = tunnel_state.tunneling_root()
    past = datetime.now(tz=timezone.utc) - timedelta(hours=1)
    _write_key_dir(os.path.join(root, tunnel_state._dirname_for("expired-run", past)))

    assert tunnel_state.find_existing_key_dir("expired-run") is None


def test_build_key_location_sanitizes_unsafe_run_id_characters(tunnel_state_dir):
    future = datetime.now(tz=timezone.utc) + timedelta(hours=6)
    paths = tunnel_state.build_key_location("../weird run/id", future)

    assert os.path.dirname(paths.state_dir) == tunnel_state.tunneling_root()
    assert os.path.basename(paths.state_dir).startswith("___weird_run_id.exp")


def test_build_key_location_falls_back_to_a_local_ttl_when_no_expiry_is_given(tunnel_state_dir):
    before = datetime.now(tz=timezone.utc)
    paths = tunnel_state.build_key_location("no-expiry-run", None)
    parsed = tunnel_state._parse_dirname(os.path.basename(paths.state_dir))

    assert parsed is not None
    _prefix, expires_at = parsed
    assert before < expires_at <= before + tunnel_state.LOCAL_FALLBACK_TTL + timedelta(seconds=5)


def test_find_existing_key_dir_rejects_an_empty_run_id(tunnel_state_dir):
    with pytest.raises(ValueError):
        tunnel_state.find_existing_key_dir("")


def test_delete_cached_tunnel_state_only_touches_its_own_run_id(tunnel_state_dir):
    root = tunnel_state.tunneling_root()
    future = datetime.now(tz=timezone.utc) + timedelta(hours=6)
    mine_dir = os.path.join(root, tunnel_state._dirname_for("mine", future))
    theirs_dir = os.path.join(root, tunnel_state._dirname_for("theirs", future))
    _write_key_dir(mine_dir)
    _write_key_dir(theirs_dir)

    tunnel_state.delete_cached_tunnel_state("mine")

    assert not os.path.exists(mine_dir)
    assert os.path.exists(theirs_dir)


def test_sweep_stale_tunnel_keys_removes_only_expired_keys(tunnel_state_dir):
    root = tunnel_state.tunneling_root()
    past = datetime.now(tz=timezone.utc) - timedelta(hours=1)
    future = datetime.now(tz=timezone.utc) + timedelta(hours=6)
    expired_dir = os.path.join(root, tunnel_state._dirname_for("expired-run", past))
    fresh_dir = os.path.join(root, tunnel_state._dirname_for("fresh-run", future))
    _write_key_dir(expired_dir)
    _write_key_dir(fresh_dir)

    tunnel_state.sweep_stale_tunnel_keys()

    assert not os.path.exists(expired_dir)
    assert os.path.exists(fresh_dir)


def test_sweep_stale_tunnel_keys_ignores_a_directory_with_no_expiry_suffix(tunnel_state_dir):
    root = tunnel_state.tunneling_root()
    broken_dir = os.path.join(root, "not-an-argus-tunnel-directory")
    _write_key_dir(broken_dir)

    tunnel_state.sweep_stale_tunnel_keys()

    assert os.path.exists(broken_dir)


def test_resolve_tunnel_config_sweeps_stale_siblings_before_registering(tunnel_state_dir, monkeypatch):
    root = tunnel_state.tunneling_root()
    past = datetime.now(tz=timezone.utc) - timedelta(hours=1)
    stale_dir = os.path.join(root, tunnel_state._dirname_for("stale-run", past))
    _write_key_dir(stale_dir)

    config = TunnelConfig(
        proxy_host="proxy.example.com",
        proxy_port=22,
        proxy_user="argus-proxy",
        target_host="10.0.0.10",
        target_port=8080,
        host_key_fingerprint="SHA256:test",
        expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=6),
    )
    monkeypatch.setattr(tunnel_api, "_register_tunnel", lambda **kwargs: config)

    resolved, key_path = tunnel_api.resolve_tunnel_config(
        auth_token="token", base_url="https://argus.example.com", run_id="new-run"
    )

    assert resolved is not None
    assert not os.path.exists(stale_dir)
    new_dir = tunnel_state.find_existing_key_dir("new-run")
    assert new_dir is not None
    assert key_path == new_dir.private_key
    assert os.path.exists(new_dir.private_key)
    assert os.path.exists(new_dir.public_key)


def test_delete_cached_tunnel_state_ignores_an_empty_run_id(tunnel_state_dir):
    tunnel_state.delete_cached_tunnel_state("")


def test_generate_keypair_with_cryptography_writes_a_keypair(tunnel_state_dir, monkeypatch):
    class _FakePublicKey:
        def public_bytes(self, encoding, format):
            return b"ssh-ed25519 AAAAFakePublicKeyBytes"

    class _FakePrivateKey:
        def public_key(self):
            return _FakePublicKey()

        def private_bytes(self, encoding, format, encryption_algorithm):
            return b"fake-private-key-material"

    class _FakeEd25519PrivateKey:
        @staticmethod
        def generate():
            return _FakePrivateKey()

    monkeypatch.setattr(tunnel_state, "Ed25519PrivateKey", _FakeEd25519PrivateKey)
    monkeypatch.setattr(tunnel_state, "Encoding", type("Encoding", (), {"PEM": 1, "OpenSSH": 2}))
    monkeypatch.setattr(tunnel_state, "PrivateFormat", type("PrivateFormat", (), {"OpenSSH": 1}))
    monkeypatch.setattr(tunnel_state, "PublicFormat", type("PublicFormat", (), {"OpenSSH": 1}))
    monkeypatch.setattr(tunnel_state, "NoEncryption", lambda: None)

    paths = tunnel_state._paths_for_dir(tunnel_state_dir)
    assert tunnel_state._generate_keypair_with_cryptography(paths) is True
    assert _read_text(paths.private_key) == "fake-private-key-material"
    assert _read_text(paths.public_key).startswith("ssh-ed25519")


def test_generate_keypair_with_cryptography_falls_back_on_error(tunnel_state_dir, monkeypatch):
    class _BrokenEd25519PrivateKey:
        @staticmethod
        def generate():
            raise RuntimeError("no entropy source")

    monkeypatch.setattr(tunnel_state, "Ed25519PrivateKey", _BrokenEd25519PrivateKey)

    paths = tunnel_state._paths_for_dir(tunnel_state_dir)
    assert tunnel_state._generate_keypair_with_cryptography(paths) is False


def test_generate_keypair_falls_back_to_ssh_keygen_when_cryptography_is_unavailable(tunnel_state_dir, monkeypatch):
    monkeypatch.setattr(tunnel_state, "Ed25519PrivateKey", None)

    paths = tunnel_state._paths_for_dir(tunnel_state_dir)
    tunnel_state._generate_keypair(paths)

    assert os.path.exists(paths.private_key)
    assert os.path.exists(paths.public_key)


def test_generate_keypair_uses_cryptography_when_available(tunnel_state_dir, monkeypatch):
    monkeypatch.setattr(tunnel_state, "_generate_keypair_with_cryptography", lambda paths: True)

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("ssh-keygen should not run when cryptography already wrote the keypair")

    monkeypatch.setattr(tunnel_state.subprocess, "run", _fail_if_called)

    paths = tunnel_state._paths_for_dir(tunnel_state_dir)
    tunnel_state._generate_keypair(paths)


def test_generate_keypair_raises_when_neither_backend_is_available(tunnel_state_dir, monkeypatch):
    monkeypatch.setattr(tunnel_state, "Ed25519PrivateKey", None)
    monkeypatch.setattr(tunnel_state.shutil, "which", lambda cmd: None)

    paths = tunnel_state._paths_for_dir(tunnel_state_dir)
    with pytest.raises(tunnel_state.TunnelClientError, match="ssh-keygen"):
        tunnel_state._generate_keypair(paths)


def test_generate_keypair_raises_when_ssh_keygen_fails(tunnel_state_dir, monkeypatch):
    monkeypatch.setattr(tunnel_state, "Ed25519PrivateKey", None)

    class _FailedResult:
        returncode = 1
        stderr = "ssh-keygen: could not create directory"

    monkeypatch.setattr(tunnel_state.subprocess, "run", lambda *args, **kwargs: _FailedResult())

    paths = tunnel_state._paths_for_dir(tunnel_state_dir)
    with pytest.raises(tunnel_state.TunnelClientError, match="ssh-keygen failed"):
        tunnel_state._generate_keypair(paths)


def test_read_cached_tunnel_config_ignores_a_missing_cache_file(tunnel_state_dir):
    paths = tunnel_state._paths_for_dir(tunnel_state_dir)

    assert tunnel_state.read_cached_tunnel_config(paths) is None


def test_read_cached_tunnel_config_ignores_unparsable_json(tunnel_state_dir):
    paths = tunnel_state._paths_for_dir(tunnel_state_dir)
    _write_text(paths.config_cache, "not json")

    assert tunnel_state.read_cached_tunnel_config(paths) is None


def test_read_cached_tunnel_config_ignores_a_payload_missing_required_fields(tunnel_state_dir):
    paths = tunnel_state._paths_for_dir(tunnel_state_dir)
    _write_text(paths.config_cache, '{"proxy_host": "proxy.example.com"}')

    assert tunnel_state.read_cached_tunnel_config(paths) is None


def test_read_cached_tunnel_config_ignores_an_expired_payload(tunnel_state_dir):
    paths = tunnel_state._paths_for_dir(tunnel_state_dir)
    config = TunnelConfig(
        proxy_host="proxy.example.com",
        proxy_port=22,
        proxy_user="argus-proxy",
        target_host="10.0.0.10",
        target_port=8080,
        host_key_fingerprint="SHA256:test",
        expires_at=datetime.now(tz=timezone.utc) - timedelta(hours=1),
    )
    tunnel_state.write_tunnel_cache(paths, config)

    assert tunnel_state.read_cached_tunnel_config(paths) is None


def test_prepare_state_dir_creates_a_missing_directory(tmp_path):
    candidate = os.path.join(tmp_path, "not-yet-created")

    assert tunnel_state._prepare_state_dir(candidate) is True
    assert os.path.isdir(candidate)


def test_prepare_state_dir_rejects_a_path_that_is_a_file(tmp_path):
    candidate = os.path.join(tmp_path, "a-plain-file")
    _write_text(candidate, "not a directory")

    assert tunnel_state._prepare_state_dir(candidate) is False


def test_prepare_state_dir_rejects_an_inaccessible_directory(tmp_path, monkeypatch):
    candidate = os.path.join(tmp_path, "locked-down")
    os.makedirs(candidate)
    monkeypatch.setattr(tunnel_state.os, "access", lambda path, mode: False)

    assert tunnel_state._prepare_state_dir(candidate) is False


def test_prepare_state_dir_returns_false_on_makedirs_failure(tmp_path, monkeypatch):
    candidate = os.path.join(tmp_path, "unmakeable")
    monkeypatch.setattr(
        tunnel_state.os,
        "makedirs",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("permission denied")),
    )

    assert tunnel_state._prepare_state_dir(candidate) is False


def test_resolve_state_dir_raises_when_no_candidate_is_usable(monkeypatch):
    monkeypatch.delenv("ARGUS_TUNNEL_STATE_DIR", raising=False)
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setattr(tunnel_state, "_prepare_state_dir", lambda path: False)

    with pytest.raises(OSError, match="No writable directory"):
        tunnel_state._resolve_state_dir()


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


@pytest.mark.parametrize(
    "value",
    [
        "2026-04-16T12:00:00Z",  # Zulu suffix as emitted by the tunnel API
        "2026-04-16T12:00:00+00:00",  # explicit offset
        "2026-04-16T12:00:00",  # naive -> assumed UTC
    ],
)
def test_parse_datetime_normalizes_to_utc(value):
    # Regression: Python 3.10's fromisoformat rejects the trailing "Z"; parse_datetime
    # must accept it (and any of these forms) and return a UTC-aware datetime.
    parsed = parse_datetime(value)
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == timedelta(0)
    assert (parsed.year, parsed.month, parsed.day, parsed.hour) == (2026, 4, 16, 12)


def test_from_api_response_accepts_zulu_expires_at():
    config = TunnelConfig.from_api_response(
        {
            "proxy_host": "proxy.example.com",
            "proxy_port": 22,
            "proxy_user": "argus-proxy",
            "target_host": "10.0.0.10",
            "target_port": 8080,
            "host_key_fingerprint": "SHA256:test",
            "expires_at": "2026-04-16T12:00:00Z",
        }
    )
    assert config.expires_at == datetime(2026, 4, 16, 12, 0, 0, tzinfo=timezone.utc)


def test_establish_uses_strict_host_options_and_temp_known_hosts(tunnel_state_dir, monkeypatch):
    private_key_path = os.path.join(tunnel_state_dir, "key")
    _write_text(private_key_path, "private")

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
    monkeypatch.setattr(
        tunnel_ssh.SSHTunnel, "_wait_for_port_ready", staticmethod(lambda process, local_port: (True, ""))
    )

    ssh_tunnel = tunnel_ssh.SSHTunnel(key_path=private_key_path)
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


def test_shutdown_drops_the_atexit_hook_so_reconnects_do_not_accumulate(tunnel_state_dir, monkeypatch, atexit_hooks):
    """The monitor builds a new SSHTunnel per reconnect.

    A hook that outlives its tunnel keeps that dead tunnel reachable and grows
    the atexit list once per reconnect for the life of the process.
    """
    private_key_path = os.path.join(tunnel_state_dir, "key")
    _write_text(private_key_path, "private")

    host_blob = "AQIDBA=="
    config = TunnelConfig(
        proxy_host="proxy.example.com",
        proxy_port=22,
        proxy_user="argus-proxy",
        target_host="10.0.0.10",
        target_port=8080,
        host_key_fingerprint=tunnel_ssh.derive_fingerprint(f"ssh-ed25519 {host_blob}"),
    )
    monkeypatch.setattr(tunnel_ssh.shutil, "which", lambda cmd: f"/usr/bin/{cmd}")
    monkeypatch.setattr(tunnel_ssh, "scan_host_keys", lambda host, port: [f"{host} ssh-ed25519 {host_blob}"])
    monkeypatch.setattr(tunnel_ssh.subprocess, "Popen", lambda command, stdout, stderr, text: _DummyProcess())
    monkeypatch.setattr(
        tunnel_ssh.SSHTunnel, "_wait_for_port_ready", staticmethod(lambda process, local_port: (True, ""))
    )

    tunnels = []
    for _ in range(3):
        ssh_tunnel = tunnel_ssh.SSHTunnel(key_path=private_key_path)
        assert ssh_tunnel.establish(config)[0] is not None
        assert ssh_tunnel.shutdown in atexit_hooks
        ssh_tunnel.shutdown()
        assert ssh_tunnel.shutdown not in atexit_hooks
        tunnels.append(ssh_tunnel)

    assert not [t for t in tunnels if t.shutdown in atexit_hooks]


def test_establish_retries_on_local_bind_conflict(tunnel_state_dir, monkeypatch):
    private_key_path = os.path.join(tunnel_state_dir, "key")
    _write_text(private_key_path, "private")

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

    ssh_tunnel = tunnel_ssh.SSHTunnel(key_path=private_key_path)
    local_port, reason = ssh_tunnel.establish(config)

    assert reason is None
    assert local_port is not None
    assert call_state["calls"] == 2


def test_establish_flags_sshd_key_rejection(tunnel_state_dir, monkeypatch):
    private_key_path = os.path.join(tunnel_state_dir, "key")
    _write_text(private_key_path, "private")

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
    monkeypatch.setattr(
        tunnel_ssh.SSHTunnel,
        "_wait_for_port_ready",
        staticmethod(lambda process, local_port: (False, "Permission denied (publickey).")),
    )
    monkeypatch.setattr(tunnel_ssh.subprocess, "Popen", lambda *args, **kwargs: _DummyProcess())

    ssh_tunnel = tunnel_ssh.SSHTunnel(key_path=private_key_path)
    local_port, reason = ssh_tunnel.establish(config)

    assert local_port is None
    assert reason is not None
    assert ssh_tunnel.sshd_rejected_key is True


def test_establish_does_not_flag_a_network_failure_as_key_rejection(tunnel_state_dir, monkeypatch):
    private_key_path = os.path.join(tunnel_state_dir, "key")
    _write_text(private_key_path, "private")

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
    monkeypatch.setattr(
        tunnel_ssh.SSHTunnel,
        "_wait_for_port_ready",
        staticmethod(lambda process, local_port: (False, "Connection timed out")),
    )
    monkeypatch.setattr(tunnel_ssh.subprocess, "Popen", lambda *args, **kwargs: _DummyProcess())

    ssh_tunnel = tunnel_ssh.SSHTunnel(key_path=private_key_path)
    local_port, reason = ssh_tunnel.establish(config)

    assert local_port is None
    assert ssh_tunnel.sshd_rejected_key is False


def _config_with_fingerprint(fingerprint: str) -> TunnelConfig:
    return TunnelConfig(
        proxy_host="proxy.example.com",
        proxy_port=22,
        proxy_user="argus-proxy",
        target_host="10.0.0.10",
        target_port=8080,
        host_key_fingerprint=fingerprint,
    )


def test_missing_ssh_binary_is_a_preflight_error(tunnel_state_dir, monkeypatch):
    private_key_path = os.path.join(tunnel_state_dir, "key")
    _write_text(private_key_path, "private")
    monkeypatch.setattr(tunnel_ssh.shutil, "which", lambda cmd: None)

    ssh_tunnel = tunnel_ssh.SSHTunnel(key_path=private_key_path)
    local_port, reason = ssh_tunnel.establish(_config_with_fingerprint("SHA256:test"))

    assert local_port is None
    assert reason == "ssh binary was not found on PATH"


def test_missing_ssh_keyscan_binary_is_a_preflight_error(tunnel_state_dir, monkeypatch):
    private_key_path = os.path.join(tunnel_state_dir, "key")
    _write_text(private_key_path, "private")
    monkeypatch.setattr(tunnel_ssh.shutil, "which", lambda cmd: None if cmd == "ssh-keyscan" else f"/usr/bin/{cmd}")

    ssh_tunnel = tunnel_ssh.SSHTunnel(key_path=private_key_path)
    local_port, reason = ssh_tunnel.establish(_config_with_fingerprint("SHA256:test"))

    assert local_port is None
    assert reason == "ssh-keyscan binary was not found on PATH"


def test_missing_key_file_is_a_preflight_error(tunnel_state_dir, monkeypatch):
    monkeypatch.setattr(tunnel_ssh.shutil, "which", lambda cmd: f"/usr/bin/{cmd}")
    missing_key_path = os.path.join(tunnel_state_dir, "no-such-key")

    ssh_tunnel = tunnel_ssh.SSHTunnel(key_path=missing_key_path)
    local_port, reason = ssh_tunnel.establish(_config_with_fingerprint("SHA256:test"))

    assert local_port is None
    assert reason == f"SSH private key does not exist: {missing_key_path}"


def test_preflight_binaries_are_resolved_once_not_per_establish_call(tunnel_state_dir, monkeypatch):
    private_key_path = os.path.join(tunnel_state_dir, "key")
    _write_text(private_key_path, "private")
    host_blob = "AQIDBA=="
    config = _config_with_fingerprint(tunnel_ssh.derive_fingerprint(f"ssh-ed25519 {host_blob}"))

    which_calls = []

    def _which(cmd):
        which_calls.append(cmd)
        return f"/usr/bin/{cmd}"

    monkeypatch.setattr(tunnel_ssh.shutil, "which", _which)
    monkeypatch.setattr(tunnel_ssh, "scan_host_keys", lambda host, port: [f"{host} ssh-ed25519 {host_blob}"])
    monkeypatch.setattr(tunnel_ssh.subprocess, "Popen", lambda *args, **kwargs: _DummyProcess())
    monkeypatch.setattr(
        tunnel_ssh.SSHTunnel, "_wait_for_port_ready", staticmethod(lambda process, local_port: (True, ""))
    )

    ssh_tunnel = tunnel_ssh.SSHTunnel(key_path=private_key_path)
    calls_after_init = len(which_calls)
    assert ssh_tunnel.establish(config)[0] is not None
    assert ssh_tunnel.establish(config)[0] is not None

    assert len(which_calls) == calls_after_init


def test_establish_reports_invalid_host_key_fingerprint(tunnel_state_dir, monkeypatch):
    private_key_path = os.path.join(tunnel_state_dir, "key")
    _write_text(private_key_path, "private")
    monkeypatch.setattr(tunnel_ssh.shutil, "which", lambda cmd: f"/usr/bin/{cmd}")

    ssh_tunnel = tunnel_ssh.SSHTunnel(key_path=private_key_path)
    local_port, reason = ssh_tunnel.establish(_config_with_fingerprint("not-a-real-format"))

    assert local_port is None
    assert reason is not None
    assert reason.startswith("strict host verification failed")


def test_establish_reports_a_failure_to_spawn_ssh(tunnel_state_dir, monkeypatch):
    private_key_path = os.path.join(tunnel_state_dir, "key")
    _write_text(private_key_path, "private")
    host_blob = "AQIDBA=="
    config = _config_with_fingerprint(tunnel_ssh.derive_fingerprint(f"ssh-ed25519 {host_blob}"))

    monkeypatch.setattr(tunnel_ssh.shutil, "which", lambda cmd: f"/usr/bin/{cmd}")
    monkeypatch.setattr(tunnel_ssh, "scan_host_keys", lambda host, port: [f"{host} ssh-ed25519 {host_blob}"])

    def _raise_popen(*args, **kwargs):
        raise OSError("out of file descriptors")

    monkeypatch.setattr(tunnel_ssh.subprocess, "Popen", _raise_popen)

    ssh_tunnel = tunnel_ssh.SSHTunnel(key_path=private_key_path)
    local_port, reason = ssh_tunnel.establish(config)

    assert local_port is None
    assert "failed to spawn ssh process" in reason


def test_establish_gives_up_after_persistent_bind_conflicts(tunnel_state_dir, monkeypatch):
    private_key_path = os.path.join(tunnel_state_dir, "key")
    _write_text(private_key_path, "private")
    host_blob = "AQIDBA=="
    config = _config_with_fingerprint(tunnel_ssh.derive_fingerprint(f"ssh-ed25519 {host_blob}"))

    monkeypatch.setattr(tunnel_ssh.shutil, "which", lambda cmd: f"/usr/bin/{cmd}")
    monkeypatch.setattr(tunnel_ssh, "scan_host_keys", lambda host, port: [f"{host} ssh-ed25519 {host_blob}"])
    monkeypatch.setattr(tunnel_ssh.subprocess, "Popen", lambda *args, **kwargs: _DummyProcess())
    monkeypatch.setattr(
        tunnel_ssh.SSHTunnel,
        "_wait_for_port_ready",
        staticmethod(lambda process, local_port: (False, "Address already in use")),
    )

    ssh_tunnel = tunnel_ssh.SSHTunnel(key_path=private_key_path)
    local_port, reason = ssh_tunnel.establish(config)

    assert local_port is None
    assert "establish failed after" in reason


def test_is_alive_reflects_the_real_process_and_port_state(tunnel_state_dir, monkeypatch):
    private_key_path = os.path.join(tunnel_state_dir, "key")
    _write_text(private_key_path, "private")
    host_blob = "AQIDBA=="
    config = _config_with_fingerprint(tunnel_ssh.derive_fingerprint(f"ssh-ed25519 {host_blob}"))

    monkeypatch.setattr(tunnel_ssh.shutil, "which", lambda cmd: f"/usr/bin/{cmd}")
    monkeypatch.setattr(tunnel_ssh, "scan_host_keys", lambda host, port: [f"{host} ssh-ed25519 {host_blob}"])
    process = _DummyProcess()
    monkeypatch.setattr(tunnel_ssh.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(
        tunnel_ssh.SSHTunnel, "_wait_for_port_ready", staticmethod(lambda process, local_port: (True, ""))
    )
    monkeypatch.setattr(tunnel_ssh, "is_local_port_open", lambda port: True)

    ssh_tunnel = tunnel_ssh.SSHTunnel(key_path=private_key_path)

    assert ssh_tunnel.is_alive() is False

    local_port, _reason = ssh_tunnel.establish(config)
    assert local_port is not None
    assert ssh_tunnel.is_alive() is True

    process.terminate()
    assert ssh_tunnel.is_alive() is False


def test_argus_client_warns_and_falls_back_when_tunnel_setup_fails(requests_mock, monkeypatch, caplog, tmp_path):
    requests_mock.get(
        "https://argus.scylladb.com/api/v1/client/testrun/test-type/test-id/get",
        json={"status": "ok", "response": {}},
        status_code=200,
    )

    monkeypatch.setattr(
        "argus.client.session.resolve_tunnel_config_with_reason", lambda **kwargs: (None, None, "api unreachable")
    )

    client = ArgusClient(
        auth_token="token",
        base_url="https://argus.scylladb.com",
        log_dir=tmp_path,
        use_tunnel=True,
        run_id="test-run-id",
    )
    with caplog.at_level("WARNING"):
        response = client.get(
            endpoint=ArgusClient.Routes.GET,
            location_params={"type": "test-type", "id": "test-id"},
        )

    assert response.status_code == 200
    assert isinstance(client.session, TunneledSession)
    assert "api unreachable" in caplog.text
    assert "using a direct connection" in caplog.text


class _FakeTunnel:
    """Stand-in for :class:`SSHTunnel` that reports a fixed local port."""

    def __init__(self, key_path: str = "", local_port: int = 9191):
        self.local_port = local_port
        self.shutdown_calls = 0

    def establish(self, cfg):
        return self.local_port, None

    def is_alive(self):
        return True

    def shutdown(self):
        self.shutdown_calls += 1


def _wait_until(predicate, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


@pytest.fixture
def fast_tunnel_retry(monkeypatch):
    """Collapse the monitor timings so retry behaviour is testable in-process."""
    monkeypatch.setenv("ARGUS_TUNNEL_MONITOR_INTERVAL", "0.01")
    monkeypatch.setenv("ARGUS_TUNNEL_RETRY_MIN_SECONDS", "0.01")
    monkeypatch.setenv("ARGUS_TUNNEL_RETRY_MAX_SECONDS", "0.05")


def test_monitor_thread_retries_tunnel_without_a_request(fast_tunnel_retry, monkeypatch):
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
            return None, None, "first failure"
        return config, "/fake/key/path", None

    monkeypatch.setattr("argus.client.session.resolve_tunnel_config_with_reason", _resolve)
    monkeypatch.setattr("argus.client.session.SSHTunnel", _FakeTunnel)

    session = TunneledSession(auth_token="token", original_base_url="https://argus.scylladb.com", run_id="test-run-id")
    try:
        assert _wait_until(lambda: session._tunnel_port == 9191), "monitor never recovered the tunnel"
        assert resolve_state["calls"] >= 2
    finally:
        session.close()


def _api_response_with_proxies() -> dict:
    return {
        "proxy_host": "proxy-a.example.com",
        "proxy_port": 22,
        "proxy_user": "argus-proxy",
        "target_host": "10.0.0.10",
        "target_port": 8080,
        "host_key_fingerprint": "entry-a ssh-ed25519 AAAA",
        "tunnel_id": "tun-a",
        "proxies": [
            {
                "proxy_host": "proxy-a.example.com",
                "proxy_port": 22,
                "proxy_user": "argus-proxy",
                "target_host": "10.0.0.10",
                "target_port": 8080,
                "host_key_fingerprint": "entry-a ssh-ed25519 AAAA",
                "tunnel_id": "tun-a",
            },
            {
                "proxy_host": "proxy-b.example.com",
                "proxy_port": 2222,
                "proxy_user": "argus-proxy",
                "target_host": "10.0.0.11",
                "target_port": 8080,
                "host_key_fingerprint": "entry-b ssh-ed25519 BBBB",
                "tunnel_id": "tun-b",
            },
        ],
    }


def test_tunnel_config_parses_failover_list_without_duplicating_primary():
    config = TunnelConfig.from_api_response(_api_response_with_proxies())

    assert config.proxy_host == "proxy-a.example.com"
    assert len(config.alternates) == 1
    assert config.alternates[0].proxy_host == "proxy-b.example.com"
    assert config.alternates[0].proxy_port == 2222
    assert [c.proxy_host for c in config.candidates()] == ["proxy-a.example.com", "proxy-b.example.com"]


def test_candidates_carry_the_key_id_onto_alternates():
    """Attribution headers must survive a failover; the key is the same either way."""
    payload = _api_response_with_proxies()
    payload["key_id"] = "key-uuid-1"

    config = TunnelConfig.from_api_response(payload)
    alternate = config.candidates()[1]

    assert alternate.proxy_host == "proxy-b.example.com"
    assert alternate.key_id == "key-uuid-1"
    # Stored alternates stay bare endpoints; enrichment happens on read.
    assert config.alternates[0].key_id is None


def test_tunnel_config_without_proxies_has_no_alternates():
    payload = _api_response_with_proxies()
    del payload["proxies"]

    config = TunnelConfig.from_api_response(payload)

    assert config.alternates == ()
    assert config.candidates() == (config,)


def test_tunnel_config_skips_malformed_alternates():
    payload = _api_response_with_proxies()
    payload["proxies"].append({"proxy_host": "broken.example.com"})
    payload["proxies"].append("not-a-dict")

    config = TunnelConfig.from_api_response(payload)

    assert [c.proxy_host for c in config.alternates] == ["proxy-b.example.com"]


def test_tunnel_config_cache_round_trips_alternates():
    config = TunnelConfig.from_api_response(_api_response_with_proxies())

    restored = TunnelConfig.from_api_response(config.to_cache_payload())

    assert restored == config


def test_session_fails_over_to_the_next_proxy(monkeypatch):
    config = TunnelConfig.from_api_response(_api_response_with_proxies())
    attempted = []

    class _FailFirstTunnel:
        def __init__(self, key_path: str = ""):
            self.local_port = None

        def establish(self, cfg):
            attempted.append(cfg.proxy_host)
            if cfg.proxy_host == "proxy-a.example.com":
                return None, "connection refused"
            self.local_port = 9292
            return 9292, None

        def is_alive(self):
            return self.local_port is not None

        def shutdown(self):
            return None

    monkeypatch.setattr(
        "argus.client.session.resolve_tunnel_config_with_reason", lambda **kwargs: (config, "/fake/key/path", None)
    )
    monkeypatch.setattr("argus.client.session.SSHTunnel", _FailFirstTunnel)

    session = TunneledSession(auth_token="token", original_base_url="https://argus.scylladb.com", run_id="test-run-id")
    try:
        assert session._first_attempt_done.wait(5)
        assert attempted == ["proxy-a.example.com", "proxy-b.example.com"]
        assert session._tunnel_port == 9292
        assert session._tunnel_config.proxy_host == "proxy-b.example.com"
    finally:
        session.close()


def test_session_gives_up_only_after_every_proxy(monkeypatch, caplog):
    config = TunnelConfig.from_api_response(_api_response_with_proxies())
    attempted = []

    class _AllDeadTunnel:
        local_port = None

        def __init__(self, key_path: str = ""):
            pass

        def establish(self, cfg):
            attempted.append(cfg.proxy_host)
            return None, "connection refused"

        def is_alive(self):
            return False

        def shutdown(self):
            return None

    monkeypatch.setattr(
        "argus.client.session.resolve_tunnel_config_with_reason", lambda **kwargs: (config, "/fake/key/path", None)
    )
    monkeypatch.setattr("argus.client.session.SSHTunnel", _AllDeadTunnel)

    with caplog.at_level("WARNING"):
        session = TunneledSession(
            auth_token="token", original_base_url="https://argus.scylladb.com", run_id="test-run-id"
        )
        try:
            assert session._first_attempt_done.wait(5)
        finally:
            session.close()

    # Every proxy is tried, then the whole list again after the config refresh
    # that covers a cached config naming a retired proxy.
    assert attempted == ["proxy-a.example.com", "proxy-b.example.com"] * 2
    assert session._tunnel_port is None
    assert "proxy-b.example.com" in caplog.text


def test_session_reports_the_refresh_failure_when_the_retry_resolve_also_fails(monkeypatch, caplog):
    config = TunnelConfig(
        proxy_host="proxy.example.com",
        proxy_port=22,
        proxy_user="argus-proxy",
        target_host="10.0.0.10",
        target_port=8080,
        host_key_fingerprint="SHA256:test",
    )

    class _DeadTunnel:
        local_port = None

        def __init__(self, key_path: str = ""):
            pass

        def establish(self, cfg):
            return None, "connection refused"

        def is_alive(self):
            return False

        def shutdown(self):
            return None

    calls = {"count": 0}

    def _resolve(**kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return config, "/fake/key/path", None
        return None, None, "second resolve failed"

    monkeypatch.setattr("argus.client.session.resolve_tunnel_config_with_reason", _resolve)
    monkeypatch.setattr("argus.client.session.SSHTunnel", _DeadTunnel)

    with caplog.at_level("WARNING"):
        session = TunneledSession(
            auth_token="token", original_base_url="https://argus.scylladb.com", run_id="test-run-id"
        )
        try:
            assert session._first_attempt_done.wait(5)
        finally:
            session.close()

    assert calls["count"] == 2
    assert session._tunnel_port is None
    assert "second resolve failed" in caplog.text


def test_short_lived_session_never_builds_a_tunnel(requests_mock, monkeypatch, tmp_path):
    """A one-shot client must not pay a handshake it cannot earn back.

    Standing a tunnel up costs a registration call plus an authorized-keys
    lookup, both direct. A process that submits once and exits would add public
    traffic instead of removing it.
    """
    monkeypatch.setenv("ARGUS_TUNNEL_MIN_REQUESTS", "10")
    monkeypatch.setenv("ARGUS_TUNNEL_MONITOR_INTERVAL", "0.01")
    requests_mock.get(
        "https://argus.scylladb.com/api/v1/client/testrun/test-type/test-id/get",
        json={"status": "ok", "response": {}},
        status_code=200,
    )
    resolved = {"calls": 0}

    def _resolve(**kwargs):
        resolved["calls"] += 1
        return None, None, "should not be reached"

    monkeypatch.setattr("argus.client.session.resolve_tunnel_config_with_reason", _resolve)

    client = ArgusClient(
        auth_token="token",
        base_url="https://argus.scylladb.com",
        log_dir=tmp_path,
        use_tunnel=True,
        run_id="test-run-id",
    )
    try:
        for _ in range(3):
            client.get(endpoint=ArgusClient.Routes.GET, location_params={"type": "test-type", "id": "test-id"})
        time.sleep(0.1)
        assert resolved["calls"] == 0, "handshake ran for a session that made 3 requests"
        assert client.session._tunnel_port is None
    finally:
        client.session.close()


def test_busy_session_builds_a_tunnel_once_it_crosses_the_threshold(requests_mock, monkeypatch, tmp_path):
    monkeypatch.setenv("ARGUS_TUNNEL_MIN_REQUESTS", "5")
    monkeypatch.setenv("ARGUS_TUNNEL_MONITOR_INTERVAL", "0.01")
    direct = "https://argus.scylladb.com/api/v1/client/testrun/test-type/test-id/get"
    requests_mock.get(direct, json={"status": "ok", "response": {}}, status_code=200)
    requests_mock.get(
        "http://127.0.0.1:9191/api/v1/client/testrun/test-type/test-id/get",
        json={"status": "ok", "response": {}},
        status_code=200,
    )

    config = TunnelConfig.from_api_response(_api_response_with_proxies())
    monkeypatch.setattr(
        "argus.client.session.resolve_tunnel_config_with_reason", lambda **kwargs: (config, "/fake/key/path", None)
    )
    monkeypatch.setattr("argus.client.session.SSHTunnel", _FakeTunnel)

    client = ArgusClient(
        auth_token="token",
        base_url="https://argus.scylladb.com",
        log_dir=tmp_path,
        use_tunnel=True,
        run_id="test-run-id",
    )
    try:
        for _ in range(4):
            client.get(endpoint=ArgusClient.Routes.GET, location_params={"type": "test-type", "id": "test-id"})
        assert client.session._tunnel_port is None, "tunnelled before earning it"

        client.get(endpoint=ArgusClient.Routes.GET, location_params={"type": "test-type", "id": "test-id"})
        assert _wait_until(lambda: client.session._tunnel_port == 9191), "never tunnelled after the threshold"
    finally:
        client.session.close()


def test_crossing_the_threshold_wakes_the_monitor(requests_mock, monkeypatch):
    """The threshold request must not wait a monitor interval to start tunnelling."""
    monkeypatch.setenv("ARGUS_TUNNEL_MIN_REQUESTS", "2")
    url = "https://argus.scylladb.com/ping"
    requests_mock.get(url, json={}, status_code=200)

    session = TunneledSession(auth_token="token", original_base_url="https://argus.scylladb.com", run_id="test-run-id")
    # Stop the monitor first, so nothing clears the event under the assertion.
    session._monitor_stop.set()
    session._wake.set()
    session._monitor_thread.join(timeout=5)
    try:
        session._wake.clear()
        session.get(url)
        assert not session._worth_tunnelling()
        assert not session._wake.is_set()

        session.get(url)
        assert session._worth_tunnelling()
        assert session._wake.is_set()
    finally:
        session.close()


def test_retry_delay_escalates_and_caps(monkeypatch):
    monkeypatch.setenv("ARGUS_TUNNEL_RETRY_MIN_SECONDS", "30")
    monkeypatch.setenv("ARGUS_TUNNEL_RETRY_MAX_SECONDS", "120")
    monkeypatch.setattr("argus.client.session.resolve_tunnel_config_with_reason", lambda **kwargs: (None, None, "down"))

    session = TunneledSession(auth_token="token", original_base_url="https://argus.scylladb.com", run_id="test-run-id")
    try:
        session._retry_delay = 30.0
        delays = []
        for _ in range(5):
            before = time.monotonic()
            session._schedule_retry()
            delays.append(session._next_retry_at - before)

        assert 24.0 <= delays[0] <= 36.0
        assert 48.0 <= delays[1] <= 72.0
        assert 96.0 <= delays[2] <= 144.0
        # Capped from here on, jitter aside.
        assert 96.0 <= delays[3] <= 144.0
        assert 96.0 <= delays[4] <= 144.0
    finally:
        session.close()


def test_request_falls_back_to_direct_without_blocking(requests_mock, monkeypatch, tmp_path):
    direct_url = "https://argus.scylladb.com/api/v1/client/testrun/test-type/test-id/get"
    tunnel_url = "http://127.0.0.1:9191/api/v1/client/testrun/test-type/test-id/get"

    requests_mock.get(tunnel_url, exc=tunnel_api.requests.ConnectionError("tunnel is dead"))
    requests_mock.get(direct_url, json={"status": "ok", "response": {}}, status_code=200)
    monkeypatch.setattr("argus.client.session.resolve_tunnel_config_with_reason", lambda **kwargs: (None, None, "down"))

    client = ArgusClient(
        auth_token="token",
        base_url="https://argus.scylladb.com",
        log_dir=tmp_path,
        use_tunnel=True,
        run_id="test-run-id",
    )
    client.session._tunnel_port = 9191

    response = client.get(
        endpoint=ArgusClient.Routes.GET,
        location_params={"type": "test-type", "id": "test-id"},
    )

    assert response.status_code == 200
    # The request served itself directly and handed recovery to the monitor
    # instead of spawning SSH on the caller's thread.
    assert client.session._tunnel_port is None


def test_request_does_not_mutate_caller_headers(requests_mock, monkeypatch):
    direct_url = "https://argus.scylladb.com/api/v1/client/testrun/test-type/test-id/get"
    tunnel_url = "http://127.0.0.1:9191/api/v1/client/testrun/test-type/test-id/get"
    requests_mock.get(tunnel_url, json={"status": "ok", "response": {}}, status_code=200)
    monkeypatch.setattr("argus.client.session.resolve_tunnel_config_with_reason", lambda **kwargs: (None, None, "down"))

    session = TunneledSession(auth_token="token", original_base_url="https://argus.scylladb.com", run_id="test-run-id")
    try:
        session._tunnel_port = 9191
        caller_headers = {"X-Caller": "keepme"}
        session.get(direct_url, headers=caller_headers)
        assert caller_headers == {"X-Caller": "keepme"}
    finally:
        session.close()


def test_monitor_tears_down_a_suspect_tunnel(fast_tunnel_retry, monkeypatch):
    monkeypatch.setattr("argus.client.session.resolve_tunnel_config_with_reason", lambda **kwargs: (None, None, "down"))

    session = TunneledSession(auth_token="token", original_base_url="https://argus.scylladb.com", run_id="test-run-id")
    try:
        fake = _FakeTunnel()
        session._tunnel = fake
        session._tunnel_port = 9191
        session._report_tunnel_failure()

        assert _wait_until(lambda: fake.shutdown_calls > 0), "monitor never tore the tunnel down"
        assert session._tunnel is None
        assert session._tunnel_port is None
    finally:
        session.close()


class _MortalTunnel:
    """SSHTunnel stand-in whose process can be killed from the test body.

    Every instance takes the next port from ``ports`` and appends itself to
    ``created``, so a test can tell one generation of tunnel from the next.
    """

    ports: list[int] = []
    created: list["_MortalTunnel"] = []

    def __init__(self, key_path: str = ""):
        self.local_port = None
        self.alive = False
        self.shutdown_calls = 0
        type(self).created.append(self)

    def establish(self, cfg):
        self.local_port = type(self).ports.pop(0)
        self.alive = True
        return self.local_port, None

    def is_alive(self):
        return self.alive

    def die(self):
        self.alive = False

    def shutdown(self):
        self.alive = False
        self.local_port = None
        self.shutdown_calls += 1


@pytest.fixture
def mortal_tunnel(monkeypatch):
    monkeypatch.setattr(_MortalTunnel, "ports", [9191, 9292, 9393], raising=False)
    monkeypatch.setattr(_MortalTunnel, "created", [], raising=False)
    monkeypatch.setattr("argus.client.session.SSHTunnel", _MortalTunnel)
    return _MortalTunnel


def test_monitor_reestablishes_the_tunnel_after_the_process_dies(fast_tunnel_retry, mortal_tunnel, monkeypatch):
    """A tunnel that dies mid-session is torn down and replaced by the monitor."""
    config = TunnelConfig(
        proxy_host="proxy.example.com",
        proxy_port=22,
        proxy_user="argus-proxy",
        target_host="10.0.0.10",
        target_port=8080,
        host_key_fingerprint="SHA256:test",
    )
    monkeypatch.setattr(
        "argus.client.session.resolve_tunnel_config_with_reason", lambda **kwargs: (config, "/fake/key/path", None)
    )

    session = TunneledSession(auth_token="token", original_base_url="https://argus.scylladb.com", run_id="test-run-id")
    try:
        assert _wait_until(lambda: session._tunnel_port == 9191), "monitor never built the first tunnel"
        first = mortal_tunnel.created[0]

        first.die()

        assert _wait_until(lambda: session._tunnel_port == 9292), "monitor never rebuilt the tunnel"
        assert first.shutdown_calls > 0, "the dead tunnel was never shut down"
        assert session._tunnel is mortal_tunnel.created[-1]
        assert session._tunnel_suspect is False
    finally:
        session.close()


def test_reconnect_is_immediate_and_does_not_wait_out_the_backoff(mortal_tunnel, monkeypatch):
    """A tunnel that was working earns a fresh ladder, not the escalated delay.

    ``_monitor_tick`` must reset ``_next_retry_at`` after ``_teardown`` has run
    its ``_schedule_retry``. Reset it first and the reconnect waits a full
    retry window instead of happening in the same tick.
    """
    monkeypatch.setenv("ARGUS_TUNNEL_MONITOR_INTERVAL", "0.01")
    monkeypatch.setenv("ARGUS_TUNNEL_RETRY_MIN_SECONDS", "300")
    monkeypatch.setenv("ARGUS_TUNNEL_RETRY_MAX_SECONDS", "600")
    config = TunnelConfig(
        proxy_host="proxy.example.com",
        proxy_port=22,
        proxy_user="argus-proxy",
        target_host="10.0.0.10",
        target_port=8080,
        host_key_fingerprint="SHA256:test",
    )
    monkeypatch.setattr(
        "argus.client.session.resolve_tunnel_config_with_reason", lambda **kwargs: (config, "/fake/key/path", None)
    )

    session = TunneledSession(auth_token="token", original_base_url="https://argus.scylladb.com", run_id="test-run-id")
    try:
        assert _wait_until(lambda: session._tunnel_port == 9191)
        mortal_tunnel.created[0].die()

        assert _wait_until(lambda: session._tunnel_port == 9292, timeout=3.0), (
            "reconnect waited for the 300s backoff instead of retrying at once"
        )
    finally:
        session.close()


def test_request_failure_makes_the_monitor_rebuild_the_tunnel(
    requests_mock, mortal_tunnel, fast_tunnel_retry, monkeypatch
):
    """A ConnectionError on a request thread routes that call direct, then reconnects."""
    direct_url = "https://argus.scylladb.com/api/v1/client/testrun/test-type/test-id/get"
    requests_mock.get(direct_url, json={"status": "ok", "response": {}}, status_code=200)
    requests_mock.get(
        "http://127.0.0.1:9191/api/v1/client/testrun/test-type/test-id/get",
        exc=tunnel_api.requests.ConnectionError("tunnel is dead"),
    )
    requests_mock.get(
        "http://127.0.0.1:9292/api/v1/client/testrun/test-type/test-id/get",
        json={"status": "ok", "response": {"via": "second tunnel"}},
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
    monkeypatch.setattr(
        "argus.client.session.resolve_tunnel_config_with_reason", lambda **kwargs: (config, "/fake/key/path", None)
    )

    session = TunneledSession(auth_token="token", original_base_url="https://argus.scylladb.com", run_id="test-run-id")
    try:
        assert _wait_until(lambda: session._tunnel_port == 9191)
        # The live tunnel object stays healthy, so only the request-thread
        # report can trigger the rebuild.
        response = session.get(direct_url)
        assert response.status_code == 200
        assert response.json()["response"] == {}, "the failed request did not fall back to a direct call"

        assert _wait_until(lambda: session._tunnel_port == 9292), "reported failure never produced a new tunnel"
        assert mortal_tunnel.created[0].shutdown_calls > 0

        response = session.get(direct_url)
        assert response.json()["response"] == {"via": "second tunnel"}, "traffic did not return to the tunnel"
    finally:
        session.close()


def test_tunneled_session_starts_and_stops_monitor_thread():
    session = TunneledSession(auth_token="token", original_base_url="https://argus.scylladb.com", run_id="test-run-id")
    try:
        assert session._monitor_thread.is_alive()
    finally:
        session.close()

    session._monitor_thread.join(timeout=5)
    assert not session._monitor_thread.is_alive()


def test_tunneled_session_close_unregisters_atexit(atexit_hooks):
    session = TunneledSession(auth_token="token", original_base_url="https://argus.scylladb.com", run_id="test-run-id")
    callback = session._atexit_close
    ref = session._atexit_ref
    assert session._atexit_callback in atexit_hooks

    session.close()

    assert session._atexit_callback not in atexit_hooks
    # After close(), invoking the atexit callback must be a no-op (the session
    # was unregistered, and even if called manually it should not blow up).
    callback(ref)


def test_closing_one_session_keeps_the_atexit_hook_of_another(atexit_hooks):
    first = TunneledSession(auth_token="token", original_base_url="https://argus.scylladb.com", run_id="test-run-id")
    second = TunneledSession(auth_token="token", original_base_url="https://argus.scylladb.com", run_id="test-run-id")
    try:
        first.close()
        assert second._atexit_callback in atexit_hooks, "close() dropped another session's exit hook"
    finally:
        second.close()


def test_monitor_sleeps_the_full_interval_until_the_session_earns_a_tunnel(monkeypatch):
    """Below the request threshold the monitor has nothing to do.

    ``_next_retry_at`` stays at 0, so a retry-driven wait would collapse to the
    0.1s floor and wake the thread ten times a second for the whole process.
    """
    monkeypatch.setenv("ARGUS_TUNNEL_MIN_REQUESTS", "10")

    session = TunneledSession(auth_token="token", original_base_url="https://argus.scylladb.com", run_id="test-run-id")
    # Stop the monitor first, so no tick moves _next_retry_at under the assertions.
    session._monitor_stop.set()
    session._wake.set()
    session._monitor_thread.join(timeout=5)
    try:
        assert session._next_retry_at == 0.0
        assert session._next_wait(5.0) == 5.0

        session._request_count = 10
        assert session._next_wait(5.0) == pytest.approx(0.1)
    finally:
        session.close()


def _prime_tunnel_state(session):
    """Force a session into the 'tunnel active' state so _tunnel_headers() emits."""
    from types import SimpleNamespace

    session._tunnel_port = 12345
    session._tunnel_established_at = "2026-06-16T00:00:00+00:00"
    session._tunnel_config = SimpleNamespace(proxy_host="proxy.example.com", key_id="key-uuid")


def test_tunnel_headers_compose_job_name_and_build_number(monkeypatch):
    monkeypatch.setenv("JOB_NAME", "scylla-master/longevity/longevity-100gb")
    monkeypatch.setenv("BUILD_NUMBER", "42")
    monkeypatch.setenv("BUILD_URL", "https://jenkins.scylladb.com/job/scylla-master/job/longevity/42/")
    session = TunneledSession(auth_token="token", original_base_url="https://argus.scylladb.com", run_id="test-run-id")
    try:
        _prime_tunnel_state(session)
        headers = session._tunnel_headers()
        assert headers["X-Argus-Build-Id"] == "scylla-master/longevity/longevity-100gb#42"
        assert headers["X-Argus-Build-Url"] == "https://jenkins.scylladb.com/job/scylla-master/job/longevity/42/"
        assert headers["X-SSH-Tunnel-Origin"] == "proxy.example.com"
    finally:
        session.close()


def test_tunnel_headers_build_id_job_name_without_build_number(monkeypatch):
    monkeypatch.delenv("BUILD_NUMBER", raising=False)
    monkeypatch.setenv("JOB_NAME", "jenkins-job-name")
    session = TunneledSession(auth_token="token", original_base_url="https://argus.scylladb.com", run_id="test-run-id")
    try:
        _prime_tunnel_state(session)
        assert session._tunnel_headers()["X-Argus-Build-Id"] == "jenkins-job-name"
    finally:
        session.close()


def test_tunnel_headers_reject_overlong_build_id(monkeypatch):
    monkeypatch.setenv("JOB_NAME", "a" * 300)
    monkeypatch.delenv("BUILD_NUMBER", raising=False)
    session = TunneledSession(auth_token="token", original_base_url="https://argus.scylladb.com", run_id="test-run-id")
    try:
        _prime_tunnel_state(session)
        # Rejected rather than truncated — header omitted entirely.
        assert "X-Argus-Build-Id" not in session._tunnel_headers()
    finally:
        session.close()


def test_tunnel_headers_omit_build_id_and_url_when_unset(monkeypatch):
    for var in ("JOB_NAME", "BUILD_NUMBER", "BUILD_URL"):
        monkeypatch.delenv(var, raising=False)
    session = TunneledSession(auth_token="token", original_base_url="https://argus.scylladb.com", run_id="test-run-id")
    try:
        _prime_tunnel_state(session)
        headers = session._tunnel_headers()
        assert "X-Argus-Build-Id" not in headers
        assert "X-Argus-Build-Url" not in headers
    finally:
        session.close()


def test_argus_client_works_as_context_manager(requests_mock, monkeypatch, tmp_path):
    requests_mock.get(
        "https://argus.scylladb.com/api/v1/client/testrun/test-type/test-id/get",
        json={"status": "ok", "response": {}},
        status_code=200,
    )
    monkeypatch.setattr(
        "argus.client.session.resolve_tunnel_config_with_reason",
        lambda **kwargs: (None, None, "api unreachable"),
    )

    with ArgusClient(
        auth_token="token",
        base_url="https://argus.scylladb.com",
        log_dir=tmp_path,
        use_tunnel=True,
        run_id="test-run-id",
    ) as client:
        client.get(endpoint=ArgusClient.Routes.GET, location_params={"type": "test-type", "id": "test-id"})
        session = client.session
        assert session._monitor_thread.is_alive()

    session._monitor_thread.join(timeout=5)
    assert not session._monitor_thread.is_alive()


def test_backoff_does_not_wipe_cached_tunnel_state(tunnel_state_dir, monkeypatch):
    future = datetime.now(tz=timezone.utc) + timedelta(hours=6)
    key_dir = os.path.join(tunnel_state.tunneling_root(), tunnel_state._dirname_for("test-run-id", future))
    _write_key_dir(key_dir)

    monkeypatch.setattr(
        "argus.client.session.resolve_tunnel_config_with_reason",
        lambda **kwargs: (None, None, "transient failure"),
    )

    session = TunneledSession(auth_token="token", original_base_url="https://argus.scylladb.com", run_id="test-run-id")
    try:
        assert session._first_attempt_done.wait(5)
        assert os.path.exists(key_dir)
    finally:
        session.close()


def test_sshd_key_rejection_wipes_cached_tunnel_state(tunnel_state_dir, monkeypatch):
    future = datetime.now(tz=timezone.utc) + timedelta(hours=6)
    key_dir = os.path.join(tunnel_state.tunneling_root(), tunnel_state._dirname_for("test-run-id", future))
    _write_key_dir(key_dir)

    config = TunnelConfig(
        proxy_host="proxy.example.com",
        proxy_port=22,
        proxy_user="argus-proxy",
        target_host="10.0.0.10",
        target_port=8080,
        host_key_fingerprint="SHA256:test",
    )

    class _KeyRejectedTunnel:
        local_port = None
        sshd_rejected_key = True

        def __init__(self, key_path: str = ""):
            pass

        def establish(self, cfg):
            return None, "Permission denied (publickey)."

        def is_alive(self):
            return False

        def shutdown(self):
            return None

    monkeypatch.setattr(
        "argus.client.session.resolve_tunnel_config_with_reason",
        lambda **kwargs: (config, os.path.join(key_dir, "key"), None),
    )
    monkeypatch.setattr("argus.client.session.SSHTunnel", _KeyRejectedTunnel)

    session = TunneledSession(auth_token="token", original_base_url="https://argus.scylladb.com", run_id="test-run-id")
    try:
        assert session._first_attempt_done.wait(5)
        assert not os.path.exists(key_dir)
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


@pytest.mark.parametrize(
    "env, expected",
    [
        (
            {
                "JOB_NAME": "scylla-master/byo/byo_build_tests_dtest",
                "BUILD_NUMBER": "42",
                "BUILD_URL": "https://jenkins.example.com/job/x/42/",
            },
            {
                "X-Argus-Build-Id": "scylla-master/byo/byo_build_tests_dtest#42",
                "X-Argus-Build-Url": "https://jenkins.example.com/job/x/42/",
            },
        ),
        # A job without a build number still names itself.
        ({"JOB_NAME": "manual-job"}, {"X-Argus-Build-Id": "manual-job"}),
        # Outside CI there is nothing to attribute.
        ({}, {}),
    ],
)
def test_build_attribution_headers(monkeypatch, env, expected):
    for key in ("JOB_NAME", "BUILD_NUMBER", "BUILD_URL"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    headers = session_mod.build_attribution_headers()

    assert headers.pop("X-Argus-Client-Version") == session_mod._resolve_client_version()
    assert headers == expected


def test_build_attribution_headers_drops_oversized_build_id(monkeypatch):
    monkeypatch.setenv("JOB_NAME", "x" * (session_mod._MAX_BUILD_ID_LEN + 1))
    monkeypatch.delenv("BUILD_NUMBER", raising=False)
    monkeypatch.delenv("BUILD_URL", raising=False)

    assert set(session_mod.build_attribution_headers()) == {"X-Argus-Client-Version"}


def test_direct_session_carries_build_attribution(monkeypatch):
    """The point of the change: a job that never tunnels is still named."""
    monkeypatch.delenv("ARGUS_USE_TUNNEL", raising=False)
    monkeypatch.setenv("JOB_NAME", "scylla-master/longevity")
    monkeypatch.setenv("BUILD_NUMBER", "7")
    monkeypatch.delenv("BUILD_URL", raising=False)

    session = session_mod.create_session(auth_token="token", base_url="https://argus.example.com", use_tunnel=False)

    assert not isinstance(session, TunneledSession)
    assert session.headers["X-Argus-Build-Id"] == "scylla-master/longevity#7"


def test_tunneled_session_carries_build_attribution_for_fallback(monkeypatch):
    """A TunneledSession that never establishes still attributes its direct requests."""
    monkeypatch.setenv("JOB_NAME", "scylla-master/longevity")
    monkeypatch.setenv("BUILD_NUMBER", "7")

    session = session_mod.create_session(
        auth_token="token", base_url="https://argus.example.com", use_tunnel=True, run_id="test-run-id"
    )
    try:
        assert isinstance(session, TunneledSession)
        assert session.headers["X-Argus-Build-Id"] == "scylla-master/longevity#7"
    finally:
        session.close()


def test_every_session_reports_its_client_version(monkeypatch):
    """The label that separates "cannot tunnel" from "tunnel is failing"."""
    monkeypatch.delenv("ARGUS_USE_TUNNEL", raising=False)
    monkeypatch.delenv("JOB_NAME", raising=False)

    session = session_mod.create_session(auth_token="token", base_url="https://argus.example.com", use_tunnel=False)

    assert session.headers["X-Argus-Client-Version"] == session_mod._resolve_client_version()


def test_client_version_is_unknown_when_the_package_is_not_installed(monkeypatch):
    def _raise(_name):
        raise session_mod.metadata.PackageNotFoundError("argus-alm")

    monkeypatch.setattr(session_mod.metadata, "version", _raise)

    assert session_mod._resolve_client_version() == "unknown"
