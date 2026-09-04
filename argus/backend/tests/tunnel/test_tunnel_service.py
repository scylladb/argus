"""
Tests for TunnelService — require a running ScyllaDB container.

Run with:
    uv run pytest argus/backend/tests/tunnel/test_tunnel_service.py -m docker_required -v
"""
import base64
import hashlib
import pytest
from pytest import MonkeyPatch
from datetime import UTC, datetime
from secrets import token_hex
from uuid import uuid4

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from coodie.exceptions import DocumentNotFound

from argus.backend.models.ssh_key import ProxyTunnelConfig, SSHTunnelKey
from argus.backend.models.web import User, UserRoles
from argus.backend.service.tunnel_service import TunnelService, TunnelServiceException, _derive_fingerprint
from argus.backend.service.user import hash_api_token


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_public_key() -> str:
    """Generate a fresh ed25519 public key in OpenSSH format."""
    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key()
    return pub.public_bytes(Encoding.OpenSSH, PublicFormat.OpenSSH).decode("utf-8")


def _make_user() -> User:
    """Create and persist a transient Argus user for testing."""
    return User.create(
        id=uuid4(),
        username=f"tunnel_test_{uuid4().hex[:8]}",
        full_name="Tunnel Test User",
        password="",
        email=f"tunnel_test_{uuid4().hex[:8]}@test.internal",
        registration_date=datetime.now(tz=UTC),
        roles=[UserRoles.User.value],
        token=hash_api_token(token_hex(32)),
        service_user=False,
    )


def _make_active_config(**overrides) -> ProxyTunnelConfig:
    """Create and persist a ProxyTunnelConfig with is_active=True."""
    defaults = dict(
        id=uuid4(),
        host=f"proxy-{uuid4().hex[:6]}.example.com",
        port=22,
        proxy_user="argus-proxy",
        target_host="10.0.0.1",
        target_port=8080,
        host_key_fingerprint="testhost ssh-ed25519 AAAAtestfingerprint",
        service_user_id=uuid4(),
        is_active=True,
    )
    defaults.update(overrides)
    return ProxyTunnelConfig.create(**defaults)


def _active_config_ids() -> list:
    return [cfg.id for cfg in ProxyTunnelConfig.find().all() if cfg.is_active]


def _deactivate_configs(config_ids: list) -> None:
    for cfg_id in config_ids:
        try:
            ProxyTunnelConfig.get(id=cfg_id).update(is_active=False)
        except Exception:
            pass


def _restore_configs(config_ids: list) -> None:
    for cfg_id in config_ids:
        try:
            ProxyTunnelConfig.get(id=cfg_id).update(is_active=True)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tunnel_user(argus_db) -> User:
    user = _make_user()
    yield user
    try:
        user.delete()
    except Exception:
        pass


@pytest.fixture
def active_config(argus_db) -> ProxyTunnelConfig:
    previous_active_ids = _active_config_ids()
    _deactivate_configs(previous_active_ids)

    config = _make_active_config()
    yield config
    try:
        config.delete()
    except Exception:
        pass

    _restore_configs(previous_active_ids)


@pytest.fixture
def mock_host_fingerprint():
    monkeypatch = MonkeyPatch()
    monkeypatch.setattr(
        TunnelService,
        "_fetch_host_key",
        staticmethod(lambda host, _port: (f"{host} ssh-ed25519 AAAA{host}", f"SHA256:{host}")),
    )
    yield
    monkeypatch.undo()


# ---------------------------------------------------------------------------
# TunnelService.register_tunnel
# ---------------------------------------------------------------------------

