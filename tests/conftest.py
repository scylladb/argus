import pytest
from time import time
from os import urandom
from random import choice
from argus.db.testrun import TestRunInfo, TestDetails, TestResourcesSetup, TestLogs, TestResults, TestResources
from argus.db.interface import ArgusDatabase
from argus.db.config import Config
from argus.db.types import PackageVersion, NemesisRunInfo, EventsBySeverity, NodeDescription, TestStatus, NemesisStatus
from argus.db.cloud_types import AWSSetupDetails, CloudNodesInfo, CloudInstanceDetails, CloudResource, ResourceState
from subprocess import run
from time import sleep
import docker
import logging

logging.basicConfig()
logging.getLogger().setLevel(logging.DEBUG)

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="function")
def preset_details():
    sct_runner_info = CloudInstanceDetails(ip="1.1.1.1", region="us-east-1", provider="aws")
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
def scylla_cluster():
    docker_session = docker.from_env()
    prefix = "pytest_scylla_cluster"
    run(args=[
        "docker-compose",
        "-p", prefix,
        "-f", "tests/scylladb-cluster/docker-compose.yml",
        "up",
        "-d"
    ], check=True)
    LOGGER.info("Sleeping for 90 seconds to let cluster catch up")
    sleep(90)
    all_containers = docker_session.containers.list(all=True)
    cluster = [container for container in all_containers if container.name.startswith("pytest_scylla_cluster")]
    contact_points = [node.attrs["NetworkSettings"]["Networks"][f"{prefix}_scylla_bridge"]["IPAddress"] for node in
                      cluster]
    LOGGER.debug("Contact points: %s", contact_points)
    yield contact_points
    run(args=[
        "docker-compose",
        "-p", prefix,
        "-f", "tests/scylladb-cluster/docker-compose.yml",
        "down"
    ])


@pytest.fixture(scope="function")
def argus_database(scylla_cluster: list[str]):
    config = Config(username="scylla", password="scylla", contact_points=scylla_cluster, keyspace_name="argus_testruns")
    db = ArgusDatabase.from_config(config)
    yield db
    ArgusDatabase.destroy()


@pytest.fixture(scope="function")
def completed_testrun(preset_details: TestResourcesSetup):
    scylla_package = PackageVersion("scylla-db", "4.4", "20210901", "deadbeef")
    details = TestDetails(name="longevity-test-100gb-4h", scm_revision_id="773413dead", started_by="komachi",
                          build_job_name="komachi-longevity-test-100gb-4h",
                          build_job_url="https://notarealjob.url/jobs/komachi-longevity-test-100gb-4h",
                          start_time=int(time()), yaml_test_duration=240, config_files=["tests/config.yaml"],
                          packages=[scylla_package])
    setup = preset_details  # TestSetup
    logs = TestLogs()
    logs.add_log(log_type="syslog", log_url="https://thisisdefinitelyans3bucket.com/logz-abcdef331.tar.gz")
    resources = TestResources()

    created_resources = []

    for requested_node in [setup.cloud_setup.db_node, setup.cloud_setup.loader_node, setup.cloud_setup.monitor_node]:
        for node_number in range(1, requested_node.node_amount + 1):
            entropy = urandom(4).hex(sep=":", bytes_per_sep=1).split(":")
            random_ip = ".".join([str(int(byte, 16)) for byte in entropy])
            instance_details = CloudInstanceDetails(ip=random_ip, provider="aws", region="us-east-1")
            resource = CloudResource(name=f"{details.name}_{requested_node.instance_type}_{node_number}",
                                     resource_state=ResourceState.RUNNING.value, instance_info=instance_details)
            resources.attach_resource(resource)
            created_resources.append(resource)

    terminated = choice(created_resources)
    resources.detach_resource(terminated)

    nemeses_names = ["SisyphusMonkey", "ChaosMonkey", "NotVeryCoolMonkey"]
    nemesis_runs = []

    for _ in range(6):
        node = choice(resources.leftover_resources)
        node_description = NodeDescription(name=node.name, ip=node.instance_info.ip, shards=10)
        nemesis = NemesisRunInfo(
            class_name=choice(nemeses_names),
            nemesis_name="disrupt_something",
            duration=42,
            target_node=node_description,
            status=NemesisStatus.Succeeded.value,
            start_time=int(time()),
            end_time=int(time() + 30),
        )
        nemesis_runs.append(nemesis)

    events = EventsBySeverity(severity="INFO", event_amount=66000, last_events=["Nothing here after all"])
    results = TestResults(status=TestStatus.Passed.value, nemesis_data=nemesis_runs, events=[events])

    run_info = TestRunInfo(details=details, setup=setup, logs=logs, resources=resources, results=results)

    return run_info
