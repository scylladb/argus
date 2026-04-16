import base64
import binascii
import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from argus.backend.error_handlers import APIException
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives.serialization import load_ssh_public_key

from argus.backend.models.ssh_key import ProxyTunnelConfig, SSHTunnelKey
from argus.backend.models.web import User, UserRoles
from argus.backend.service.user import UserService

LOGGER = logging.getLogger(__name__)

DEFAULT_TTL_SECONDS = 86400  # 24 hours
MIN_TTL_SECONDS = 86400  # 24 hours
MAX_TTL_SECONDS = 2592000  # 30 days
DEFAULT_KEYS_LIST_LIMIT = 5000


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
        stripped_key = public_key_str.strip()
        parts = stripped_key.split()
        if len(parts) < 2:
            raise ValueError("Malformed OpenSSH public key")

        load_ssh_public_key(stripped_key.encode("utf-8"))
        key_blob = base64.b64decode(parts[1].encode("ascii"), validate=True)
        digest = hashlib.sha256(key_blob).digest()
        b64 = base64.b64encode(digest).rstrip(b"=").decode("ascii")
        return f"SHA256:{b64}"
    except (ValueError, UnsupportedAlgorithm, TypeError, binascii.Error) as exc:
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
        ttl_seconds:
            How long (in seconds) the key should remain valid.  Defaults to
            ``DEFAULT_TTL_SECONDS`` (86 400 / 24 h).

        Returns
        -------
        dict with keys: ``proxy_host``, ``proxy_port``, ``proxy_user``,
        ``target_host``, ``target_port``, ``host_key_fingerprint``,
        ``expires_at`` (UTC datetime), ``tunnel_id``, ``key_id``.
        """
        if not public_key or not public_key.strip():
            raise TunnelServiceException("public_key is required")

        fingerprint = _derive_fingerprint(public_key)

        config = self._get_active_config()

        if ttl_seconds is None:
            ttl = DEFAULT_TTL_SECONDS
        else:
            try:
                ttl = int(ttl_seconds)
            except (TypeError, ValueError) as exc:
                raise TunnelServiceException(
                    f"ttl_seconds must be between {MIN_TTL_SECONDS} and {MAX_TTL_SECONDS} seconds"
                ) from exc
            if ttl < MIN_TTL_SECONDS or ttl > MAX_TTL_SECONDS:
                raise TunnelServiceException(
                    f"ttl_seconds must be between {MIN_TTL_SECONDS} and {MAX_TTL_SECONDS} seconds"
                )

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
            "expires_at": expires_at,
        }

    def get_tunnel_connection(self) -> dict:
        """
        Return active proxy tunnel connection details for tunnel clients.
        """
        config = self._get_active_config()
        return {
            "proxy_host": config.host,
            "proxy_port": config.port,
            "proxy_user": config.proxy_user,
            "target_host": config.target_host,
            "target_port": config.target_port,
            "host_key_fingerprint": config.host_key_fingerprint,
        }

    # ------------------------------------------------------------------
    # Authorised keys (used by the proxy host AuthorizedKeysCommand)
    # ------------------------------------------------------------------

    def get_authorized_keys(self, service_user_id: UUID | str) -> str:
        """
        Return all non-expired public keys in OpenSSH ``authorized_keys``
        format (one key per line).

        ScyllaDB TTL guarantees that expired rows are already gone by the time
        this is called, so a plain table scan is sufficient.

        """
        if not isinstance(service_user_id, UUID):
            service_user_id = UUID(str(service_user_id))

        config = self._get_active_config()
        if config.service_user_id != service_user_id:
            raise APIException("Not authorized to fetch SSH keys for the active tunnel")

        rows = SSHTunnelKey.objects.filter(tunnel_id=config.id).all()

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
            rows = SSHTunnelKey.objects.filter(tunnel_id=tunnel_id).limit(DEFAULT_KEYS_LIST_LIMIT).all()
        else:
            rows = SSHTunnelKey.objects.limit(DEFAULT_KEYS_LIST_LIMIT).all()

        return [row._as_dict() for row in rows]

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
                return config._as_dict()
            except ProxyTunnelConfig.DoesNotExist:
                return None

        try:
            config = self._get_active_config()
            return config._as_dict()
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
        for existing in ProxyTunnelConfig.objects.all():
            if existing.is_active:
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

        result = config._as_dict()
        result["api_token"] = api_token
        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_active_config(self) -> ProxyTunnelConfig:
        configs = [cfg for cfg in ProxyTunnelConfig.objects.all() if cfg.is_active]
        if not configs:
            raise TunnelServiceException(
                "No active proxy tunnel configuration found. "
                "An admin must configure a proxy host before tunnel registration is possible."
            )
        return configs[0]

    @staticmethod
    def _create_proxy_service_user(host: str) -> tuple[User, str]:
        """
        Create (or re-use) a service ``User`` for the given proxy host and
        return ``(user, api_token)``.

        The username follows the pattern ``proxy-tunnel-<host>`` to make it
        easy to identify in the user list.
        """
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