@pytest.mark.docker_required
def test_register_tunnel_stores_key(argus_db, tunnel_user, active_config):
    """register_tunnel should persist an SSHTunnelKey row in the DB."""
    pub_key = _make_public_key()
    svc = TunnelService()

    result = svc.register_tunnel(user=tunnel_user, public_key=pub_key)

    assert result.proxy_host == active_config.host
    assert result.proxy_port == active_config.port
    assert result.proxy_user == active_config.proxy_user
    assert result.target_host == active_config.target_host
    assert result.target_port == active_config.target_port
    assert result.host_key_fingerprint == active_config.host_key_fingerprint
    assert isinstance(result.expires_at, datetime)
    assert result.key_id is not None
    assert result.tunnel_id is not None

    # Verify the DB row exists
    key = SSHTunnelKey.get(id=result.key_id)
    assert str(key.user_id) == str(tunnel_user.id)
    assert str(key.tunnel_id) == str(active_config.id)
    assert key.public_key == pub_key.strip()
    assert key.fingerprint.startswith("SHA256:")


@pytest.mark.docker_required
def test_register_tunnel_custom_ttl(argus_db, tunnel_user, active_config):
    """A custom ttl_seconds should be reflected in the expires_at timestamp."""
    from datetime import datetime, timezone
    pub_key = _make_public_key()
    svc = TunnelService()
    ttl = 172800  # 2 days

    before = datetime.now(tz=timezone.utc)
    result = svc.register_tunnel(user=tunnel_user, public_key=pub_key, ttl_seconds=ttl)
    after = datetime.now(tz=timezone.utc)

    expires_at = result.expires_at.replace(tzinfo=timezone.utc)
    # expires_at should be approximately now + 1 hour (allow ±5 s for test timing)
    assert (before.timestamp() + ttl - 5) <= expires_at.timestamp() <= (after.timestamp() + ttl + 5)


@pytest.mark.docker_required
def test_register_tunnel_invalid_ttl_raises(argus_db, tunnel_user, active_config):
    """TTL outside [1h, 30d] or non-integer ttl_seconds should raise TunnelServiceException."""
    svc = TunnelService()

    for ttl in (0, -1, 3599, 2592001, "abc", "0"):
        with pytest.raises(TunnelServiceException, match="ttl_seconds must be between 3600 and 2592000 seconds"):
            svc.register_tunnel(user=tunnel_user, public_key=_make_public_key(), ttl_seconds=ttl)


@pytest.mark.docker_required
def test_register_tunnel_ttl_upper_bound_allowed(argus_db, tunnel_user, active_config):
    """A TTL of exactly 30 days should be accepted."""
    from datetime import datetime, timezone

    ttl = 2592000
    svc = TunnelService()
    before = datetime.now(tz=timezone.utc)
    result = svc.register_tunnel(user=tunnel_user, public_key=_make_public_key(), ttl_seconds=ttl)
    after = datetime.now(tz=timezone.utc)

    expires_at = result.expires_at.replace(tzinfo=timezone.utc)
    assert (before.timestamp() + ttl - 5) <= expires_at.timestamp() <= (after.timestamp() + ttl + 5)


@pytest.mark.docker_required
def test_register_tunnel_no_active_config_raises(argus_db, tunnel_user):
    """register_tunnel should raise TunnelServiceException when no active config exists."""
    previous_active_ids = _active_config_ids()
    _deactivate_configs(previous_active_ids)

    try:
        svc = TunnelService()
        with pytest.raises(TunnelServiceException, match="No active proxy tunnel"):
            svc.register_tunnel(user=tunnel_user, public_key=_make_public_key())
    finally:
        _restore_configs(previous_active_ids)


@pytest.mark.docker_required
def test_register_tunnel_invalid_public_key(argus_db, tunnel_user, active_config):
    """Submitting garbage as a public key should raise TunnelServiceException."""
    svc = TunnelService()
    with pytest.raises(TunnelServiceException, match="Invalid SSH public key"):
        svc.register_tunnel(user=tunnel_user, public_key="this-is-not-a-valid-key")


@pytest.mark.docker_required
def test_register_tunnel_missing_public_key(argus_db, tunnel_user, active_config):
    """Missing public_key should raise TunnelServiceException."""
    svc = TunnelService()
    with pytest.raises(TunnelServiceException, match="public_key is required"):
        svc.register_tunnel(user=tunnel_user, public_key="")


