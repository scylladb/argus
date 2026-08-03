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


class SSHTunnelKeyByFingerprint(Model):
    """
    Fingerprint-keyed view of :class:`SSHTunnelKey`, read by the proxy host on
    every SSH authentication attempt.

    A secondary index propagates asynchronously, so a client that registers a
    key and connects immediately can be denied while the index catches up. This
    is a plain table on the same write path as the key itself, so the QUORUM
    read that follows a QUORUM write always sees the row.

    ``key_id`` clusters the partition. Two users cannot hold the same key
    without also holding the same private key, but a duplicate fingerprint must
    add a row instead of overwriting one.
    """

    fingerprint = columns.Text(partition_key=True)
    key_id = columns.UUID(primary_key=True, default=uuid4)
    user_id = columns.UUID(required=True)
    tunnel_id = columns.UUID(required=True)
    public_key = columns.Text(required=True)
    created_at = columns.DateTime(required=True, default=_utcnow_naive)
    expires_at = columns.DateTime(required=True)


class ProxyTunnelConfig(Model):
    """
    Stores the configuration of an SSH proxy tunnel server.

    Multiple configs can be active at the same time. A client receives every
    active config, ordered by a stable rotation keyed on its user, and fails
    over down the list when its primary proxy is unreachable.

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
