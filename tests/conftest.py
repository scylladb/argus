from uuid import UUID
import logging
from time import sleep, time
from os import urandom
from random import choice
from subprocess import run
import pytest
import docker
import cassandra.cluster
from mocks.mock_cluster import MockCluster
from argus.db.testrun import TestRunInfo, TestDetails, TestResourcesSetup, TestLogs, TestResults, TestResources
from argus.db.interface import ArgusDatabase
from argus.db.config import Config
from argus.db.db_types import PackageVersion, NemesisRunInfo, EventsBySeverity, NodeDescription, TestStatus, \
    NemesisStatus, ColumnInfo, CollectionHint
from argus.db.cloud_types import AWSSetupDetails, CloudNodesInfo, CloudInstanceDetails, CloudResource, ResourceState, \
    BaseCloudSetupDetails

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="function")
def mock_cluster(monkeypatch):
    monkeypatch.setattr(cassandra.cluster, "Cluster", MockCluster)


@pytest.fixture(scope="function")
def argus_interface_default():
    database = ArgusDatabase.get()
    yield database
    database.destroy()


@pytest.fixture(scope="function")
def preset_test_resource_setup():
    sct_runner_info = CloudInstanceDetails(public_ip="1.1.1.1", region="us-east-1",
                                           provider="aws", private_ip="10.10.10.1", creation_time=7734)
    db_node = CloudNodesInfo(image_id="ami-abcdef99", instance_type="spot",
                             node_amount=6, post_behaviour="keep-on-failure")
    loader_node = CloudNodesInfo(image_id="ami-deadbeef", instance_type="spot",
                                 node_amount=2, post_behaviour="terminate")
    monitor_node = CloudNodesInfo(image_id="ami-abdcef60", instance_type="spot",
                                  node_amount=1, post_behaviour="keep-on-failure")

    aws_setup = AWSSetupDetails(db_node=db_node, loader_node=loader_node, monitor_node=monitor_node)

    setup = TestResourcesSetup(sct_runner_host=sct_runner_info, region_name=["us-east-1"],
                               cloud_setup=aws_setup)

    return setup


@pytest.fixture(scope="function")
def preset_test_resources_setup_schema():
    return {
        "sct_runner_host": ColumnInfo(name="sct_runner_host", type=CloudInstanceDetails, value=None, constraints=[]),
        "region_name": ColumnInfo(name="region_name", type=CollectionHint, value=CollectionHint(list[str]),
                                  constraints=[]),
        "cloud_setup": ColumnInfo(name="cloud_setup", type=BaseCloudSetupDetails, value=None, constraints=[]),
    }


@pytest.fixture(scope="function")
def preset_test_resources_setup_serialized():
    return {
        "sct_runner_host": {
            "public_ip": "1.1.1.1",
            "region": "us-east-1",
            "provider": "aws",
            "private_ip": "10.10.10.1",
            "creation_time": 7734,
            "termination_time": 0,
            "termination_reason": "",
            "shards_amount": 0,

        },
        "region_name": ["us-east-1"],
        "cloud_setup": {
            "backend": "aws",
            "db_node": {
                "image_id": "ami-abcdef99",
                "instance_type": "spot",
                "node_amount": 6,
                "post_behaviour": "keep-on-failure",
            },
            "loader_node": {
                "image_id": "ami-deadbeef",
                "instance_type": "spot",
                "node_amount": 2,
                "post_behaviour": "terminate",
            },
            "monitor_node": {
                "image_id": "ami-abdcef60",
                "instance_type": "spot",
                "node_amount": 1,
                "post_behaviour": "keep-on-failure",
            },
        }
    }


@pytest.fixture(scope="function")
def preset_test_details():
    details = TestDetails(name="some-test", scm_revision_id="abcde", started_by="someone",
                          build_job_name="some-test-job",
                          build_job_url="https://job.tld/1", start_time=1600000000, yaml_test_duration=120,
                          config_files=["some-test.yaml"],
                          packages=[PackageVersion(name="package-server", version="1.0", date="2021-10-01",
                                                   revision_id="dfcedb3", build_id="dfeeeffffff330fddd")])
    return details


@pytest.fixture(scope="function")
def preset_test_details_schema():
    return {
        "name": ColumnInfo(name="name", type=str, value=None, constraints=[]),
        "scm_revision_id": ColumnInfo(name="scm_revision_id", type=str, value=None, constraints=[]),
        "started_by": ColumnInfo(name="started_by", type=str, value=None, constraints=[]),
        "build_job_name": ColumnInfo(name="build_job_name", type=str, value=None, constraints=[]),
        "build_job_url": ColumnInfo(name="build_job_url", type=str, value=None, constraints=[]),
        "start_time": ColumnInfo(name="start_time", type=int, value=None, constraints=[]),
        "yaml_test_duration": ColumnInfo(name="yaml_test_duration", type=int, value=None, constraints=[]),
        "config_files": ColumnInfo(name="config_files", type=CollectionHint, value=CollectionHint(list[str]),
                                   constraints=[]),
        "packages": ColumnInfo(name="packages", type=CollectionHint, value=CollectionHint(list[PackageVersion]),
                               constraints=[]),
        "end_time": ColumnInfo(name="end_time", type=int, value=None, constraints=[])
    }