# ---------------------------------------------------------------------------
# TunnelService.get_authorized_keys
# ---------------------------------------------------------------------------

@pytest.mark.docker_required
def test_get_authorized_keys_format(argus_db, tunnel_user, active_config):
    """Each line of get_authorized_keys output should be a valid OpenSSH key."""
    pub_key = _make_public_key()
    svc = TunnelService()
    svc.register_tunnel(user=tunnel_user, public_key=pub_key)

    keys_text = svc.get_authorized_keys()
    lines = [ln for ln in keys_text.splitlines() if ln.strip()]
    assert any(pub_key.strip() in ln for ln in lines), "Registered key not found in authorized_keys output"
    for line in lines:
        # Each line must start with a key type
        assert line.startswith(("ssh-", "ecdsa-", "sk-")), f"Unexpected line format: {line!r}"


@pytest.mark.docker_required
def test_get_authorized_keys_includes_keys_from_multiple_tunnels(argus_db, tunnel_user, active_config):
    """authorized_keys should contain all keys across active tunnel hosts."""
    second = _make_active_config(is_active=True)
    try:
        key_a = _make_public_key()
        key_b = _make_public_key()

        now_utc = datetime.now(tz=UTC).replace(tzinfo=None)
        SSHTunnelKey.find().ttl(86400).create(
            id=uuid4(),
            user_id=tunnel_user.id,
            tunnel_id=active_config.id,
            public_key=key_a,
            fingerprint="SHA256:test-a",
            created_at=now_utc,
            expires_at=now_utc,
        )
        SSHTunnelKey.find().ttl(86400).create(
            id=uuid4(),
            user_id=tunnel_user.id,
            tunnel_id=second.id,
            public_key=key_b,
            fingerprint="SHA256:test-b",
            created_at=now_utc,
            expires_at=now_utc,
        )

        keys_text = TunnelService().get_authorized_keys()
        assert key_a.strip() in keys_text
        assert key_b.strip() in keys_text
    finally:
        try:
            second.delete()
        except Exception:
            pass


@pytest.mark.docker_required
def test_get_authorized_keys_by_fingerprint_returns_only_that_key(argus_db, tunnel_user, active_config):
    """A fingerprint scopes the response to the single matching key."""
    wanted = _make_public_key()
    other = _make_public_key()
    svc = TunnelService()
    svc.register_tunnel(user=tunnel_user, public_key=wanted)
    svc.register_tunnel(user=tunnel_user, public_key=other)

    keys_text = svc.get_authorized_keys(fingerprint=_derive_fingerprint(wanted))

    lines = [ln for ln in keys_text.splitlines() if ln.strip()]
    assert len(lines) == 1
    assert wanted.strip() in lines[0]
    assert other.strip() not in keys_text


@pytest.mark.docker_required
def test_get_authorized_keys_by_unknown_fingerprint_is_empty(argus_db, tunnel_user, active_config):
    """An unregistered fingerprint yields an empty body, which sshd reads as a denial."""
    svc = TunnelService()
    svc.register_tunnel(user=tunnel_user, public_key=_make_public_key())

    unknown = _derive_fingerprint(_make_public_key())
    assert svc.get_authorized_keys(fingerprint=unknown) == ""


@pytest.mark.docker_required
def test_a_key_authenticates_on_the_attempt_that_follows_registration(argus_db, tunnel_user, active_config):
    """A registered key is readable through the fingerprint view.

    ScyllaDB applies the view update on the base replica, so a single-node test
    cluster answers the first authentication attempt.
    """
    public_key = _make_public_key()
    svc = TunnelService()
    svc.register_tunnel(user=tunnel_user, public_key=public_key)

    keys_text = svc.get_authorized_keys(fingerprint=_derive_fingerprint(public_key))

    assert public_key.strip() in keys_text


