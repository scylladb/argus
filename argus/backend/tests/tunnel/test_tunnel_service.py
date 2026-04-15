"""
Tests for TunnelService — require a running ScyllaDB container.

Run with:
    uv run pytest argus/backend/tests/tunnel/test_tunnel_service.py -m docker_required -v
"""
import pytest
from datetime import UTC, datetime
from secrets import token_hex
from uuid import uuid4

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from argus.backend.models.ssh_key import ProxyTunnelConfig, SSHTunnelKey
from argus.backend.models.web import User, UserRoles
from argus.backend.service.tunnel_service import TunnelService, TunnelServiceException


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
        is_active=True,
    )
    defaults.update(overrides)
    return ProxyTunnelConfig.create(**defaults)


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
    config = _make_active_config()
    yield config
    try:
        config.delete()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# TunnelService.register_tunnel
# ---------------------------------------------------------------------------

@pytest.mark.docker_required
def test_register_tunnel_stores_key(argus_db, tunnel_user, active_config):
    """register_tunnel should persist an SSHTunnelKey row in the DB."""
    pub_key = _make_public_key()
    svc = TunnelService()

    result = svc.register_tunnel(user=tunnel_user, public_key=pub_key)

    assert result["proxy_host"] == active_config.host
    assert result["proxy_port"] == active_config.port
    assert result["proxy_user"] == active_config.proxy_user
    assert result["target_host"] == active_config.target_host
    assert result["target_port"] == active_config.target_port
    assert result["host_key_fingerprint"] == active_config.host_key_fingerprint
    assert result["expires_at"].endswith("Z")
    assert "key_id" in result
    assert "tunnel_id" in result

    # Verify the DB row exists
    key = SSHTunnelKey.get(id=result["key_id"])
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
    ttl = 3600  # 1 hour

    before = datetime.now(tz=timezone.utc)
    result = svc.register_tunnel(user=tunnel_user, public_key=pub_key, ttl_seconds=ttl)
    after = datetime.now(tz=timezone.utc)

    expires_at = datetime.fromisoformat(result["expires_at"].rstrip("Z")).replace(tzinfo=timezone.utc)
    # expires_at should be approximately now + 1 hour (allow ±5 s for test timing)
    assert (before.timestamp() + ttl - 5) <= expires_at.timestamp() <= (after.timestamp() + ttl + 5)


@pytest.mark.docker_required
def test_register_tunnel_no_active_config_raises(argus_db, tunnel_user):
    """register_tunnel should raise TunnelServiceException when no active config exists."""
    # Deactivate all configs
    for cfg in ProxyTunnelConfig.objects.filter(is_active=True).all():
        cfg.update(is_active=False)

    svc = TunnelService()
    with pytest.raises(TunnelServiceException, match="No active proxy tunnel"):
        svc.register_tunnel(user=tunnel_user, public_key=_make_public_key())


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


@pytest.mark.docker_required
def test_register_tunnel_by_tunnel_id(argus_db, tunnel_user):
    """register_tunnel should accept an explicit tunnel_id."""
    config = _make_active_config(is_active=False)  # not the active one
    try:
        pub_key = _make_public_key()
        svc = TunnelService()
        result = svc.register_tunnel(user=tunnel_user, public_key=pub_key, tunnel_id=config.id)
        assert result["tunnel_id"] == str(config.id)
    finally:
        try:
            config.delete()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# TunnelService.get_authorized_keys
# ---------------------------------------------------------------------------

@pytest.mark.docker_required
def test_get_authorized_keys_format(argus_db, tunnel_user, active_config):
    """Each line of get_authorized_keys output should be a valid OpenSSH key."""
    pub_key = _make_public_key()
    svc = TunnelService()
    svc.register_tunnel(user=tunnel_user, public_key=pub_key)

    keys_text = svc.get_authorized_keys(tunnel_id=active_config.id)
    lines = [ln for ln in keys_text.splitlines() if ln.strip()]
    assert any(pub_key.strip() in ln for ln in lines), "Registered key not found in authorized_keys output"
    for line in lines:
        # Each line must start with a key type
        assert line.startswith(("ssh-", "ecdsa-", "sk-")), f"Unexpected line format: {line!r}"


