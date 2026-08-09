from datetime import UTC, datetime
from uuid import uuid4

from cassandra.cluster import Session
from cassandra.cqlengine import columns
from cassandra.cqlengine.models import Model

SSH_TUNNEL_KEY_BY_FINGERPRINT_VIEW = "ssh_tunnel_key_by_fingerprint"


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

    @classmethod
    def _sync_additional_rules(cls, session: Session):
        # public_key is selected into the view, so the proxy host reads one
        # partition. A secondary index would add a second hop to the base table.
        session.execute(
            f"CREATE MATERIALIZED VIEW IF NOT EXISTS {SSH_TUNNEL_KEY_BY_FINGERPRINT_VIEW} AS "
            f"SELECT id, user_id, tunnel_id, public_key, fingerprint, created_at, expires_at "
            f"FROM {cls.column_family_name(include_keyspace=False)} "
            f"WHERE fingerprint IS NOT NULL AND id IS NOT NULL "
            f"PRIMARY KEY (fingerprint, id)"
        )


class SSHTunnelKeyByFingerprint(Model):
    """
    Read-only handle on the ``ssh_tunnel_key_by_fingerprint`` materialized view,
    queried by the proxy host on every SSH authentication attempt.

    ScyllaDB maintains the view from :class:`SSHTunnelKey`, TTL included, so
    nothing writes here. The class is deliberately absent from ``USED_MODELS``:
    ``sync_table`` would create a plain table and shadow the view.
    """

    __table_name__ = SSH_TUNNEL_KEY_BY_FINGERPRINT_VIEW

    fingerprint = columns.Text(partition_key=True)
    id = columns.UUID(primary_key=True)
    user_id = columns.UUID()
    tunnel_id = columns.UUID()
    public_key = columns.Text()
    created_at = columns.DateTime()
    expires_at = columns.DateTime()


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