@pytest.mark.docker_required
def test_registering_the_same_key_again_reuses_the_row(argus_db, tunnel_user, active_config):
    """A repeat registration returns the existing key id and does not duplicate it."""
    public_key = _make_public_key()
    svc = TunnelService()
    result = svc.register_tunnel(user=tunnel_user, public_key=public_key)
    fingerprint = _derive_fingerprint(public_key)

    again = svc.register_tunnel(user=tunnel_user, public_key=public_key)

    assert again.key_id == result.key_id
    rows = [row for row in SSHTunnelKey.find(user_id=tunnel_user.id) if row.fingerprint == fingerprint]
    assert len(rows) == 1
    assert public_key.strip() in svc.get_authorized_keys(fingerprint=fingerprint)


class _FakeConfig:
    """Only ``id`` matters to proxy ordering, so a stub keeps this test DB-free."""

    def __init__(self, name: str):
        self.id = name


def _order(user_id, names: list[str]) -> list[str]:
    svc = TunnelService()
    configs = [_FakeConfig(name) for name in names]
    svc._get_active_configs = lambda: list(configs)
    return [cfg.id for cfg in svc._ordered_active_configs(user_id)]


def test_proxy_order_is_stable_for_a_user():
    user = uuid4()
    assert _order(user, ["a", "b", "c"]) == _order(user, ["c", "b", "a"])


def test_proxy_order_spreads_users_and_lists_every_proxy():
    names = ["a", "b", "c"]
    primaries = {_order(uuid4(), names)[0] for _ in range(200)}
    assert primaries == set(names)
    assert sorted(_order(uuid4(), names)) == sorted(names)


def test_adding_a_proxy_reassigns_only_its_own_share():
    """Rendezvous hashing keeps churn near 1/N. Rotating by ``hash % len`` moves everyone."""
    users = [uuid4() for _ in range(2000)]
    before = {u: _order(u, ["a", "b"])[0] for u in users}
    after = {u: _order(u, ["a", "b", "c"])[0] for u in users}

    moved = sum(1 for u in users if before[u] != after[u])
    assert 0.25 < moved / len(users) < 0.45


def test_no_active_proxies_raises():
    with pytest.raises(TunnelServiceException, match="No active proxy tunnel configuration"):
        _order(uuid4(), [])


@pytest.mark.parametrize("bad", [
    "",
    "not-a-fingerprint",
    "MD5:aa:bb:cc",
    "SHA256:",
    "SHA256:tooshort",
    "SHA256:" + "A" * 44,
    "SHA256:" + "!" * 43,
])
def test_get_authorized_keys_rejects_malformed_fingerprint(bad):
    """A malformed fingerprint is rejected before it reaches the database."""
    with pytest.raises(TunnelServiceException):
        TunnelService().get_authorized_keys(fingerprint=bad)


@pytest.mark.docker_required
def test_derive_fingerprint_matches_openssh_wire_blob(argus_db):
    """Fingerprint derivation should match SHA256 of OpenSSH wire blob (ssh-keygen format)."""
    public_key = _make_public_key()
    key_blob = base64.b64decode(public_key.split()[1])
    expected = f"SHA256:{base64.b64encode(hashlib.sha256(key_blob).digest()).rstrip(b'=').decode('ascii')}"
    assert _derive_fingerprint(public_key) == expected


# ---------------------------------------------------------------------------
# TunnelService.delete_key
# ---------------------------------------------------------------------------

@pytest.mark.docker_required
def test_delete_key_removes_row(argus_db, tunnel_user, active_config):
    """delete_key should remove the SSHTunnelKey row from the DB."""
    pub_key = _make_public_key()
    svc = TunnelService()
    result = svc.register_tunnel(user=tunnel_user, public_key=pub_key)
    key_id = result.key_id

    svc.delete_key(key_id)

    with pytest.raises(DocumentNotFound):
        SSHTunnelKey.get(id=key_id)


