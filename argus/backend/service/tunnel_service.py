import base64
import binascii
import hashlib
import logging
import secrets
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TypedDict
from uuid import UUID, uuid4

from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives.serialization import load_ssh_public_key

from argus.backend.models.runtime_store import RuntimeStore
from argus.backend.models.ssh_key import ProxyTunnelConfig, SSHTunnelKey
from argus.backend.models.web import User, UserRoles
from argus.backend.service.user import UserService

LOGGER = logging.getLogger(__name__)

DEFAULT_TTL_SECONDS = 86400  # 24 hours
MIN_TTL_SECONDS = 3600  # 1 hour
MAX_TTL_SECONDS = 2592000  # 30 days
DEFAULT_KEYS_LIST_LIMIT = 5000
PROXY_RR_INDEX_KEY = "ssh_tunnel_proxy_rr_index"


class TunnelServiceException(Exception):
    pass


@dataclass(frozen=True, slots=True)
class TunnelCommonFieldsDTO:
    proxy_user: str
    target_host: str
    target_port: int
    host_key_fingerprint: str


@dataclass(frozen=True, slots=True)
class TunnelRegistrationResponseDTO(TunnelCommonFieldsDTO):
    key_id: UUID
    tunnel_id: UUID
    proxy_host: str
    proxy_port: int
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class TunnelConnectionResponseDTO(TunnelCommonFieldsDTO):
    proxy_host: str
    proxy_port: int


@dataclass(frozen=True, slots=True)
class SSHTunnelKeyDTO:
    key_id: UUID
    user_id: UUID
    tunnel_id: UUID
    public_key: str
    fingerprint: str
    created_at: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class ProxyTunnelConfigDTO(TunnelCommonFieldsDTO):
    id: UUID
    host: str
    port: int
    service_user_id: UUID | None
    is_active: bool


@dataclass(frozen=True, slots=True)
class ProxyTunnelCreateResponseDTO(ProxyTunnelConfigDTO):
    api_token: str = ""


