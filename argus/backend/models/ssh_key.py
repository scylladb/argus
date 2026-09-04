from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import Field
from coodie import Indexed, PrimaryKey
from coodie.sync import Document


def _utcnow_naive() -> datetime:
    return datetime.now(tz=UTC).replace(tzinfo=None)


class SSHTunnelKey(Document):
    """
    Stores a client-registered SSH public key for a specific (user, tunnel) pair.

    Rows are inserted with a ScyllaDB TTL (default 24 h). The ``expires_at``
    field is informational — it mirrors the TTL so the client knows when to
    re-register. Actual expiry is handled automatically by ScyllaDB.
    """

    id: Annotated[UUID, PrimaryKey()] = Field(default_factory=uuid4)
    user_id: Annotated[UUID, Indexed()]
    tunnel_id: Annotated[UUID, Indexed()]
    public_key: str
    fingerprint: Annotated[str, Indexed()]
    created_at: datetime = Field(default_factory=_utcnow_naive)
    expires_at: datetime

    class Settings:
        # cqlengine collapsed the consecutive capitals when deriving the name
        name = "sshtunnel_key"


class ProxyTunnelConfig(Document):
    """
    Stores the configuration of an SSH proxy tunnel server.

    Multiple configs can be active at the same time. A client receives every
    active config, ordered by a stable rotation keyed on its user, and fails
    over down the list when its primary proxy is unreachable.

    A dedicated Argus service user (``service_user_id``) is created per
    proxy host so the proxy host can call the authorised-keys API with its
    own isolated credentials.
    """

    id: Annotated[UUID, PrimaryKey()] = Field(default_factory=uuid4)
    host: str
    port: int
    proxy_user: str
    target_host: str
    target_port: int
    host_key_fingerprint: str
    service_user_id: UUID
    is_active: bool = True

    class Settings:
        name = "proxy_tunnel_config"