@pytest.mark.docker_required
def test_deleted_key_stops_authenticating(argus_db, tunnel_user, active_config):
    """A revoked key must not survive in the fingerprint view."""
    pub_key = _make_public_key()
    svc = TunnelService()
    result = svc.register_tunnel(user=tunnel_user, public_key=pub_key)
    fingerprint = _derive_fingerprint(pub_key)
    assert pub_key.strip() in svc.get_authorized_keys(fingerprint=fingerprint)

    svc.delete_key(result.key_id)

    assert svc.get_authorized_keys(fingerprint=fingerprint) == ""


@pytest.mark.docker_required
def test_delete_key_nonexistent_is_noop(argus_db):
    """delete_key for an unknown id should not raise (already TTL-expired is valid)."""
    svc = TunnelService()
    svc.delete_key(uuid4())


# ---------------------------------------------------------------------------
# TunnelService.save_proxy_tunnel_config
# ---------------------------------------------------------------------------

@pytest.mark.docker_required
def test_save_proxy_tunnel_config_creates_service_user(argus_db, mock_host_fingerprint):
    """save_proxy_tunnel_config should create a dedicated service user."""
    previous_active_ids = _active_config_ids()
    _deactivate_configs(previous_active_ids)

    try:
        host = f"proxy-svcuser-{uuid4().hex[:6]}.example.com"
        payload = dict(
            host=host,
            port=22,
            proxy_user="argus-proxy",
            target_host="10.0.1.1",
            target_port=8080,
            host_key_fingerprint=f"SHA256:{host}",
        )
        svc = TunnelService()
        result = svc.save_proxy_tunnel_config(payload)

        assert result.is_active is True
        assert result.service_user_id is not None
        assert result.api_token

        service_user = User.get(id=result.service_user_id)
        assert service_user.token == hash_api_token(result.api_token)
        assert service_user.service_user is True
        assert f"proxy-tunnel-{host}" in service_user.username
        assert service_user.roles == [UserRoles.SSHTunnelServer.value]
    finally:
        _restore_configs(previous_active_ids)


@pytest.mark.docker_required
def test_save_proxy_tunnel_config_reuses_existing_tunnel_service_user(argus_db, mock_host_fingerprint):
    """Saving config for the same host should re-use the existing tunnel service user."""
    previous_active_ids = _active_config_ids()
    _deactivate_configs(previous_active_ids)
    host = f"proxy-reuse-{uuid4().hex[:6]}.example.com"
    payload = dict(
        host=host,
        port=22,
        proxy_user="argus-proxy",
        target_host="10.0.1.1",
        target_port=8080,
        host_key_fingerprint=f"SHA256:{host}",
    )

    try:
        svc = TunnelService()
        first = svc.save_proxy_tunnel_config(payload)
        second = svc.save_proxy_tunnel_config(payload)

        assert first.service_user_id == second.service_user_id
        assert second.api_token == ""
        assert User.get(id=second.service_user_id).token == hash_api_token(first.api_token)
    finally:
        _restore_configs(previous_active_ids)


@pytest.mark.docker_required
def test_save_proxy_tunnel_config_deactivates_old(argus_db, mock_host_fingerprint):
    """Creating a new config should not force-deactivate prior active configs."""
    previous_active_ids = _active_config_ids()
    _deactivate_configs(previous_active_ids)

    try:
        first_payload = dict(
            host=f"proxy-first-{uuid4().hex[:6]}.example.com",
            port=22,
            proxy_user="argus-proxy",
            target_host="10.0.2.1",
            target_port=8080,
        )
        svc = TunnelService()
        first_payload["host_key_fingerprint"] = f"SHA256:{first_payload['host']}"
        first = svc.save_proxy_tunnel_config(first_payload)
        assert first.is_active is True

        second_payload = dict(
            host=f"proxy-second-{uuid4().hex[:6]}.example.com",
            port=22,
            proxy_user="argus-proxy",
            target_host="10.0.2.2",
            target_port=8080,
        )
        second_payload["host_key_fingerprint"] = f"SHA256:{second_payload['host']}"
        second = svc.save_proxy_tunnel_config(second_payload)
        assert second.is_active is True

        refreshed_first = ProxyTunnelConfig.get(id=first.id)
        assert refreshed_first.is_active is True
    finally:
        _restore_configs(previous_active_ids)


