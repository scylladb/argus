import base64
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, load_ssh_public_key

from argus.backend.models.ssh_key import ProxyTunnelConfig, SSHTunnelKey
from argus.backend.models.web import User, UserRoles

LOGGER = logging.getLogger(__name__)

DEFAULT_TTL_SECONDS = 86400  # 24 hours


class TunnelServiceException(Exception):
    pass


def _derive_fingerprint(public_key_str: str) -> str:
    """
    Derive an OpenSSH SHA-256 fingerprint from an OpenSSH-formatted public key
    string (e.g. ``ssh-ed25519 AAAA... comment``).

    Returns a string of the form ``SHA256:<base64>``, matching the output of
    ``ssh-keygen -lf``.

    Raises ``TunnelServiceException`` if the key cannot be parsed.
    """
    try:
        key_bytes = public_key_str.strip().encode("utf-8")
        public_key = load_ssh_public_key(key_bytes)
        raw = public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
        digest = hashlib.sha256(raw).digest()
        b64 = base64.b64encode(digest).rstrip(b"=").decode("ascii")
        return f"SHA256:{b64}"
    except (ValueError, UnsupportedAlgorithm, TypeError) as exc:
        raise TunnelServiceException(f"Invalid SSH public key: {exc}") from exc


class TunnelService:
    """
    Business logic for SSH tunnel key registration and proxy tunnel config
    management.

    Key registration flow (called from ``POST /client/ssh/tunnel``):
    1. Validate and fingerprint the supplied public key.
    2. Fetch the active ``ProxyTunnelConfig`` — raise if none exists.
    3. Insert ``SSHTunnelKey`` with a ScyllaDB TTL so ScyllaDB auto-expires it.
    4. Return the proxy connection parameters plus ``expires_at`` so the client
       knows when to re-register.

    Authorised-keys flow (called from ``GET /client/ssh/keys`` by the proxy
    host via ``AuthorizedKeysCommand``):
    1. Fetch all non-expired ``SSHTunnelKey`` rows for the given tunnel.
    2. Return them as a newline-separated OpenSSH ``authorized_keys`` string.
    """

    # ------------------------------------------------------------------
    # Public key registration
    # ------------------------------------------------------------------

    def register_tunnel(
        self,
        user: User,
        public_key: str,
        tunnel_id: UUID | str | None = None,
        ttl_seconds: int | None = None,
    ) -> dict:
        """
        Register ``public_key`` for ``user`` against the active (or specified)
        proxy tunnel config.

        Parameters
        ----------
        user:
            The authenticated Argus user.
        public_key:
            OpenSSH-encoded ed25519 (or other) public key string.
        tunnel_id:
            Optional. If supplied, register the key against that specific
            ``ProxyTunnelConfig`` id.  Otherwise the currently active config is
            used.
        ttl_seconds:
            How long (in seconds) the key should remain valid.  Defaults to
            ``DEFAULT_TTL_SECONDS`` (86 400 / 24 h).

        Returns
        -------
        dict with keys: ``proxy_host``, ``proxy_port``, ``proxy_user``,
        ``target_host``, ``target_port``, ``host_key_fingerprint``,
        ``expires_at`` (UTC ISO-8601 string), ``tunnel_id``, ``key_id``.
        """
        if not public_key or not public_key.strip():
            raise TunnelServiceException("public_key is required")

        fingerprint = _derive_fingerprint(public_key)

        if tunnel_id is not None:
            if not isinstance(tunnel_id, UUID):
                tunnel_id = UUID(str(tunnel_id))
            try:
                config = ProxyTunnelConfig.get(id=tunnel_id)
            except ProxyTunnelConfig.DoesNotExist as exc:
                raise TunnelServiceException(f"Proxy tunnel config {tunnel_id} not found") from exc
        else:
            config = self._get_active_config()

        ttl = int(ttl_seconds) if ttl_seconds else DEFAULT_TTL_SECONDS
        now_utc = datetime.now(tz=timezone.utc).replace(tzinfo=None)
        expires_at = now_utc + timedelta(seconds=ttl)

        key = SSHTunnelKey.objects.ttl(ttl).create(
            id=uuid4(),
            user_id=user.id,
            tunnel_id=config.id,
            public_key=public_key.strip(),
            fingerprint=fingerprint,
            created_at=now_utc,
            expires_at=expires_at,
        )

        return {
            "key_id": str(key.id),
            "tunnel_id": str(config.id),
            "proxy_host": config.host,
            "proxy_port": config.port,
            "proxy_user": config.proxy_user,
            "target_host": config.target_host,
            "target_port": config.target_port,
            "host_key_fingerprint": config.host_key_fingerprint,
            "expires_at": expires_at.isoformat() + "Z",
        }

    # ------------------------------------------------------------------
    # Authorised keys (used by the proxy host AuthorizedKeysCommand)
    # ------------------------------------------------------------------

    def get_authorized_keys(self, tunnel_id: UUID | str | None = None) -> str:
        """
        Return all non-expired public keys in OpenSSH ``authorized_keys``
        format (one key per line).

        ScyllaDB TTL guarantees that expired rows are already gone by the time
        this is called, so a plain table scan is sufficient.

        Parameters
        ----------
        tunnel_id:
            When supplied, only keys for that tunnel are returned.  When
            omitted, all keys across all tunnels are returned.
        """
        if tunnel_id is not None:
            if not isinstance(tunnel_id, UUID):
                tunnel_id = UUID(str(tunnel_id))
            rows = SSHTunnelKey.objects.filter(tunnel_id=tunnel_id).all()
        else:
            rows = SSHTunnelKey.objects.all()

        keys = [row.public_key for row in rows if row.public_key]
        return "\n".join(keys)

    # ------------------------------------------------------------------
    # Key management (admin / informational)
    # ------------------------------------------------------------------

    def list_keys(self, tunnel_id: UUID | str | None = None) -> list[dict]:
        """
        Return a list of dicts describing all non-expired keys.

        Parameters
        ----------
        tunnel_id:
            When supplied, restrict to keys for that tunnel.
        """
        if tunnel_id is not None:
            if not isinstance(tunnel_id, UUID):
                tunnel_id = UUID(str(tunnel_id))
            rows = SSHTunnelKey.objects.filter(tunnel_id=tunnel_id).all()
        else:
            rows = SSHTunnelKey.objects.all()

        return [
            {
                "id": str(row.id),
                "user_id": str(row.user_id),
                "tunnel_id": str(row.tunnel_id),
                "fingerprint": row.fingerprint,
                "created_at": row.created_at.isoformat() + "Z" if row.created_at else None,
                "expires_at": row.expires_at.isoformat() + "Z" if row.expires_at else None,
            }
            for row in rows
        ]

    def delete_key(self, key_id: UUID | str) -> None:
        """
        Delete a single ``SSHTunnelKey`` row.  Takes immediate effect — the
        next ``AuthorizedKeysCommand`` call on the proxy host will not include
        this key.
        """
        if not isinstance(key_id, UUID):
            key_id = UUID(str(key_id))
        try:
            key = SSHTunnelKey.get(id=key_id)
            key.delete()
        except SSHTunnelKey.DoesNotExist as exc:
            raise TunnelServiceException(f"SSH key {key_id} not found") from exc

    # ------------------------------------------------------------------
    # Proxy tunnel config management
    # ------------------------------------------------------------------

    def get_proxy_tunnel_config(self, tunnel_id: UUID | str | None = None) -> dict | None:
        """
        Return the active proxy tunnel config as a dict, or a specific config
        if ``tunnel_id`` is provided.  Returns ``None`` if none exists.
        """
        if tunnel_id is not None:
            if not isinstance(tunnel_id, UUID):
                tunnel_id = UUID(str(tunnel_id))
            try:
                config = ProxyTunnelConfig.get(id=tunnel_id)
                return self._config_to_dict(config)
            except ProxyTunnelConfig.DoesNotExist:
                return None

        try:
            config = self._get_active_config()
            return self._config_to_dict(config)
        except TunnelServiceException:
            return None

    def save_proxy_tunnel_config(self, payload: dict) -> dict:
        """
        Create a new ``ProxyTunnelConfig`` entry.

        1. Deactivates any existing active config.
        2. Creates a dedicated Argus service user (e.g. ``proxy-tunnel-<host>``)
           with a fresh API token — this user is what the proxy host will
           authenticate as when calling ``GET /client/ssh/keys``.
        3. Saves the new config with ``is_active=True`` and the service user's
           id stored in ``service_user_id``.

        Required payload keys: ``host``, ``port``, ``proxy_user``,
        ``target_host``, ``target_port``, ``host_key_fingerprint``.

        Returns the saved config as a dict (including ``service_user_id`` and
        the generated ``api_token`` so the caller can provision the proxy host).
        """
        required = ("host", "port", "proxy_user", "target_host", "target_port", "host_key_fingerprint")
        missing = [k for k in required if not payload.get(k)]
        if missing:
            raise TunnelServiceException(f"Missing required fields: {', '.join(missing)}")

        # Deactivate any currently active config.
        for existing in ProxyTunnelConfig.objects.filter(is_active=True).all():
            existing.update(is_active=False)

        # Create a dedicated service user for this proxy host.
        service_user, api_token = self._create_proxy_service_user(payload["host"])

        config = ProxyTunnelConfig.create(
            id=uuid4(),
            host=payload["host"],
            port=int(payload["port"]),
            proxy_user=payload["proxy_user"],
            target_host=payload["target_host"],
            target_port=int(payload["target_port"]),
            host_key_fingerprint=payload["host_key_fingerprint"],
            service_user_id=service_user.id,
            is_active=True,
        )

        result = self._config_to_dict(config)
        result["api_token"] = api_token
        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_active_config(self) -> ProxyTunnelConfig:
        configs = list(ProxyTunnelConfig.objects.filter(is_active=True).all())
        if not configs:
            raise TunnelServiceException(
                "No active proxy tunnel configuration found. "
                "An admin must configure a proxy host before tunnel registration is possible."
            )
        return configs[0]

    @staticmethod
    def _config_to_dict(config: ProxyTunnelConfig) -> dict:
        return {
            "id": str(config.id),
            "host": config.host,
            "port": config.port,
            "proxy_user": config.proxy_user,
            "target_host": config.target_host,
            "target_port": config.target_port,
            "host_key_fingerprint": config.host_key_fingerprint,
            "service_user_id": str(config.service_user_id) if config.service_user_id else None,
            "is_active": config.is_active,
        }

    @staticmethod
    def _create_proxy_service_user(host: str) -> tuple[User, str]:
        """
        Create (or re-use) a service ``User`` for the given proxy host and
        return ``(user, api_token)``.

        The username follows the pattern ``proxy-tunnel-<host>`` to make it
        easy to identify in the user list.
        """
        import secrets
        from argus.backend.service.user import UserService

        username = f"proxy-tunnel-{host}"

        # Re-use existing service user if it already exists.
        existing = User.exists_by_name(username)
        if existing:
            svc = UserService()
            token = svc.get_or_generate_token(existing)
            return existing, token

        api_token = secrets.token_hex(32)
        now = datetime.now(tz=timezone.utc).replace(tzinfo=None)
        user = User.create(
            id=uuid4(),
            username=username,
            full_name=f"Proxy Tunnel Service User ({host})",
            password="",
            email=f"{username}@argus.internal",
            registration_date=now,
            roles=[UserRoles.User.value],
            api_token=api_token,
            service_user=True,
        )
        return user, api_token