@pytest.fixture(scope="function")
def preset_test_details_serialized():
    return {
        "name": "some-test",
        "scm_revision_id": "abcde",
        "started_by": "someone",
        "build_job_name": "some-test-job",
        "build_job_url": "https://job.tld/1",
        "start_time": 1600000000,
        "yaml_test_duration": 120,
        "config_files": ["some-test.yaml"],
        "packages": [{
            "name": "package-server",
            "version": "1.0",
            "date": "2021-10-01",
            "revision_id": "dfcedb3",
            "build_id": "dfeeeffffff330fddd",
        }],
        "end_time": -1,
    }


@pytest.fixture(scope="function")
def preset_test_logs():
    logs = TestLogs()
    logs.add_log(log_type="example", log_url="http://example.com")

    return logs


@pytest.fixture(scope="function")
def preset_test_logs_schema():
    return {
        "logs": ColumnInfo(name="logs", type=CollectionHint, value=CollectionHint(list[tuple[str, str]]),
                           constraints=[])
    }


@pytest.fixture(scope="function")
def preset_test_logs_serialized():
    return {
        "logs": [("example", "http://example.com")]
    }


@pytest.fixture(scope="function")
def preset_test_resources():
    resources = TestResources()

    instance_info = CloudInstanceDetails(public_ip="1.1.1.1", region="us-east-1",
                                         provider="aws", private_ip="10.10.10.1", creation_time=7734, shards_amount=10)
    resource = CloudResource(name="example_resource", state=ResourceState.RUNNING, instance_info=instance_info)

    resources.attach_resource(resource)

    return resources


@pytest.fixture(scope="function")
def preset_test_resources_schema():
    return {
        "allocated_resources": ColumnInfo(name="allocated_resources", type=CollectionHint,
                                          value=CollectionHint(list[CloudResource]), constraints=[]),
        "leftover_resources": ColumnInfo(name="leftover_resources", type=CollectionHint,
                                         value=CollectionHint(list[CloudResource]), constraints=[]),
        "terminated_resources": ColumnInfo(name="terminated_resources", type=CollectionHint,
                                           value=CollectionHint(list[CloudResource]), constraints=[]),
    }


@pytest.fixture(scope="function")
def preset_test_resources_serialized():
    return {
        "allocated_resources": [{
            "name": "example_resource",
            "state": "running",
            "instance_info": {
                "public_ip": "1.1.1.1",
                "region": "us-east-1",
                "provider": "aws",
                "private_ip": "10.10.10.1",
                "creation_time": 7734,
                "termination_time": 0,
                "termination_reason": "",
                "shards_amount": 10,
            }
        }],
        "leftover_resources": [{
            "name": "example_resource",
            "state": "running",
            "instance_info": {
                "public_ip": "1.1.1.1",
                "private_ip": "10.10.10.1",
                "region": "us-east-1",
                "provider": "aws",
                "creation_time": 7734,
                "termination_time": 0,
                "termination_reason": "",
                "shards_amount": 10,
            }
        }],
        "terminated_resources": [],
    }


@pytest.fixture(scope="function")
def preset_test_results():
    results = TestResults(TestStatus.CREATED)

    node_description = NodeDescription(ip="1.1.1.1", shards=10, name="example_node")
    nemesis = NemesisRunInfo("Nemesis", "disrupt_everything", 100, target_node=node_description,
                             status=NemesisStatus.RUNNING,
                             start_time=16000)

    nemesis.complete("Something went wrong...")

    results.add_event(event_severity="ERROR", event_message="Something went wrong...")
    results.add_nemesis(nemesis=nemesis)
    results.status = TestStatus.FAILED
    return results


@pytest.fixture(scope="function")
def preset_test_results_schema():
    return {
        "status": ColumnInfo(name="status", type=str, value=None, constraints=[]),
        "events": ColumnInfo(name="events", type=CollectionHint, value=CollectionHint(list[EventsBySeverity]),
                             constraints=[]),
        "nemesis_data": ColumnInfo(name="nemesis_data", type=CollectionHint,
                                   value=CollectionHint(list[NemesisRunInfo]), constraints=[]),
    }


@pytest.fixture(scope="function")
def preset_test_results_serialized():
    return {
        "status": "failed",
        "events": [
            {
                "severity": "ERROR",
                "event_amount": 1,
                "last_events": ["Something went wrong..."]
            }
        ],
        "nemesis_data": [
            {
                "class_name": "Nemesis",
                "name": "disrupt_everything",
                "duration": 100,
                "target_node": {
                    "ip": "1.1.1.1",
                    "shards": 10,
                    "name": "example_node",
                },
                "status": "failed",
                "start_time": 16000,
                "end_time": 16001,
                "stack_trace": "Something went wrong..."
            }
        ]
    }