@pytest.mark.docker_required
def test_save_proxy_tunnel_config_can_create_inactive(argus_db, mock_host_fingerprint):
    """save_proxy_tunnel_config should accept is_active=False for disabled hosts."""
    host = f"proxy-inactive-{uuid4().hex[:6]}.example.com"
    payload = dict(
        host=host,
        port=22,
        proxy_user="argus-proxy",
        target_host="10.0.3.1",
        target_port=8080,
        host_key_fingerprint=f"SHA256:{host}",
        is_active=False,
    )

    svc = TunnelService()
    result = svc.save_proxy_tunnel_config(payload)
    assert result.is_active is False


@pytest.mark.docker_required
def test_list_proxy_tunnel_configs_filters_active(argus_db):
    """list_proxy_tunnel_configs should support active_only filtering."""
    active_cfg = _make_active_config(is_active=True)
    inactive_cfg = _make_active_config(is_active=False)
    try:
        svc = TunnelService()
        active_rows = svc.list_proxy_tunnel_configs(active_only=True)
        inactive_rows = svc.list_proxy_tunnel_configs(active_only=False)

        active_ids = {str(row.id) for row in active_rows}
        inactive_ids = {str(row.id) for row in inactive_rows}
        assert str(active_cfg.id) in active_ids
        assert str(inactive_cfg.id) in inactive_ids
    finally:
        try:
            active_cfg.delete()
        except Exception:
            pass
        try:
            inactive_cfg.delete()
        except Exception:
            pass


@pytest.mark.docker_required
def test_set_proxy_tunnel_config_active_toggles_state(argus_db):
    """set_proxy_tunnel_config_active should toggle single config state."""
    cfg = _make_active_config(is_active=False)
    try:
        svc = TunnelService()
        enabled = svc.set_proxy_tunnel_config_active(cfg.id, True)
        assert enabled.is_active is True

        disabled = svc.set_proxy_tunnel_config_active(cfg.id, False)
        assert disabled.is_active is False
    finally:
        try:
            cfg.delete()
        except Exception:
            pass


@pytest.mark.docker_required
def test_save_proxy_tunnel_config_missing_fields(argus_db, mock_host_fingerprint):
    """save_proxy_tunnel_config should raise when required fields are absent."""
    svc = TunnelService()
    with pytest.raises(TunnelServiceException, match="Missing required fields"):
        svc.save_proxy_tunnel_config({"host": "proxy.example.com"})



@pytest.mark.docker_required
def test_create_proxy_service_user_rejects_username_collision(argus_db):
    host = f"proxy-collision-{uuid4().hex[:6]}.example.com"
    username = f"proxy-tunnel-{host}"
    now_utc = datetime.now(tz=UTC).replace(tzinfo=None)
    collision_user = User.create(
        id=uuid4(),
        username=username,
        full_name="Conflicting User",
        password="",
        email=f"{username}@example.com",
        registration_date=now_utc,
        roles=[UserRoles.User.value],
        service_user=False,
    )

    try:
        with pytest.raises(TunnelServiceException, match="already exists and is not a dedicated SSH tunnel service user"):
            TunnelService()._create_proxy_service_user(host)
    finally:
        try:
            collision_user.delete()
        except Exception:
            pass


