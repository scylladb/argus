from datetime import UTC, datetime
from uuid import uuid4

from cassandra.cqlengine import columns
from cassandra.cqlengine.models import Model


def _utcnow_naive() -> datetime:
    return datetime.now(tz=UTC).replace(tzinfo=None)


class SSHTunnelKey(Model):
    """
    Stores a client-registered SSH public key for a specific (user, tunnel) pair.

    Rows are inserted with a ScyllaDB TTL (default 24 h). The ``expires_at``
    field is informational — it mirrors the TTL so the client knows when to
    re-register. Actual expiry is handled automatically by ScyllaDB.
    """

    id = columns.UUID(primary_key=True, default=uuid4)
    user_id = columns.UUID(required=True, index=True)
    tunnel_id = columns.UUID(required=True, index=True)
    public_key = columns.Text(required=True)
    fingerprint = columns.Text(required=True)
    created_at = columns.DateTime(required=True, default=_utcnow_naive)
    expires_at = columns.DateTime(required=True)


class ProxyTunnelConfig(Model):
    """
    Stores the configuration of an SSH proxy tunnel server.

    Multiple configs can be active at the same time. Active configs are used
    for tunnel connection selection via round-robin.

    A dedicated Argus service user (``service_user_id``) is created per
    proxy host so the proxy host can call the authorised-keys API with its
    own isolated credentials.
    """

    id = columns.UUID(primary_key=True, default=uuid4)
    host = columns.Text(required=True)
    port = columns.Integer(required=True)
    proxy_user = columns.Text(required=True)
    target_host = columns.Text(required=True)
    target_port = columns.Integer(required=True)
    host_key_fingerprint = columns.Text(required=True)
    service_user_id = columns.UUID()
    is_active = columns.Boolean(default=True)
