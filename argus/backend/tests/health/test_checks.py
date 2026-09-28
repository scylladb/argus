import asyncio
import threading
from types import SimpleNamespace

import boto3
from botocore.stub import Stubber
import pytest
from cassandra import InvalidRequest, OperationTimedOut
from cassandra.cluster import NoHostAvailable
from cassandra.cqlengine import connection
from cassandra.policies import HostDistance
from qatools_health import HealthCheckResult, HealthCheckStatus

from argus.backend.service.health.checks import (
    ArgusDatabase,
    NginxHealthCheck,
    S3BucketHealthCheck,
    ScyllaHealthCheck,
    SshKeyLookupHealthCheck,
)


class FakeResponseFuture:
    has_more_pages = False

    def __init__(self, rows=None, error=None):
        self.rows = rows
        self.error = error

    def add_callbacks(self, callback, errback):
        if self.error is not None:
            errback(self.error)
        else:
            callback(self.rows)


class FakeDatabase:
    def __init__(self, hosts_up, error=None, ignored=0):
        hosts = [SimpleNamespace(is_up=up, ignored=False) for up in hosts_up]
        hosts += [SimpleNamespace(is_up=None, ignored=True) for _ in range(ignored)]
        profiles = SimpleNamespace(
            distance=lambda host: HostDistance.IGNORED if host.ignored else HostDistance.LOCAL)
        self.fake_session = SimpleNamespace(
            execute_async=lambda statement, timeout=None: FakeResponseFuture(
                rows=[{"release_version": "2025.4.0"}], error=error),
            cluster=SimpleNamespace(metadata=SimpleNamespace(all_hosts=lambda: hosts), profile_manager=profiles),
        )

    async def session(self):
        return self.fake_session


class FailingDatabase:
    async def session(self):
        raise NoHostAvailable("Unable to connect to any servers", {"10.0.0.7:9042": ConnectionRefusedError(111)})


async def run(check) -> HealthCheckResult:
    result = await check.perform_check()
    if isinstance(result, HealthCheckResult):
        return result
    return HealthCheckResult.healthy() if result in (None, True) else HealthCheckResult.unhealthy(str(result))


async def test_scylla_healthy_against_the_test_cluster(argus_db):
    database = ArgusDatabase(argus_db.config)
    result = await run(ScyllaHealthCheck(database))
    assert result.status is HealthCheckStatus.HEALTHY
    assert "release_version" not in result.message


async def test_scylla_degraded_when_some_hosts_are_down():
    result = await run(ScyllaHealthCheck(FakeDatabase([True, False, True])))
    assert result.status is HealthCheckStatus.DEGRADED
    assert "2 of 3" in result.message


async def test_scylla_ignores_hosts_outside_the_contact_points():
    result = await run(ScyllaHealthCheck(FakeDatabase([True, True], ignored=3)))
    assert result.status is HealthCheckStatus.HEALTHY
    assert result.message == "2 of 2 hosts up"


async def test_database_opens_once_when_the_first_caller_is_cancelled():
    opened = []
    release = threading.Event()

    class SlowDatabase(ArgusDatabase):
        def _open(self):
            opened.append(threading.get_ident())
            release.wait(5)
            return "session"

    database = SlowDatabase({})
    first = asyncio.ensure_future(database.session())
    await asyncio.sleep(0.05)
    first.cancel()
    second = asyncio.ensure_future(database.session())
    await asyncio.sleep(0.05)
    release.set()
    assert await second == "session"
    assert len(opened) == 1


async def test_scylla_unhealthy_when_the_query_fails():
    database = FakeDatabase([True], error=InvalidRequest("read failed on 10.0.0.7"))
    result = await run(ScyllaHealthCheck(database))
    assert result.status is HealthCheckStatus.UNHEALTHY
    assert result.message == "the ScyllaDB read failed with InvalidRequest"


