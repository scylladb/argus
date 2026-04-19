"""
Tests for TunnelService — require a running ScyllaDB container.

Run with:
    uv run pytest argus/backend/tests/tunnel/test_tunnel_service.py -m docker_required -v
"""
import base64
import hashlib
import pytest
from datetime import UTC, datetime
from secrets import token_hex
from uuid import uuid4

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from argus.backend.models.runtime_store import RuntimeStore
from argus.backend.models.ssh_key import ProxyTunnelConfig, SSHTunnelKey
from argus.backend.models.web import User, UserRoles
from argus.backend.service.tunnel_service import TunnelService, TunnelServiceException, _derive_fingerprint


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
        api_token=token_hex(32),
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
        host_key_fingerprint="SHA256:testfingerprint",
        service_user_id=uuid4(),
        is_active=True,
    )
    defaults.update(overrides)
    return ProxyTunnelConfig.create(**defaults)


def _active_config_ids() -> list:
    return [cfg.id for cfg in ProxyTunnelConfig.objects.all() if cfg.is_active]


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


def _clear_proxy_rr_state() -> None:
    try:
        RuntimeStore.get(key="ssh_tunnel_proxy_rr_index").delete()
    except RuntimeStore.DoesNotExist:
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
    _clear_proxy_rr_state()

    config = _make_active_config()
    yield config
    try:
        config.delete()
    except Exception:
        pass

    _restore_configs(previous_active_ids)


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
        SSHTunnelKey.objects.ttl(86400).create(
            id=uuid4(),
            user_id=tunnel_user.id,
            tunnel_id=active_config.id,
            public_key=key_a,
            fingerprint="SHA256:test-a",
            created_at=now_utc,
            expires_at=now_utc,
        )
        SSHTunnelKey.objects.ttl(86400).create(
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

    with pytest.raises(SSHTunnelKey.DoesNotExist):
        SSHTunnelKey.get(id=key_id)


@pytest.mark.docker_required
def test_delete_key_nonexistent_is_noop(argus_db):
    """delete_key for an unknown id should not raise (already TTL-expired is valid)."""
    svc = TunnelService()
    svc.delete_key(uuid4())


# ---------------------------------------------------------------------------
# TunnelService.save_proxy_tunnel_config
# ---------------------------------------------------------------------------

@pytest.mark.docker_required
def test_save_proxy_tunnel_config_creates_service_user(argus_db):
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
            host_key_fingerprint="SHA256:svcusertest",
        )
        svc = TunnelService()
        result = svc.save_proxy_tunnel_config(payload)

        assert result.is_active is True
        assert result.service_user_id is not None
        assert result.api_token is not None

        service_user = User.get(id=result.service_user_id)
        assert service_user.service_user is True
        assert f"proxy-tunnel-{host}" in service_user.username
        assert service_user.roles == [UserRoles.SSHTunnelServer.value]
    finally:
        _restore_configs(previous_active_ids)


@pytest.mark.docker_required
def test_save_proxy_tunnel_config_deactivates_old(argus_db):
    """Creating a new config should leave prior active configs active."""
    previous_active_ids = _active_config_ids()
    _deactivate_configs(previous_active_ids)

    try:
        first_payload = dict(
            host=f"proxy-first-{uuid4().hex[:6]}.example.com",
            port=22,
            proxy_user="argus-proxy",
            target_host="10.0.2.1",
            target_port=8080,
            host_key_fingerprint="SHA256:first",
        )
        svc = TunnelService()
        first = svc.save_proxy_tunnel_config(first_payload)
        assert first.is_active is True

        second_payload = dict(
            host=f"proxy-second-{uuid4().hex[:6]}.example.com",
            port=22,
            proxy_user="argus-proxy",
            target_host="10.0.2.2",
            target_port=8080,
            host_key_fingerprint="SHA256:second",
        )
        second = svc.save_proxy_tunnel_config(second_payload)
        assert second.is_active is True

        refreshed_first = ProxyTunnelConfig.get(id=first.id)
        assert refreshed_first.is_active is True
    finally:
        _restore_configs(previous_active_ids)


@pytest.mark.docker_required
def test_save_proxy_tunnel_config_missing_fields(argus_db):
    """save_proxy_tunnel_config should raise when required fields are absent."""
    svc = TunnelService()
    with pytest.raises(TunnelServiceException, match="Missing required fields"):
        svc.save_proxy_tunnel_config({"host": "proxy.example.com"})


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
def test_get_tunnel_connection_returns_active_fields(argus_db, active_config):
    """get_tunnel_connection should return active config fields used by SSH clients."""
    result = TunnelService().get_tunnel_connection()
    assert result.proxy_host == active_config.host
    assert result.proxy_port == active_config.port
    assert result.proxy_user == active_config.proxy_user
    assert result.target_host == active_config.target_host
    assert result.target_port == active_config.target_port
    assert result.host_key_fingerprint == active_config.host_key_fingerprint


@pytest.mark.docker_required
def test_register_tunnel_uses_round_robin_when_multiple_active(argus_db, tunnel_user, active_config):
    """register_tunnel should rotate selected host when multiple active configs exist."""
    second = _make_active_config(is_active=True)
    try:
        _clear_proxy_rr_state()
        svc = TunnelService()
        first = svc.register_tunnel(user=tunnel_user, public_key=_make_public_key())
        second_pick = svc.register_tunnel(user=tunnel_user, public_key=_make_public_key())

        assert first.proxy_host != second_pick.proxy_host
        assert {first.proxy_host, second_pick.proxy_host} == {active_config.host, second.host}
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
        result = TunnelService().get_tunnel_connection(proxy_host=second.host)
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
        TunnelService().get_tunnel_connection(proxy_host="missing-host.example.com")


@pytest.mark.docker_required
def test_get_tunnel_connection_round_robin(argus_db, active_config):
    """get_tunnel_connection without proxy_host should rotate across active hosts."""
    second = _make_active_config(is_active=True)
    try:
        _clear_proxy_rr_state()
        svc = TunnelService()
        first = svc.get_tunnel_connection()
        second_pick = svc.get_tunnel_connection()

        assert first.proxy_host != second_pick.proxy_host
        assert {first.proxy_host, second_pick.proxy_host} == {active_config.host, second.host}
    finally:
        try:
            second.delete()
        except Exception:
            pass
