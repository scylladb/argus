import asyncio
from cassandra.cluster import Cluster
import json
import logging
from datetime import UTC, datetime
from argus.backend.service.results_service import ResultsService
from argus.backend.service.release_manager import ReleaseManagerService
from argus.backend.service.client_service import ClientService
from argus.backend.plugins.sct.testrun import SCTTestRunSubmissionRequest
from argus.backend.models.web import ArgusTest, ArgusGroup, ArgusRelease, User, UserRoles
from argus.backend.db import ScyllaCluster
from argus.backend.cli import sync_models
from base64 import b64decode, b64encode
from docker.errors import NotFound
from _pytest.fixtures import fixture
from fastapi import Request as FastAPIRequest
from itsdangerous import TimestampSigner
from starlette.testclient import TestClient
import os
from pathlib import Path
import re
import socket
import subprocess
import time
import uuid
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

from cassandra.auth import PlainTextAuthProvider
from docker import DockerClient
from docker.models.containers import Container
import pytest

from argus.backend.plugins.loader import all_plugin_models, all_plugin_types
from argus.backend.plugins.sct.service import SCTService
from argus.backend.service import test_lookup as lookup
from argus.backend.service.issue_service import IssueService
from argus.backend.service.jenkins_service import JenkinsService
from argus.backend.service.testrun import TestRunService
from argus.backend.service.views_widgets.pytest import PytestViewService
from argus.backend.service.user import load_user
from argus.backend.util.config import Config


os.environ['DOCKER_HOST'] = ""
logging.getLogger().setLevel(logging.INFO)
os.environ['CQLENG_ALLOW_SCHEMA_MANAGEMENT'] = '1'
logging.getLogger('cassandra').setLevel(logging.WARNING)
logging.getLogger('cassandra.connection').setLevel(logging.WARNING)
logging.getLogger('cassandra.pool').setLevel(logging.WARNING)
logging.getLogger('cassandra.cluster').setLevel(logging.WARNING)

LOGGER = logging.getLogger(__name__)


TEST_PORTS = (9042, 19042, 7000, 7001, 9001, 9180, 10000, 6080)
CLAIM_PORT = 9099

SUPERVISORD_CONF = """[supervisord]
nodaemon=true
logfile=/dev/stdout
logfile_maxbytes=0
pidfile=/var/tmp/supervisord.pid

[inet_http_server]
port = {address}:9001

[rpcinterface:supervisor]
supervisor.rpcinterface_factory = supervisor.rpcinterface:make_main_rpcinterface

[supervisorctl]

[include]
files = /etc/supervisord.conf.d/scylla-server.conf
"""