@pytest.mark.docker_required
def test_fetch_host_key_prefers_ed25519(argus_db):
    svc = TunnelService()
    ed25519_pub = _make_public_key()

    class _Result:
        def __init__(self):
            self.stdout = (
                "example.com ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQC7fY7Y1hQ7jLlY9gZmve6n9YjKTRv9QTHd8xh9Mo6mMma7mXFF7n6yFB6gki8k4d9eQWIRtwywR6fRa3fVYvULr3zP1mpIhA2bc6ctXb9x7Xj7J2Ff8V0s8m2q9f5P6m3trcTQj1qk0Eo2FtfYV3xJkYyWm3q2bN4YfQYyp7Y6dQz8fXw91n6mQmA6W6M3uVlbM8qqQvY8jN8cQpD6k9lQGmQ1ZlW9d6kqv6dQd7w9cH8q5rR9k1M6t8eN7gQW8qD9r1m2b4u6p8s0t2v4w6x8y0z2A4C6E8G0I2K4M6O8Q0S2U4W6Y8a0c2e4g6i8k0m2o4q6s8u0w2y4\n"
                f"example.com {ed25519_pub}\n"
            )
            self.stderr = ""

    import argus.backend.service.tunnel_service as tunnel_module

    original_run = tunnel_module.subprocess.run
    tunnel_module.subprocess.run = lambda *args, **kwargs: _Result()
    try:
        known_hosts_entry, fingerprint = svc._fetch_host_key("example.com", 22)
    finally:
        tunnel_module.subprocess.run = original_run

    expected_fp = _derive_fingerprint(ed25519_pub)
    assert fingerprint == expected_fp
    assert "example.com" in known_hosts_entry
    assert "ssh-ed25519" in known_hosts_entry


@pytest.mark.docker_required
def test_fetch_host_key_raises_when_empty(argus_db):
    svc = TunnelService()

    class _Result:
        def __init__(self):
            self.stdout = ""
            self.stderr = "connection refused"

    import argus.backend.service.tunnel_service as tunnel_module

    original_run = tunnel_module.subprocess.run
    tunnel_module.subprocess.run = lambda *args, **kwargs: _Result()
    try:
        with pytest.raises(TunnelServiceException, match="Failed to fetch host key"):
            svc._fetch_host_key("bad.example.com", 22)
    finally:
        tunnel_module.subprocess.run = original_run


# ---------------------------------------------------------------------------
# TunnelService.get_proxy_tunnel_config
# ---------------------------------------------------------------------------

@pytest.mark.docker_required
def test_get_proxy_tunnel_config_returns_active(argus_db):
    """get_proxy_tunnel_config should return the currently active config."""
    previous_active_ids = _active_config_ids()
    _deactivate_configs(previous_active_ids)

    config = _make_active_config()
    try:
        svc = TunnelService()
        result = svc.get_proxy_tunnel_config()
        assert result is not None
        assert str(result.id) == str(config.id)
        assert result.is_active is True
    finally:
        try:
            config.delete()
        except Exception:
            pass
        _restore_configs(previous_active_ids)


@pytest.mark.docker_required
def test_get_proxy_tunnel_config_none_when_no_active(argus_db):
    """get_proxy_tunnel_config should return None when no active config exists."""
    previous_active_ids = _active_config_ids()
    _deactivate_configs(previous_active_ids)
    try:
        svc = TunnelService()
        assert svc.get_proxy_tunnel_config() is None
    finally:
        _restore_configs(previous_active_ids)


@pytest.mark.docker_required
def test_get_proxy_tunnel_config_returns_none_for_inactive_tunnel_id(argus_db):
    """get_proxy_tunnel_config(tunnel_id=...) should ignore inactive configs."""
    cfg = _make_active_config(is_active=False)
    try:
        assert TunnelService().get_proxy_tunnel_config(tunnel_id=cfg.id) is None
    finally:
        try:
            cfg.delete()
        except Exception:
            pass