@pytest.fixture(scope="function")
def simple_primary_key():
    return {
        "$tablekeys$": {
            "id": (UUID, "partition")
        }
    }


@pytest.fixture(scope="function")
def completed_testrun(preset_test_resource_setup: TestResourcesSetup):  # pylint: disable=redefined-outer-name
    # pylint: disable=too-many-locals
    scylla_package = PackageVersion("scylla-db", "4.4", "20210901", "deadbeef")
    details = TestDetails(name="longevity-test-100gb-4h", scm_revision_id="773413dead", started_by="komachi",
                          build_job_name="komachi-longevity-test-100gb-4h",
                          build_job_url="https://notarealjob.url/jobs/komachi-longevity-test-100gb-4h",
                          start_time=int(time()), yaml_test_duration=240, config_files=["tests/config.yaml"],
                          packages=[scylla_package])
    setup = preset_test_resource_setup
    logs = TestLogs()
    logs.add_log(log_type="syslog", log_url="https://thisisdefinitelyans3bucket.com/logz-abcdef331.tar.gz")
    resources = TestResources()

    created_resources = []

    for requested_node in [setup.cloud_setup.db_node, setup.cloud_setup.loader_node, setup.cloud_setup.monitor_node]:
        for node_number in range(1, requested_node.node_amount + 1):
            entropy = urandom(4).hex(sep=":", bytes_per_sep=1).split(":")
            random_ip = ".".join([str(int(byte, 16)) for byte in entropy])
            instance_details = CloudInstanceDetails(public_ip=random_ip, provider="aws", region="us-east-1",
                                                    private_ip="10.10.10.1", shards_amount=8)
            resource = CloudResource(name=f"{details.name}_{requested_node.instance_type}_{node_number}",
                                     state=ResourceState.RUNNING.value, instance_info=instance_details)
            resources.attach_resource(resource)
            created_resources.append(resource)

    terminated = choice(created_resources)
    resources.detach_resource(terminated)

    nemeses_names = ["SisyphusMonkey", "ChaosMonkey", "NotVeryCoolMonkey"]
    nemesis_runs = []

    for _ in range(6):
        node = choice(resources.leftover_resources)
        node_description = NodeDescription(name=node.name, ip=node.instance_info.public_ip, shards=10)
        nemesis = NemesisRunInfo(
            class_name=choice(nemeses_names),
            name="disrupt_something",
            duration=42,
            target_node=node_description,
            status=NemesisStatus.SUCCEEDED.value,
            start_time=int(time()),
            end_time=int(time() + 30),
        )
        nemesis_runs.append(nemesis)

    events = EventsBySeverity(severity="INFO", event_amount=66000, last_events=["Nothing here after all"])
    results = TestResults(status=TestStatus.PASSED.value, nemesis_data=nemesis_runs, events=[events])

    run_info = TestRunInfo(details=details, setup=setup, logs=logs, resources=resources, results=results)

    return run_info


@pytest.fixture(scope="class")
def scylla_cluster() -> list[str]:
    docker_session = docker.from_env()
    prefix = "pytest_scylla_cluster"
    LOGGER.info("Starting docker cluster...")
    cluster_start = run(args=[
        "docker-compose",
        "-p", prefix,
        "-f", "tests/scylladb-cluster/docker-compose.yml",
        "up",
        "-d"
    ], check=True, capture_output=True)
    LOGGER.info("Started docker cluster.\nSTDOUT:\n%s", cluster_start.stdout.decode(encoding="utf-8"))
    interval = 180
    LOGGER.info("Sleeping for %s seconds to let cluster catch up", interval)
    sleep(interval)
    all_containers = docker_session.containers.list(all=True)
    cluster = [container for container in all_containers if container.name.startswith("pytest_scylla_cluster")]
    contact_points = [node.attrs["NetworkSettings"]["Networks"][f"{prefix}_scylla_bridge"]["IPAddress"] for node in
                      cluster]
    LOGGER.debug("Contact points: %s", contact_points)
    yield contact_points
    LOGGER.info("Stopping docker cluster...")
    cluster_stop = run(args=[
        "docker-compose",
        "-p", prefix,
        "-f", "tests/scylladb-cluster/docker-compose.yml",
        "down"
    ], check=True, capture_output=True)
    LOGGER.info("Stopped docker cluster.\nSTDOUT:\n%s", cluster_stop.stdout.decode(encoding="utf-8"))


@pytest.fixture(scope="class")
def argus_database(scylla_cluster: list[str]):  # pylint: disable=redefined-outer-name
    config = Config(username="scylla", password="scylla", contact_points=scylla_cluster, keyspace_name="argus_testruns")
    database = ArgusDatabase.from_config(config)
    yield database
    ArgusDatabase.destroy()