def bound_socket(address: str, port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((address, port))
    except OSError as error:
        sock.close()
        raise OSError(f"{address}:{port} is busy") from error
    return sock


def claim_loopback_address() -> tuple[str, socket.socket]:
    """The first 127.0.1.0/24 address with every test port free, and the socket that holds its claim port."""
    busy = ""
    for host in range(1, 255):
        address = f"127.0.1.{host}"
        sockets = []
        try:
            for port in (CLAIM_PORT, *TEST_PORTS):
                sockets.append(bound_socket(address, port))
        except OSError as error:
            busy = str(error)
            for sock in sockets:
                sock.close()
            continue
        claim, *probes = sockets
        claim.listen()
        for sock in probes:
            sock.close()
        return address, claim
    raise RuntimeError(f"No address in 127.0.1.0/24 has the test ports {TEST_PORTS} free; {busy}")


def current_ref() -> str:
    """The checked-out branch, or the short commit id of a detached HEAD."""
    for args in (("git", "rev-parse", "--abbrev-ref", "HEAD"), ("git", "rev-parse", "--short", "HEAD")):
        try:
            ref = subprocess.run(args, capture_output=True, text=True, check=False, cwd=Path(__file__).parent).stdout
        except OSError:
            return "detached"
        if ref.strip() and ref.strip() != "HEAD":
            return ref.strip()
    return "detached"


@fixture(scope='session')
def argus_db(request, tmp_path_factory):
    address, claim = claim_loopback_address()
    request.addfinalizer(claim.close)
    suffix = re.sub(r"[^A-Za-z0-9_.-]", "_", f"{current_ref()}_{address}")
    supervisord_conf = tmp_path_factory.mktemp("supervisord") / "supervisord.conf"
    supervisord_conf.write_text(SUPERVISORD_CONF.format(address=address))
    CONTAINERS = {
        "database": {
            "image": "scylladb/scylla:2026.3.3",
            "name": f"argus_test_scylla_{suffix}",
            "detach": True,
            "network_mode": "host",
            "command": [
                "--listen-address", address,
                "--rpc-address", address,
                "--api-address", address,
                "--prometheus-address", address,
                "--smp", "1",
                "--overprovisioned", "1",
                "--rf-rack-valid-keyspaces", "1",
                "--skip-wait-for-gossip-to-settle", "0",
                "--endpoint-snitch=SimpleSnitch",
                "--authenticator", "PasswordAuthenticator",
                "--auth-superuser-name", "cassandra",
                "--auth-superuser-salted-password",
                r"\$6\$argusdev\$QoXJxKv2KybwyGg1hvwCCn00nZdHk7lv9HcpZWgrwdNQEKg70jegeVmMSkUqTngHVD4iNnLIFBkYMED/6/CCT1",
                "--vector-store-primary-uri", f"http://{address}:6080",
            ],
            "volumes": {
                str(supervisord_conf): {
                    "bind": "/etc/supervisord.conf",
                    "mode": "ro",
                },
            },
        },
        "vs": {
            "image": "scylladb/vector-store:1.13.0",
            "name": f"vector-search_test_{suffix}",
            "detach": True,
            "network_mode": "host",
            "environment": {
                "VECTOR_STORE_URI": f"{address}:6080",
                "VECTOR_STORE_SCYLLADB_URI": f"{address}:9042",
                "VECTOR_STORE_THREADS": "4",
                "VECTOR_STORE_SCYLLADB_USERNAME": "cassandra",
                "VECTOR_STORE_SCYLLADB_PASSWORD_FILE": "/var/lib/vector-store/db_password",
            },
            "volumes": {
                Path("./argus/backend/tests/vs").absolute(): {
                    "bind": "/var/lib/vector-store",
                    "mode": "rw",
                },
            }
        }
    }

    docker_client = DockerClient.from_env()
    need_sync_models = True
    containers: dict[str, Container] = {}
    for name, params in CONTAINERS.items():
        try:
            container = docker_client.containers.get(params["name"])
            container.remove(force=True)
        except NotFound:
            pass

    for name, params in CONTAINERS.items():
        container = docker_client.containers.run(**params)
        containers[name] = container
        request.addfinalizer(lambda container=container: container.remove(force=True))
    log_wait_timeout = 120
    start_time = time.time()

    print("Waiting for 'init - serving' message in container logs...")
    for log in containers["database"].logs(stream=True):
        log_line = log.decode('utf-8')
        if "init - serving" in log_line:
            print("'init - serving' message found.")
            break
        if "FATAL state" in log_line:
            raise Exception(
                "ScyllaDB exited unexpectedly. Check container logs for more information.")
        if time.time() - start_time > log_wait_timeout:
            raise Exception(
                "ScyllaDB did not log 'init - serving' within the timeout period.")

    containers["database"].reload()
    container_ip = address
    print(f"Container IP: {container_ip}")

    if need_sync_models:
        auth_provider = PlainTextAuthProvider(
            username='cassandra', password='cassandra')
        cluster = Cluster([container_ip], port=9042,
                          auth_provider=auth_provider)  # Use container IP
        session = cluster.connect()
        session.execute("""
             CREATE KEYSPACE IF NOT EXISTS test_argus
             WITH replication = {'class': 'NetworkTopologyStrategy', 'replication_factor' : 1};
         """)
        session.execute("""
             CREATE KEYSPACE IF NOT EXISTS argus_tablets
             WITH replication = {'class': 'NetworkTopologyStrategy', 'replication_factor' : 1} AND tablets = {'enabled': true};
         """)
    config = {"SCYLLA_KEYSPACE_NAME": "test_argus", "SCYLLA_CONTACT_POINTS": [container_ip],
              "SCYLLA_USERNAME": "cassandra", "SCYLLA_PASSWORD": "cassandra", "APP_LOG_LEVEL": "INFO",
              "EMAIL_ENABLED": False,
              "JIRA_SERVER": "https://zxqtesting.atlassian.net",
              "EMAIL_SENDER": "unit tester", "EMAIL_SENDER_PASS": "pass", "EMAIL_SENDER_USER": "qa",
              "EMAIL_SERVER": "fake", "EMAIL_SERVER_PORT": 25,
              "GITHUB_ACCESS_TOKEN": "test_token",
              "SECRET_KEY": "test-secret-key",
              # External-service config keys: set so service constructors don't crash
              # in tests. Real network calls are blocked by per-test mocks (see
              # argus/backend/tests/_helpers/external_mocks.py).
              "LOGIN_METHODS": ["password", "gh", "cf"],
              "GITHUB_CLIENT_ID": "test_gh_client_id",
              "GITHUB_CLIENT_SECRET": "test_gh_client_secret",
              "JIRA_EMAIL": "tester@scylladb.com",
              "JIRA_TOKEN": "test_jira_token",
              "JENKINS_URL": "http://jenkins.test",
              "JENKINS_USER": "tester",
              "JENKINS_API_TOKEN": "test_jenkins_token",
              "AWS_CLIENT_ID": "test_aws_id",
              "AWS_CLIENT_SECRET": "test_aws_secret",
              "S3_ALLOWED_BUCKETS": ["test-bucket"],
              "S3_ALLOWED_MIME": ["image/png", "image/jpeg", "text/plain"],
              "CLOUDFLARE_ACCESS_TEAM_DOMAIN": "scylladb.cloudflareaccess.com",
              "CLOUDFLARE_ACCESS_AUD": "test-aud",
              # Stub PyJWKClient so _get_cf_access_payload doesn't fetch JWKS over HTTP.
              "CLOUDFLARE_ACCESS_JWK_CLIENT": SimpleNamespace(
                  get_signing_key_from_jwt=lambda token: SimpleNamespace(
                      key="test-key")
    )}
    # patch config for whole test to avoid using Config.load_yaml_config() required by app context
    Config.CONFIG = config
    database = ScyllaCluster.get(config)
    if need_sync_models:
        asyncio.run(sync_models("test_argus"))
    # Wait a little to let CDC Reader and full scan of Vector Store indices to complete.
    LOGGER.info("Waiting on Vector Store to be ready...")
    ks_name = "argus_tablets"
    vs_indices = [r["name"] for r in database.session.execute(f"DESCRIBE {ks_name}").all(
    ) if r["type"] == "index" and "vector_index" in r["create_statement"]]
    for index_name in vs_indices:
        for log in containers["vs"].logs(stream=True):
            log_line = log.decode('utf-8')
            if f"finished full scan on {ks_name}.{index_name}" in log_line:
                break
            if time.time() - start_time > log_wait_timeout:
                raise Exception("FATAL - Vector search did not build indices.")
        LOGGER.info("Vector Index %s - Ready.", index_name)

    yield database
    database.shutdown()


@fixture(scope='session')
def asgi_app(argus_db):
    """The FastAPI app, built once for the whole session."""
    import argus_backend
    yield argus_backend.create_app()


@fixture(scope='session')
def logged_in_user() -> User:
    return User(id=uuid.uuid4(), username='test_user', full_name='Test User',
                email="tester@scylladb.com", password="", registration_date=datetime.now(UTC),
                roles=[UserRoles.User, UserRoles.Admin, UserRoles.Manager])


class _RequestContextShim:
    """Stand-in for the removed flask.g: tests keep referring to ``g.user``
    for the shared logged-in test user."""
    user: User | None = None


g = _RequestContextShim()


@fixture(scope='session', autouse=True)
def test_user_context(argus_db, logged_in_user):
    g.user = logged_in_user
    yield


@fixture(autouse=True)
def _clear_search_index():
    lookup.TestLookup.clear_index()


@fixture(scope='session')
def app_config(asgi_app) -> dict:
    """The live config mapping the controllers read (request.app.state.config)."""
    return asgi_app.state.config


@fixture(scope='session')
def api_client(asgi_app, logged_in_user):
    """TestClient over the app, logged in as logged_in_user through the
    load_user dependency override."""
    def _logged_in_user_override(request: FastAPIRequest) -> User:
        request.state.user = logged_in_user
        return logged_in_user

    asgi_app.dependency_overrides[load_user] = _logged_in_user_override
    yield TestClient(asgi_app, raise_server_exceptions=False)
    asgi_app.dependency_overrides.pop(load_user, None)


@fixture
def anon_client(asgi_app):
    """TestClient without dependency overrides — exercises real auth.

    api_client's session-scoped load_user override lives on the shared app
    object, so it is stashed away for the duration of the test.
    """
    saved = dict(asgi_app.dependency_overrides)
    asgi_app.dependency_overrides.clear()
    yield TestClient(asgi_app, raise_server_exceptions=False)
    asgi_app.dependency_overrides.update(saved)


@fixture(scope='session')
def session_signer(asgi_app) -> TimestampSigner:
    """The session-cookie signer SessionMiddleware uses — mint and read
    session cookies for TestClient-based tests."""
    return TimestampSigner(str(asgi_app.state.config["SECRET_KEY"]))


@fixture
def make_session_cookie(session_signer):
    def make(**values) -> str:
        data = b64encode(json.dumps(values).encode("utf-8"))
        return session_signer.sign(data).decode("utf-8")
    return make


@fixture
def read_session(session_signer):
    def read(client) -> dict:
        jar_cookies = [c for c in client.cookies.jar if c.name == "session"]
        if not jar_cookies:
            return {}
        # prefer the host cookie the server set over a test-minted one
        cookie = next((c for c in jar_cookies if c.domain == "testserver"), jar_cookies[-1])
        return json.loads(b64decode(session_signer.unsign(cookie.value)))
    return read


@fixture(scope='session')
def release_manager_service(argus_db) -> ReleaseManagerService:
    return ReleaseManagerService()


@fixture(scope='session')
def client_service(argus_db):
    return ClientService()


@fixture(scope='session')
def pv_service(argus_db) -> PytestViewService:
    return PytestViewService()


@fixture(scope='session')
def sct_service(argus_db) -> SCTService:
    return SCTService()


@fixture(scope='session')
def testrun_service(argus_db) -> TestRunService:
    return TestRunService()


@fixture(scope='session')
def results_service(argus_db):
    return ResultsService()


@fixture(scope='session')
def issue_service(argus_db) -> IssueService:
    return IssueService(True)


def get_fake_test_run(
        test: ArgusTest,
        schema_version: str = "1.0.0",
        job_url: str = "http://example.com/job/42",
        started_by: str = "default_user",
        commit_id: str = "default_commit_id",
        sct_config: dict | None = None,
        origin_url: str | None = None,
        branch_name: str | None = "main",
        runner_public_ip: str | None = None,
        runner_private_ip: str | None = None
) -> tuple[str, SCTTestRunSubmissionRequest]:
    run_id = str(uuid.uuid4())
    return "scylla-cluster-tests", SCTTestRunSubmissionRequest(
        schema_version=schema_version,
        run_id=run_id,
        job_name=test.build_system_id,
        job_url=job_url,
        started_by=started_by,
        commit_id=commit_id,
        sct_config=sct_config,
        origin_url=origin_url,
        branch_name=branch_name,
        runner_public_ip=runner_public_ip,
        runner_private_ip=runner_private_ip
    )


@fixture(scope='session')
async def release(release_manager_service) -> ArgusRelease:
    name = f"best_results_{time.time_ns()}"
    return await release_manager_service.create_release(name, name, False)


@fixture(scope='session')
async def group(release_manager_service, release) -> ArgusGroup:
    name = f"br_group{time.time_ns()}"
    return await release_manager_service.create_group(name, name, build_system_id=release.name, release_id=release.id)


@fixture
async def fake_test(release_manager_service, group: ArgusGroup, release: ArgusRelease) -> ArgusTest:
    name = f"test_{time.time_ns()}"
    return await release_manager_service.create_test(name, name, name, name,
                                               group_id=group.id, release_id=release.id, plugin_name='scylla-cluster-tests')


# ---------------------------------------------------------------------------
# IssueService (covers PyGithub + Jira together)
# ---------------------------------------------------------------------------
# Patched at the controller import site so the underlying GithubService and
# JiraService constructors (and their HTTP clients) never run.


@pytest.fixture
def mock_issue_service():
    """Replace ``IssueService`` in controller modules with a MagicMock.

    Yields the patched class mock. ``mock.return_value`` is the per-call
    instance used by the controller; configure ``submit``/``get``/``delete``
    on ``mock.return_value`` as needed.
    """
    instance = MagicMock(spec=IssueService, name="IssueServiceInstance")
    # Sensible defaults so tests that don't customize still get JSON-serializable
    # responses.
    instance.submit.return_value = {
        "id": "00000000-0000-0000-0000-000000000000"}
    instance.submit_for_sct_event.return_value = {
        "id": "00000000-0000-0000-0000-000000000000"}
    instance.get.return_value = []
    instance.delete.return_value = True

    with patch("argus.backend.controller.testrun_api.IssueService", return_value=instance) as m:
        yield m


# ---------------------------------------------------------------------------
# UserService.github_callback  (OAuth login)
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_github_callback():
    """Patch ``UserService.github_callback`` to return canned ``first_run_info``.

    Default return is ``None`` (existing user, no first-run banner). Override
    via ``mock_github_callback.return_value = {...}``.
    """
    with patch("argus.backend.service.user.UserService.github_callback") as m:
        m.return_value = None
        yield m


# ---------------------------------------------------------------------------
# JenkinsService (testrun_api Jenkins routes + planner trigger)
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_jenkins_service():
    """Replace ``JenkinsService`` at every import site with a MagicMock.

    Default return values mirror the typical happy-path responses so tests can
    customize only the bits they care about.
    """
    instance = MagicMock(spec=JenkinsService, name="JenkinsServiceInstance")
    instance.retrieve_job_parameters.return_value = []
    instance.build_job.return_value = 12345  # queue item id
    instance.get_queue_info.return_value = {
        "why": None, "url": "http://jenkins.test/job/1/"}
    instance.latest_build.return_value = {"number": 1}
    instance.get_advanced_settings.return_value = {}
    instance.clone_job.return_value = "cloned/job/path"
    instance.verify_job_settings.return_value = True

    with (
        patch("argus.backend.controller.testrun_api.JenkinsService", return_value=instance) as m,
        patch("argus.backend.service.planner_service.JenkinsService", return_value=instance),
    ):
        yield m


# ---------------------------------------------------------------------------
# TestRunService S3 methods (log/screenshot proxies)
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_s3():
    """Patch ``TestRunService`` S3-touching methods to avoid real AWS calls.

    Returns a ``SimpleNamespace`` with attributes for each patched method so
    tests can inspect call arguments / customize return values.
    """
    with (
        patch("argus.backend.service.testrun.TestRunService.get_log") as get_log,
        patch("argus.backend.service.testrun.TestRunService.proxy_stored_s3_image") as proxy_img,
        patch("argus.backend.service.testrun.TestRunService.resolve_artifact_size") as resolve_size,
        patch("argus.backend.service.testrun.TestRunService.proxy_s3_file") as proxy_file,
    ):
        get_log.return_value = "https://test-bucket.s3.amazonaws.com/log/example.log?signed"
        proxy_img.return_value = "https://test-bucket.s3.amazonaws.com/screenshots/example.png?signed"
        resolve_size.return_value = 1024
        proxy_file.return_value = b"fake-s3-content"
        yield SimpleNamespace(
            get_log=get_log,
            proxy_stored_s3_image=proxy_img,
            resolve_artifact_size=resolve_size,
            proxy_s3_file=proxy_file,
        )


# ---------------------------------------------------------------------------
# Cloudflare Access JWT
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_cf_access_payload():
    """Patch ``_get_cf_access_payload`` to return a fabricated JWT payload.

    Default email is ``"tester@scylladb.com"`` (passes the @scylladb.com gate).
    Override via ``mock_cf_access_payload.return_value = {"email": "..."}``.
    """
    with patch("argus.backend.service.user._get_cf_access_payload") as m:
        m.return_value = {"email": "tester@scylladb.com"}
        yield m
