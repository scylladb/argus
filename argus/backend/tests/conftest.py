import os
import time
import uuid
from unittest.mock import patch

from cassandra.auth import PlainTextAuthProvider
from docker import DockerClient
from flask import g, Flask
from flask.testing import FlaskClient

from argus.backend.plugins.loader import all_plugin_types
from argus.backend.plugins.sct.service import SCTService
from argus.backend.service.testrun import TestRunService
from argus.backend.service.views_widgets.pytest import PytestViewService
from argus.backend.util.config import Config

os.environ['DOCKER_HOST'] = ""

from cassandra.cqlengine.management import sync_type
from _pytest.fixtures import fixture
from docker.errors import NotFound
from argus.backend.cli import sync_models
from argus.backend.db import ScyllaCluster
from argus.backend.models.web import ArgusTest, ArgusGroup, ArgusRelease, User, UserRoles
from argus.backend.plugins.sct.testrun import SCTTestRunSubmissionRequest
from argus.backend.service.client_service import ClientService
from argus.backend.service.release_manager import ReleaseManagerService
from argus.backend.service.results_service import ResultsService
import logging
from cassandra.cluster import Cluster

logging.getLogger().setLevel(logging.INFO)
os.environ['CQLENG_ALLOW_SCHEMA_MANAGEMENT'] = '1'
logging.getLogger('cassandra').setLevel(logging.WARNING)
logging.getLogger('cassandra.connection').setLevel(logging.WARNING)
logging.getLogger('cassandra.pool').setLevel(logging.WARNING)
logging.getLogger('cassandra.cluster').setLevel(logging.WARNING)


@fixture(scope='session')
def argus_db():
    container_name = "argus_test_scylla"
    docker_client = DockerClient.from_env()
    need_sync_models = True
    try:
        container = docker_client.containers.get(container_name)
        if container.status != 'running':
            container.start()
            print(f"Started existing container '{container_name}'.")
        else:
            print(f"Using already running container '{container_name}'.")
        need_sync_models = False
    except NotFound:
        container = docker_client.containers.run(
            "scylladb/scylla:2025.4.0-rc3",
            name=container_name,
            detach=True,
            ports={'9042/tcp': 9042},
            command=[
                "--smp", "1",
                "--overprovisioned", "1",
                "--skip-wait-for-gossip-to-settle", "0",
                "--endpoint-snitch=SimpleSnitch",
                "--authenticator", "PasswordAuthenticator",
            ],
        )
        log_wait_timeout = 120
        start_time = time.time()

        print("Waiting for 'init - serving' message in container logs...")
        for log in container.logs(stream=True):
            log_line = log.decode('utf-8')
            if "init - serving" in log_line:
                print("'init - serving' message found.")
                break
            if "FATAL state" in log_line:
                raise Exception("ScyllaDB exited unexpectedly. Check container logs for more information.")
            if time.time() - start_time > log_wait_timeout:
                raise Exception("ScyllaDB did not log 'init - serving' within the timeout period.")

    container.reload()
    container_ip = container.attrs['NetworkSettings']['Networks']['bridge']['IPAddress']
    print(f"Container IP: {container_ip}")

    if need_sync_models:
        auth_provider = PlainTextAuthProvider(username='cassandra', password='cassandra')
        cluster = Cluster([container_ip], port=9042, auth_provider=auth_provider)  # Use container IP
        session = cluster.connect()
        session.execute("""
             CREATE KEYSPACE IF NOT EXISTS test_argus
             WITH replication = {'class': 'SimpleStrategy', 'replication_factor' : 1};
         """)
    config = {"SCYLLA_KEYSPACE_NAME": "test_argus", "SCYLLA_CONTACT_POINTS": [container_ip],
              "SCYLLA_USERNAME": "cassandra", "SCYLLA_PASSWORD": "cassandra", "APP_LOG_LEVEL": "INFO",
              "EMAIL_SENDER": "unit tester", "EMAIL_SENDER_PASS": "pass", "EMAIL_SENDER_USER": "qa",
              "EMAIL_SERVER": "fake", "EMAIL_SERVER_PORT": 25}
    Config.CONFIG = config  # patch config for whole test to avoid using Config.load_yaml_config() required by app context
    database = ScyllaCluster.get(config)
    if need_sync_models:
        for user_type in all_plugin_types():
            sync_type(ks_name="test_argus", type_model=user_type)
        sync_models()

    yield database
    database.shutdown()


@fixture(scope='session')
def argus_app():
    with patch('argus.backend.service.user.load_logged_in_user') as mock_load:
        mock_load.return_value = None  # Make the function do nothing so test can override user
        from argus_backend import argus_app
        yield argus_app


@fixture(scope='session', autouse=True)
def app_context(argus_db, argus_app):
    with argus_app.app_context():
        g.user = User(id=uuid.uuid4(), username='test_user', full_name='Test User',
                      email="tester@scylladb.com",
                      roles=[UserRoles.User, UserRoles.Admin, UserRoles.Manager])
        yield


@fixture(scope='session')
def flask_client(argus_app: Flask) -> FlaskClient:
    return argus_app.test_client()


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


def get_fake_test_run(
        test: ArgusTest,
        schema_version: str = "1.0.0",
        job_url: str = "http://example.com",
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
def release(release_manager_service) -> ArgusRelease:
    name = f"best_results_{time.time_ns()}"
    return release_manager_service.create_release(name, name, False)


@fixture(scope='session')
def group(release_manager_service, release) -> ArgusGroup:
    name = f"br_group{time.time_ns()}"
    return release_manager_service.create_group(name, name, build_system_id=release.name, release_id=str(release.id))


@fixture
def fake_test(release_manager_service, group: ArgusGroup, release: ArgusRelease) -> ArgusTest:
    name = f"test_{time.time_ns()}"
    return release_manager_service.create_test(name, name, name, name,
                                               group_id=str(group.id), release_id=str(release.id), plugin_name='scylla-cluster-tests')