@pytest.mark.docker_required
def test_get_authorized_keys_scoped_by_tunnel(argus_db, tunnel_user):
    """get_authorized_keys with a specific tunnel_id should not return keys from other tunnels."""
    config_a = _make_active_config(is_active=False)
    config_b = _make_active_config(is_active=False)
    try:
        pub_key_a = _make_public_key()
        pub_key_b = _make_public_key()
        svc = TunnelService()
        svc.register_tunnel(user=tunnel_user, public_key=pub_key_a, tunnel_id=config_a.id)
        svc.register_tunnel(user=tunnel_user, public_key=pub_key_b, tunnel_id=config_b.id)

        keys_for_a = svc.get_authorized_keys(tunnel_id=config_a.id)
        assert pub_key_a.strip() in keys_for_a
        assert pub_key_b.strip() not in keys_for_a

        keys_for_b = svc.get_authorized_keys(tunnel_id=config_b.id)
        assert pub_key_b.strip() in keys_for_b
        assert pub_key_a.strip() not in keys_for_b
    finally:
        for cfg in (config_a, config_b):
            try:
                cfg.delete()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# TunnelService.delete_key
# ---------------------------------------------------------------------------

@pytest.mark.docker_required
def test_delete_key_removes_row(argus_db, tunnel_user, active_config):
    """delete_key should remove the SSHTunnelKey row from the DB."""
    pub_key = _make_public_key()
    svc = TunnelService()
    result = svc.register_tunnel(user=tunnel_user, public_key=pub_key)
    key_id = result["key_id"]

    svc.delete_key(key_id)

    with pytest.raises(SSHTunnelKey.DoesNotExist):
        SSHTunnelKey.get(id=key_id)


@pytest.mark.docker_required
def test_delete_key_nonexistent_raises(argus_db):
    """delete_key for an unknown id should raise TunnelServiceException."""
    svc = TunnelService()
    with pytest.raises(TunnelServiceException, match="not found"):
        svc.delete_key(uuid4())


# ---------------------------------------------------------------------------
# TunnelService.save_proxy_tunnel_config
# ---------------------------------------------------------------------------

@pytest.mark.docker_required
def test_save_proxy_tunnel_config_creates_service_user(argus_db):
    """save_proxy_tunnel_config should create a dedicated service user."""
    # Deactivate all configs first so we start clean
    for cfg in ProxyTunnelConfig.objects.filter(is_active=True).all():
        cfg.update(is_active=False)

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

    assert result["is_active"] is True
    assert result["service_user_id"] is not None
    assert "api_token" in result  # token returned so admin can provision

    # Service user exists in DB
    service_user = User.get(id=result["service_user_id"])
    assert service_user.service_user is True
    assert f"proxy-tunnel-{host}" in service_user.username


@pytest.mark.docker_required
def test_save_proxy_tunnel_config_deactivates_old(argus_db):
    """Creating a new config should deactivate the previously active one."""
    # Deactivate any stale configs
    for cfg in ProxyTunnelConfig.objects.filter(is_active=True).all():
        cfg.update(is_active=False)

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
    assert first["is_active"] is True

    second_payload = dict(
        host=f"proxy-second-{uuid4().hex[:6]}.example.com",
        port=22,
        proxy_user="argus-proxy",
        target_host="10.0.2.2",
        target_port=8080,
        host_key_fingerprint="SHA256:second",
    )
    second = svc.save_proxy_tunnel_config(second_payload)
    assert second["is_active"] is True

    # The first config should now be inactive in the DB
    refreshed_first = ProxyTunnelConfig.get(id=first["id"])
    assert refreshed_first.is_active is False


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
    for cfg in ProxyTunnelConfig.objects.filter(is_active=True).all():
        cfg.update(is_active=False)

    config = _make_active_config()
    try:
        svc = TunnelService()
        result = svc.get_proxy_tunnel_config()
        assert result is not None
        assert result["id"] == str(config.id)
        assert result["is_active"] is True
    finally:
        try:
            config.delete()
        except Exception:
            pass


@pytest.mark.docker_required
def test_get_proxy_tunnel_config_by_id(argus_db):
    """get_proxy_tunnel_config with a tunnel_id should return that specific config."""
    config = _make_active_config(is_active=False)
    try:
        svc = TunnelService()
        result = svc.get_proxy_tunnel_config(tunnel_id=config.id)
        assert result is not None
        assert result["id"] == str(config.id)
    finally:
        try:
            config.delete()
        except Exception:
            pass


@pytest.mark.docker_required
def test_get_proxy_tunnel_config_none_when_no_active(argus_db):
    """get_proxy_tunnel_config should return None when no active config exists."""
    for cfg in ProxyTunnelConfig.objects.filter(is_active=True).all():
        cfg.update(is_active=False)

    svc = TunnelService()
    assert svc.get_proxy_tunnel_config() is None