@pytest.mark.docker_required
def test_get_proxy_tunnel_config_is_deterministic(argus_db):
    """get_proxy_tunnel_config() should be deterministic for admin reads."""
    first = _make_active_config(is_active=True)
    second = _make_active_config(is_active=True)
    try:
        svc = TunnelService()
        pick1 = svc.get_proxy_tunnel_config()
        pick2 = svc.get_proxy_tunnel_config()
        assert pick1 is not None
        assert pick2 is not None
        assert pick1.host == pick2.host
    finally:
        try:
            first.delete()
        except Exception:
            pass
        try:
            second.delete()
        except Exception:
            pass


@pytest.mark.docker_required
def test_get_tunnel_connection_is_stable_for_one_user(argus_db):
    """Repeat lookups give the same primary, so a cached config never drifts."""
    previous_active_ids = _active_config_ids()
    _deactivate_configs(previous_active_ids)
    first = _make_active_config(is_active=True)
    second = _make_active_config(is_active=True)
    user_id = uuid4()
    try:
        service = TunnelService()
        picks = {service.get_tunnel_connection(user_id=user_id).proxy_host for _ in range(5)}
        assert len(picks) == 1
        assert picks.pop() in {first.host, second.host}
    finally:
        try:
            first.delete()
        except Exception:
            pass
        try:
            second.delete()
        except Exception:
            pass
        _restore_configs(previous_active_ids)


@pytest.mark.docker_required
def test_get_tunnel_connection_returns_active_fields(argus_db, active_config):
    """get_tunnel_connection should return active config fields used by SSH clients."""
    result = TunnelService().get_tunnel_connection(user_id=uuid4())
    assert result.proxy_host == active_config.host
    assert result.proxy_port == active_config.port
    assert result.proxy_user == active_config.proxy_user
    assert result.target_host == active_config.target_host
    assert result.target_port == active_config.target_port
    assert result.host_key_fingerprint == active_config.host_key_fingerprint


@pytest.mark.docker_required
def test_register_tunnel_is_stable_per_user_and_lists_every_proxy(argus_db, tunnel_user, active_config):
    """One user keeps one primary, and the response carries the whole failover list."""
    second = _make_active_config(is_active=True)
    try:
        svc = TunnelService()
        first = svc.register_tunnel(user=tunnel_user, public_key=_make_public_key())
        again = svc.register_tunnel(user=tunnel_user, public_key=_make_public_key())

        assert first.proxy_host == again.proxy_host
        assert {p.proxy_host for p in first.proxies} == {active_config.host, second.host}
        assert first.proxies[0].proxy_host == first.proxy_host
    finally:
        try:
            second.delete()
        except Exception:
            pass


@pytest.mark.docker_required
def test_get_tunnel_connection_selects_specific_host(argus_db, active_config):
    """get_tunnel_connection should return requested active host when proxy_host is provided."""
    second = _make_active_config(is_active=True)
    try:
        result = TunnelService().get_tunnel_connection(user_id=uuid4(), proxy_host=second.host)
        assert result.proxy_host == second.host
        assert result.proxy_port == second.port
        assert result.proxy_user == second.proxy_user
    finally:
        try:
            second.delete()
        except Exception:
            pass


@pytest.mark.docker_required
def test_get_tunnel_connection_unknown_host_raises(argus_db, active_config):
    """Selecting an inactive/unknown host should raise."""
    with pytest.raises(TunnelServiceException, match="No active proxy tunnel configuration found for host"):
        TunnelService().get_tunnel_connection(user_id=uuid4(), proxy_host="missing-host.example.com")


@pytest.mark.docker_required
def test_get_tunnel_connection_spreads_users_across_proxies(argus_db, active_config):
    """Different users start at different proxies without a shared counter."""
    second = _make_active_config(is_active=True)
    try:
        svc = TunnelService()
        picks = {svc.get_tunnel_connection(user_id=uuid4()).proxy_host for _ in range(40)}
        assert picks == {active_config.host, second.host}
    finally:
        try:
            second.delete()
        except Exception:
            pass
