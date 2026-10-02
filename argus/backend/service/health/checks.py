"""The checks for the Argus dependencies that qatools-health has no class for."""

import asyncio
import logging
from typing import Any, override

import boto3
import httpx
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError
from cassandra import ConsistencyLevel, DriverException, OperationTimedOut, ReadTimeout
from cassandra.cluster import NoHostAvailable
from cassandra.cqlengine import CQLEngineException, connection
from cassandra.policies import HostDistance
from cassandra.query import SimpleStatement
from coodie.exceptions import CoodieError
from qatools_health import HealthCheck, HealthCheckResult, Severity
from qatools_health.checks import HttpHealthCheck

from argus.backend.db import ScyllaCluster, await_all_pages
from argus.backend.service.tunnel_service import TunnelService

LOGGER = logging.getLogger(__name__)

SENTINEL_FINGERPRINT = "SHA256:" + "A" * 43
NGINX_PROBE_URL = "http://127.0.0.1/s/argus.png"
S3_CONNECT_TIMEOUT = 3
S3_READ_TIMEOUT = 5
DATABASE_ERRORS = (DriverException, NoHostAvailable, CQLEngineException, CoodieError)


def describe_database_error(check_name: str, error: Exception) -> HealthCheckResult:
    LOGGER.warning("%s probe failed: %r", check_name, error)
    if isinstance(error, NoHostAvailable):
        return HealthCheckResult.unhealthy("no ScyllaDB host answered")
    if isinstance(error, (OperationTimedOut, ReadTimeout)):
        return HealthCheckResult.unhealthy("the ScyllaDB read timed out")
    return HealthCheckResult.unhealthy(f"the ScyllaDB read failed with {type(error).__name__}")


class ArgusDatabase:
    """The ScyllaDB session of the health process, opened on first use.

    The cluster opens in a thread on the first probe, so a ScyllaDB outage at
    start gives an UNHEALTHY check instead of a process that fails to start.
    One open runs at a time. A caller that the runner cancels at the check
    timeout leaves the open running, and the next caller awaits the same open,
    so two threads never set up the cluster together. A failed open leaves no
    session, and the next probe tries again.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self._session = None
        self._opening: asyncio.Future | None = None

    async def session(self):
        """Return the open session, and open the cluster when it is not open yet."""
        if self._session is not None:
            return self._session
        if self._opening is None:
            self._opening = asyncio.ensure_future(asyncio.to_thread(self._open))
            self._opening.add_done_callback(_retrieve_error)
        opening = self._opening
        try:
            self._session = await asyncio.shield(opening)
        finally:
            if opening.done() and self._opening is opening:
                self._opening = None
        return self._session

    def _open(self):
        ScyllaCluster.get(self.config)
        return connection.get_session(connection="default")


def _retrieve_error(future: asyncio.Future) -> None:
    if not future.cancelled():
        future.exception()


class ScyllaHealthCheck(HealthCheck):
    """ScyllaDB answers a local read through the Argus cluster configuration.

    The read goes to one coordinator at LOCAL_ONE, so a single live host is
    enough to pass. The check reports DEGRADED when the read answers and the
    driver sees some hosts down. A host that the load balancing policy ignores,
    such as a node outside SCYLLA_CONTACT_POINTS, is never tracked, so it does
    not count.
    """

    name = "scylla"
    severity = Severity.CRITICAL
    query = "SELECT release_version FROM system.local"

    def __init__(self, database: ArgusDatabase, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.database = database

    @override
    async def perform_check(self) -> HealthCheckResult:
        """Run the read, then count the hosts the driver sees up."""
        try:
            session = await self.database.session()
            statement = SimpleStatement(self.query, consistency_level=ConsistencyLevel.LOCAL_ONE)
            await await_all_pages(session.execute_async(statement, timeout=self.timeout))
        except DATABASE_ERRORS as exc:
            return describe_database_error(self.name, exc)
        profiles = session.cluster.profile_manager
        hosts = [
            host for host in session.cluster.metadata.all_hosts() if profiles.distance(host) != HostDistance.IGNORED
        ]
        up = sum(1 for host in hosts if host.is_up)
        if up < len(hosts):
            return HealthCheckResult.degraded(f"{up} of {len(hosts)} hosts up")
        return HealthCheckResult.healthy(f"{up} of {len(hosts)} hosts up")


class NginxHealthCheck(HttpHealthCheck):
    name = "nginx"
    severity = Severity.IMPORTANT
    interval = 60.0

    def __init__(self, url: str = NGINX_PROBE_URL, **kwargs: Any) -> None:
        super().__init__(url, **kwargs)

    @override
    def build_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=self.timeout, follow_redirects=False, trust_env=False)


class SshKeyLookupHealthCheck(HealthCheck):
    """The authorized keys lookup that sshd on every tunnel proxy depends on.

    The check calls the service method the keys route calls, with a
    well-formed fingerprint that matches no key. An empty answer is HEALTHY.
    """

    name = "ssh_key_lookup"
    interval = 120.0

    def __init__(self, database: ArgusDatabase, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.database = database

    @override
    async def perform_check(self) -> HealthCheckResult:
        """Open the database, then look up the sentinel fingerprint."""
        try:
            await self.database.session()
            await TunnelService().get_authorized_keys(SENTINEL_FINGERPRINT)
        except DATABASE_ERRORS as exc:
            return describe_database_error(self.name, exc)
        return HealthCheckResult.healthy("the lookup answered")


class S3BucketHealthCheck(HealthCheck):
    """One S3 bucket exists and the Argus credentials can reach it."""

    name = "s3"

    def __init__(
        self,
        bucket: str,
        *,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        client: Any = None,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("name", f"s3:{bucket}")
        super().__init__(**kwargs)
        self.bucket = bucket
        self.credential = (access_key_id, secret_access_key)
        self._client = client

    def _s3(self):
        if self._client is None:
            self._client = boto3.client(
                "s3",
                aws_access_key_id=self.credential[0],
                aws_secret_access_key=self.credential[1],
                config=BotoConfig(
                    connect_timeout=S3_CONNECT_TIMEOUT,
                    read_timeout=S3_READ_TIMEOUT,
                    retries={"mode": "standard", "total_max_attempts": 1},
                ),
            )
        return self._client

    def _head_bucket(self) -> None:
        self._s3().head_bucket(Bucket=self.bucket)

    @override
    async def perform_check(self) -> HealthCheckResult:
        """Send HeadBucket in a thread and grade the answer."""
        try:
            await asyncio.to_thread(self._head_bucket)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "unknown")
            return HealthCheckResult.unhealthy(f"HeadBucket {self.bucket} answered {code}")
        return HealthCheckResult.healthy(f"HeadBucket {self.bucket} answered")