class ProxyTunnelConfigPayload(TypedDict, total=False):
    host: str
    port: int
    proxy_user: str
    target_host: str
    target_port: int
    host_key_fingerprint: str
    is_active: bool


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
    2. Select one active ``ProxyTunnelConfig`` using round-robin.
    3. Insert ``SSHTunnelKey`` with a ScyllaDB TTL so ScyllaDB auto-expires it.
    4. Return the proxy connection parameters plus ``expires_at`` so the client
       knows when to re-register.

    Authorised-keys flow (called from ``GET /client/ssh/keys`` by the proxy
    host via ``AuthorizedKeysCommand``):
    1. Fetch all non-expired ``SSHTunnelKey`` rows.
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
    ) -> TunnelRegistrationResponseDTO:
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
        TunnelRegistrationResponseDTO with keys: ``proxy_host``,
        ``proxy_port``, ``proxy_user``, ``target_host``, ``target_port``,
        ``host_key_fingerprint``, ``expires_at`` (UTC datetime),
        ``tunnel_id``, ``key_id``.
        """
        if not public_key or not public_key.strip():
            raise TunnelServiceException("public_key is required")

        fingerprint = _derive_fingerprint(public_key)

        config = self._get_active_config_round_robin()

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

        return TunnelRegistrationResponseDTO(
            key_id=key.id,
            tunnel_id=config.id,
            proxy_host=config.host,
            proxy_port=config.port,
            proxy_user=config.proxy_user,
            target_host=config.target_host,
            target_port=config.target_port,
            host_key_fingerprint=config.host_key_fingerprint,
            expires_at=expires_at,
        )

    def get_tunnel_connection(self, proxy_host: str | None = None) -> TunnelConnectionResponseDTO:
        """
        Return active proxy tunnel connection details for tunnel clients.

        If ``proxy_host`` is provided, return that active host.
        Otherwise, select one deterministically.
        """
        if proxy_host:
            config = self._get_active_config(proxy_host=proxy_host)
        else:
            config = self._get_active_config_round_robin()
        return TunnelConnectionResponseDTO(
            proxy_host=config.host,
            proxy_port=config.port,
            proxy_user=config.proxy_user,
            target_host=config.target_host,
            target_port=config.target_port,
            host_key_fingerprint=config.host_key_fingerprint,
        )

    # ------------------------------------------------------------------
    # Authorised keys (used by the proxy host AuthorizedKeysCommand)
    # ------------------------------------------------------------------

    def get_authorized_keys(self) -> str:
        """
        Return all non-expired public keys in OpenSSH ``authorized_keys``
        format (one key per line).

        ScyllaDB TTL guarantees that expired rows are already gone by the time
        this is called, so a plain table scan is sufficient.

        """
        rows = SSHTunnelKey.objects.all()

        keys = [row.public_key for row in rows if row.public_key]
        return "\n".join(keys)

    # ------------------------------------------------------------------
    # Key management (admin / informational)
    # ------------------------------------------------------------------

    def list_keys(self, tunnel_id: UUID | str | None = None, user_id: UUID | str | None = None) -> list[SSHTunnelKeyDTO]:
        """
        Return a list of dicts describing all non-expired keys.

        Parameters
        ----------
        tunnel_id:
            When supplied, restrict to keys for that tunnel.
        user_id:
            When supplied, restrict to keys for that user.
        """
        query = SSHTunnelKey.objects

        if tunnel_id is not None:
            if not isinstance(tunnel_id, UUID):
                tunnel_id = UUID(str(tunnel_id))

        if user_id is not None:
            if not isinstance(user_id, UUID):
                user_id = UUID(str(user_id))
            query = query.filter(user_id=user_id)

        if tunnel_id is not None and user_id is None:
            query = query.filter(tunnel_id=tunnel_id)

        rows = list(query.all())

        if tunnel_id is not None and user_id is not None:
            rows = [row for row in rows if row.tunnel_id == tunnel_id]

        rows = rows[:DEFAULT_KEYS_LIST_LIMIT]

        return [self._to_ssh_tunnel_key_dto(row) for row in rows]

    def delete_key(self, key_id: UUID | str) -> None:
        """Delete a single ``SSHTunnelKey`` row."""
        if not isinstance(key_id, UUID):
            key_id = UUID(str(key_id))
        try:
            key = SSHTunnelKey.get(id=key_id)
            key.delete()
        except SSHTunnelKey.DoesNotExist:
            LOGGER.info("SSH key %s was already deleted or TTL-expired", key_id)

    # ------------------------------------------------------------------
    # Proxy tunnel config management
    # ------------------------------------------------------------------

    def get_proxy_tunnel_config(self, tunnel_id: UUID | str | None = None) -> ProxyTunnelConfigDTO | None:
        """
        Return one active proxy tunnel config.

        - If ``tunnel_id`` is provided: return that config only when it exists
          and is active.
        - If ``tunnel_id`` is not provided: return one active config using
          deterministic selection (non-mutating).

        Returns ``None`` if no matching active config exists.
        """
        if tunnel_id is not None:
            if not isinstance(tunnel_id, UUID):
                tunnel_id = UUID(str(tunnel_id))
            try:
                config = ProxyTunnelConfig.get(id=tunnel_id)
                if not config.is_active:
                    return None
                return self._to_proxy_tunnel_config_dto(config)
            except ProxyTunnelConfig.DoesNotExist:
                return None

        try:
            config = self._get_active_config()
            return self._to_proxy_tunnel_config_dto(config)
        except TunnelServiceException:
            return None

    def save_proxy_tunnel_config(self, payload: ProxyTunnelConfigPayload) -> ProxyTunnelCreateResponseDTO:
        """
        Create a new ``ProxyTunnelConfig`` entry.

        1. Creates a dedicated Argus service user (e.g. ``proxy-tunnel-<host>``)
           with a fresh API token — this user is what the proxy host will
           authenticate as when calling ``GET /client/ssh/keys``.
        2. Saves the new config with explicit ``is_active`` (default True) and the
           service user's id stored in ``service_user_id``.

        Required payload keys: ``host``, ``port``, ``proxy_user``,
        ``target_host``, ``target_port``.

        The host key is always discovered via ``ssh-keyscan`` and stored as
        the full known_hosts entry. It is never supplied by the caller.

        Returns the saved config as a dict (including ``service_user_id`` and
        the generated ``api_token`` so the caller can provision the proxy host).
        """
        required = ("host", "port", "proxy_user", "target_host", "target_port")
        missing = [k for k in required if not payload.get(k)]
        if missing:
            raise TunnelServiceException(f"Missing required fields: {', '.join(missing)}")

        is_active = payload.get("is_active", True)
        port = int(payload["port"])
        known_hosts_entry, _ = self._fetch_host_key(payload["host"], port)

        # Create a dedicated service user for this proxy host.
        service_user, api_token = self._create_proxy_service_user(payload["host"])

        config = ProxyTunnelConfig.create(
            id=uuid4(),
            host=payload["host"],
            port=port,
            proxy_user=payload["proxy_user"],
            target_host=payload["target_host"],
            target_port=int(payload["target_port"]),
            host_key_fingerprint=known_hosts_entry,
            service_user_id=service_user.id,
            is_active=is_active,
        )

        return ProxyTunnelCreateResponseDTO(
            id=config.id,
            host=config.host,
            port=port,
            proxy_user=config.proxy_user,
            target_host=config.target_host,
            target_port=int(config.target_port),
            host_key_fingerprint=known_hosts_entry,
            service_user_id=service_user.id,
            is_active=bool(config.is_active),
            api_token=api_token,
        )

    def list_proxy_tunnel_configs(self, active_only: bool | None = None) -> list[ProxyTunnelConfigDTO]:
        """Return proxy tunnel configs, optionally filtered by active state."""
        rows = list(ProxyTunnelConfig.objects.all())
        if active_only is not None:
            rows = [row for row in rows if bool(row.is_active) == active_only]
        rows = sorted(rows, key=lambda row: (row.host or "", str(row.id)))
        return [self._to_proxy_tunnel_config_dto(row) for row in rows]

    def delete_proxy_tunnel_config(self, tunnel_id: UUID | str) -> None:
        """Permanently delete a proxy tunnel config and its associated service user."""
        if not isinstance(tunnel_id, UUID):
            tunnel_id = UUID(str(tunnel_id))
        try:
            config = ProxyTunnelConfig.get(id=tunnel_id)
        except ProxyTunnelConfig.DoesNotExist as exc:
            raise TunnelServiceException(f"Proxy tunnel config {tunnel_id} not found") from exc

        if config.service_user_id:
            try:
                from argus.backend.models.web import ArgusUser  # noqa: PLC0415
                ArgusUser.get(id=config.service_user_id).delete()
            except Exception:  # noqa: BLE001
                pass  # service user already gone — proceed with config deletion

        config.delete()

    def set_proxy_tunnel_config_active(self, tunnel_id: UUID | str, is_active: bool) -> ProxyTunnelConfigDTO:
        """Enable or disable a specific proxy tunnel config."""
        if not isinstance(tunnel_id, UUID):
            tunnel_id = UUID(str(tunnel_id))
        try:
            config = ProxyTunnelConfig.get(id=tunnel_id)
        except ProxyTunnelConfig.DoesNotExist as exc:
            raise TunnelServiceException(f"Proxy tunnel config {tunnel_id} not found") from exc

        config.update(is_active=is_active)
        refreshed = ProxyTunnelConfig.get(id=tunnel_id)
        return self._to_proxy_tunnel_config_dto(refreshed)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_active_configs() -> list[ProxyTunnelConfig]:
        return [cfg for cfg in ProxyTunnelConfig.objects.all() if cfg.is_active]

    @staticmethod
    def _fetch_host_key(host: str, port: int) -> tuple[str, str]:
        """Run ssh-keyscan and return ``(known_hosts_entry, sha256_fingerprint)``.

        ``known_hosts_entry`` is the full ``host keytype keydata`` line suitable
        for writing directly into a known_hosts file.
        ``sha256_fingerprint`` is the ``SHA256:…`` string used for admin
        verification only.
        """
        try:
            result = subprocess.run(
                ["ssh-keyscan", "-p", str(port), "-t", "ed25519,ecdsa,rsa", host],
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
        except FileNotFoundError as exc:
            raise TunnelServiceException("ssh-keyscan is required on the Argus backend host") from exc
        except subprocess.TimeoutExpired as exc:
            raise TunnelServiceException(f"Timed out fetching host key from {host}:{port}") from exc

        # Build a map of keytype → (full_known_hosts_line, pubkey_str).
        # ssh-keyscan output format: "<host> <keytype> <keydata>"
        keys_by_type: dict[str, tuple[str, str]] = {}
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            parts = stripped.split()
            if len(parts) < 3:
                continue
            key_type = parts[1]
            key_data = parts[2]
            if key_type.startswith("ssh-") or key_type.startswith("ecdsa-"):
                full_line = f"{host} {key_type} {key_data}"
                pubkey_str = f"{key_type} {key_data}"
                keys_by_type.setdefault(key_type, (full_line, pubkey_str))

        preferred_types = (
            "ssh-ed25519",
            "ecdsa-sha2-nistp256",
            "ecdsa-sha2-nistp384",
            "ecdsa-sha2-nistp521",
            "ssh-rsa",
        )
        for key_type in preferred_types:
            if key_type in keys_by_type:
                full_line, pubkey_str = keys_by_type[key_type]
                return full_line, _derive_fingerprint(pubkey_str)

        if keys_by_type:
            full_line, pubkey_str = next(iter(keys_by_type.values()))
            return full_line, _derive_fingerprint(pubkey_str)

        stderr = (result.stderr or "").strip()
        if stderr:
            raise TunnelServiceException(f"Failed to fetch host key for {host}:{port}: {stderr}")
        raise TunnelServiceException(f"Failed to fetch host key for {host}:{port}")

    def _get_active_config(self, proxy_host: str | None = None) -> ProxyTunnelConfig:
        configs = self._get_active_configs()
        if not configs:
            raise TunnelServiceException(
                "No active proxy tunnel configuration found. "
                "An admin must configure a proxy host before tunnel registration is possible."
            )

        if proxy_host:
            matching_configs = [cfg for cfg in configs if cfg.host == proxy_host]
            if not matching_configs:
                raise TunnelServiceException(f"No active proxy tunnel configuration found for host: {proxy_host}")
            return sorted(matching_configs, key=lambda cfg: str(cfg.id))[0]

        return sorted(configs, key=lambda cfg: (cfg.host or "", str(cfg.id)))[0]

    def _get_active_config_round_robin(self) -> ProxyTunnelConfig:
        configs = sorted(self._get_active_configs(), key=lambda cfg: (cfg.host or "", str(cfg.id)))
        if not configs:
            raise TunnelServiceException(
                "No active proxy tunnel configuration found. "
                "An admin must configure a proxy host before tunnel registration is possible."
            )

        current_index = 0
        store = None
        try:
            store = RuntimeStore.get(key=PROXY_RR_INDEX_KEY)
            if isinstance(store.value, int):
                current_index = store.value
        except RuntimeStore.DoesNotExist:
            pass

        selected = configs[current_index % len(configs)]
        next_index = (current_index + 1) % len(configs)

        if store is None:
            store = RuntimeStore(key=PROXY_RR_INDEX_KEY)
        store.value = next_index
        store.save()

        return selected

    @staticmethod
    def _create_proxy_service_user(host: str) -> tuple[User, str]:
        """
        Create (or re-use) a service ``User`` for the given proxy host and
        return ``(user, api_token)``.

        The username follows the pattern ``proxy-tunnel-<host>`` to make it
        easy to identify in the user list.
        """
        username = f"proxy-tunnel-{host}"

        # Re-use existing tunnel service user if it already exists.
        existing = User.exists_by_name(username)
        if existing:
            if not existing.is_service_user() or not UserService.check_roles(UserRoles.SSHTunnelServer, existing):
                raise TunnelServiceException(
                    f"User '{username}' already exists and is not a dedicated SSH tunnel service user"
                )
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
            roles=[UserRoles.SSHTunnelServer.value],
            api_token=api_token,
            service_user=True,
        )
        return user, api_token

    @staticmethod
    def _to_ssh_tunnel_key_dto(row: SSHTunnelKey) -> SSHTunnelKeyDTO:
        return SSHTunnelKeyDTO(
            key_id=row.id,
            user_id=row.user_id,
            tunnel_id=row.tunnel_id,
            public_key=row.public_key,
            fingerprint=row.fingerprint,
            created_at=row.created_at,
            expires_at=row.expires_at,
        )

    @staticmethod
    def _to_proxy_tunnel_config_dto(config: ProxyTunnelConfig) -> ProxyTunnelConfigDTO:
        return ProxyTunnelConfigDTO(
            id=config.id,
            host=config.host,
            port=config.port,
            proxy_user=config.proxy_user,
            target_host=config.target_host,
            target_port=config.target_port,
            host_key_fingerprint=config.host_key_fingerprint,
            service_user_id=config.service_user_id,
            is_active=bool(config.is_active),
        )