async def test_scylla_leaves_an_error_outside_the_driver_to_the_runner():
    database = FakeDatabase([True], error=RuntimeError("a bug in the check"))
    with pytest.raises(RuntimeError):
        await ScyllaHealthCheck(database).perform_check()


async def test_scylla_unhealthy_when_the_read_times_out():
    database = FakeDatabase([True], error=OperationTimedOut("10.0.0.7:9042 timed out"))
    result = await run(ScyllaHealthCheck(database))
    assert result.message == "the ScyllaDB read timed out"


async def test_scylla_names_no_host_when_the_cluster_does_not_open():
    result = await run(ScyllaHealthCheck(FailingDatabase()))
    assert result.status is HealthCheckStatus.UNHEALTHY
    assert result.message == "no ScyllaDB host answered"
    assert "10.0.0.7" not in result.message


async def test_ssh_key_lookup_names_no_host_when_the_cluster_does_not_open():
    result = await run(SshKeyLookupHealthCheck(FailingDatabase()))
    assert result.status is HealthCheckStatus.UNHEALTHY
    assert result.message == "no ScyllaDB host answered"


async def test_ssh_key_lookup_answers_healthy_for_the_sentinel(argus_db):
    database = ArgusDatabase(argus_db.config)
    result = await run(SshKeyLookupHealthCheck(database))
    assert result.status is HealthCheckStatus.HEALTHY


async def test_s3_bucket_healthy_on_head_bucket():
    client = boto3.client("s3", region_name="us-east-1", aws_access_key_id="id", aws_secret_access_key="secret")
    with Stubber(client) as stubber:
        stubber.add_response("head_bucket", {}, {"Bucket": "argus-logs"})
        check = S3BucketHealthCheck("argus-logs", client=client)
        assert check.name == "s3:argus-logs"
        assert (await run(check)).status is HealthCheckStatus.HEALTHY


async def test_s3_bucket_unhealthy_on_missing_bucket():
    client = boto3.client("s3", region_name="us-east-1", aws_access_key_id="id", aws_secret_access_key="secret")
    with Stubber(client) as stubber:
        stubber.add_client_error("head_bucket", service_error_code="404", http_status_code=404)
        result = await run(S3BucketHealthCheck("argus-logs", client=client))
    assert result.status is HealthCheckStatus.UNHEALTHY
    assert "404" in result.message


async def test_s3_client_makes_one_attempt_inside_the_check_timeout():
    check = S3BucketHealthCheck("argus-logs", access_key_id="id", secret_access_key="secret")
    config = check._s3().meta.config
    assert config.retries == {"mode": "standard", "total_max_attempts": 1}
    assert config.connect_timeout + config.read_timeout < check.timeout


async def test_s3_buckets_with_other_names_are_other_checks():
    first = S3BucketHealthCheck("argus-logs", access_key_id="id", secret_access_key="secret")
    second = S3BucketHealthCheck("argus-images", access_key_id="id", secret_access_key="secret")
    assert first.identity() != second.identity()


async def test_nginx_probes_a_static_file():
    check = NginxHealthCheck()
    assert check.name == "nginx"
    assert check.url == "http://127.0.0.1/s/argus.png"


async def test_nginx_probes_the_configured_url():
    check = NginxHealthCheck("http://127.0.0.1:8000/s/argus.png")
    assert check.url == "http://127.0.0.1:8000/s/argus.png"


async def test_database_uses_the_cqlengine_session(argus_db):
    session = await ArgusDatabase(argus_db.config).session()
    assert session is connection.get_session(connection="default")


async def test_s3_client_is_built_off_the_event_loop():
    loop_thread = threading.get_ident()
    built_in = []

    class RecordingCheck(S3BucketHealthCheck):
        def _s3(self):
            built_in.append(threading.get_ident())
            return SimpleNamespace(head_bucket=lambda Bucket: {})

    result = await run(RecordingCheck("argus-logs"))
    assert result.status is HealthCheckStatus.HEALTHY
    assert built_in and loop_thread not in built_in
