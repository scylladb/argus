import pytest
from time import time
from argus.db.testrun import TestDetails, TestResourcesSetup, TestResources, TestLogs, TestResults, TestInfoValueError
from argus.db.db_types import TestStatus, PackageVersion, CollectionHint, ColumnInfo, NodeDescription, NemesisRunInfo, \
    NemesisStatus
from argus.db.cloud_types import BaseCloudSetupDetails, CloudInstanceDetails, ResourceState, CloudResource
from collections import namedtuple


def test_details_schema_dump(preset_test_details_schema: dict):
    schema = TestDetails.schema()
    assert schema == preset_test_details_schema


def test_details_serialization(preset_test_details: TestDetails, preset_test_details_serialized: dict):
    dump = preset_test_details.serialize()

    assert dump == preset_test_details_serialized


def test_details_validation_invalid_packages():
    with pytest.raises(TestInfoValueError):
        TestDetails(name="some-test", scm_revision_id="abcde", started_by="someone",
                    build_job_name="some-test-job",
                    build_job_url="https://job.tld/1", start_time=1600000000, yaml_test_duration=120,
                    config_files=["some-test.yaml"],
                    packages=["peckege", 123])


def test_details_no_exception_on_empty_package_list():
    TestDetails(name="some-test", scm_revision_id="abcde", started_by="someone",
                build_job_name="some-test-job",
                build_job_url="https://job.tld/1", start_time=1600000000, yaml_test_duration=120,
                config_files=["some-test.yaml"],
                packages=[])


def test_details_ctor_from_named_tuple(preset_test_details):
    ResultSet = namedtuple("Row",
                           ["name", "scm_revision_id", "started_by", "build_job_name", "build_job_url", "start_time",
                            "yaml_test_duration", "config_files", "packages", "end_time"])
    PackageMapped = namedtuple("PackageMapped", ["name", "version", "date", "revision_id"])
    package = PackageMapped("package-server", "1.0", "2021-10-01", "dfcedb3")
    row = ResultSet(preset_test_details.name, preset_test_details.scm_revision_id, preset_test_details.started_by,
                    preset_test_details.build_job_name, preset_test_details.build_job_url,
                    preset_test_details.start_time,
                    preset_test_details.yaml_test_duration,
                    preset_test_details.config_files,
                    [package], preset_test_details.end_time)

    new_test_details = TestDetails.from_db_row(row)
    assert new_test_details.serialize() == preset_test_details.serialize()


def test_resources_setup_schema_dump(preset_test_resources_setup_schema: dict):
    schema = TestResourcesSetup.schema()
    assert schema == preset_test_resources_setup_schema


def test_resources_setup_serialization(preset_test_resource_setup,
                                       preset_test_resources_setup_serialized: dict):
    assert preset_test_resource_setup.serialize() == preset_test_resources_setup_serialized


def test_resources_setup_ctor_from_named_tuple(preset_test_resource_setup: TestResourcesSetup):
    CloudNodeMapped = namedtuple("CloudNodeMapped", ["image_id", "instance_type", "node_amount", "post_behaviour"])
    CloudSetupMapped = namedtuple("CloudSetupMapped", ["backend", "db_node", "loader_node", "monitor_node"])
    CloudInstanceDetailsMapped = namedtuple("CloudInstanceDetailsMapped", ["ip", "region", "provider"])
    ResourceSetupRow = namedtuple("ResourceSetupRow", ["sct_runner_host", "region_name", "cloud_setup"])

    db_node = CloudNodeMapped(image_id="ami-abcdef99", instance_type="spot",
                              node_amount=6, post_behaviour="keep-on-failure")
    loader_node = CloudNodeMapped(image_id="ami-deadbeef", instance_type="spot",
                                  node_amount=2, post_behaviour="terminate")
    monitor_node = CloudNodeMapped(image_id="ami-abdcef60", instance_type="spot",
                                   node_amount=1, post_behaviour="keep-on-failure")

    cloud_setup = CloudSetupMapped(backend="aws", db_node=db_node, loader_node=loader_node, monitor_node=monitor_node)

    sct_runner_info = CloudInstanceDetailsMapped(ip="1.1.1.1", region="us-east-1", provider="aws")

    mapped_setup = ResourceSetupRow(sct_runner_host=sct_runner_info, region_name=["us-east-1"], cloud_setup=cloud_setup)

    new_setup = TestResourcesSetup.from_db_row(mapped_setup)

    assert new_setup.serialize() == preset_test_resource_setup.serialize()


def test_logs_schema_dump(preset_test_logs_schema: dict):
    assert TestLogs.schema() == preset_test_logs_schema


def test_logs_serialization(preset_test_logs: TestLogs, preset_test_logs_serialized: dict):
    assert preset_test_logs.serialize() == preset_test_logs_serialized


def test_logs_add_log(preset_test_logs: TestLogs):
    log_pair = ("another_example", "http://eggsample.com")
    preset_test_logs.add_log(*log_pair)

    assert log_pair in preset_test_logs.logs


def test_logs_ctor_from_named_tuple(preset_test_logs: TestLogs):
    MappedLogs = namedtuple("MappedLogs", ["logs"])
    mapped_logs = MappedLogs([("example", "http://example.com")])

    new_logs = TestLogs.from_db_row(mapped_logs)
    assert new_logs.serialize() == preset_test_logs.serialize()


def test_resources_schema_dump(preset_test_resources_schema: dict):
    assert TestResources.schema() == preset_test_resources_schema


def test_resources_serialization(preset_test_resources: TestResources, preset_test_resources_serialized: dict):
    assert preset_test_resources.serialize() == preset_test_resources_serialized


def test_resources_attach(preset_test_resources: TestResources):
    instance_info = CloudInstanceDetails(ip="1.1.1.2", region="us-east-1", provider="aws")
    resource = CloudResource(name="example_resource_2", resource_state=ResourceState.RUNNING,
                             instance_info=instance_info)

    preset_test_resources.attach_resource(resource)

    assert resource in preset_test_resources.allocated_resources
    assert resource in preset_test_resources.leftover_resources


def test_resources_attach_detach(preset_test_resources: TestResources):
    instance_info = CloudInstanceDetails(ip="1.1.1.2", region="us-east-1", provider="aws")
    resource = CloudResource(name="example_resource_2", resource_state=ResourceState.RUNNING,
                             instance_info=instance_info)

    preset_test_resources.attach_resource(resource)

    assert resource in preset_test_resources.allocated_resources
    assert resource in preset_test_resources.leftover_resources

    preset_test_resources.detach_resource(resource)

    assert resource not in preset_test_resources.leftover_resources
    assert resource in preset_test_resources.allocated_resources
    assert resource in preset_test_resources.terminated_resources


def test_resources_ctor_from_named_tuple(preset_test_resources):
    CloudInstanceDetailsMapped = namedtuple("CloudInstanceDetailsMapped", ["provider", "region", "ip"])
    CloudResourceMapped = namedtuple("CloudResourceMapped", ["name", "resource_state", "instance_info"])
    instance_info = CloudInstanceDetailsMapped(ip="1.1.1.1", region="us-east-1", provider="aws")
    resource = CloudResourceMapped(name="example_resource", resource_state=ResourceState.RUNNING.value,
                                   instance_info=instance_info)

    ResourceSetupRow = namedtuple("ResourcesRow", ["allocated_resources", "leftover_resources", "terminated_resources"])

    row = ResourceSetupRow([resource], [resource], [])

    new_resources = TestResources.from_db_row(row)

    assert new_resources.serialize() == preset_test_resources.serialize()


def test_results_schema_dump(preset_test_results_schema: dict):
    assert TestResults.schema() == preset_test_results_schema


def test_results_serialization(monkeypatch: pytest.MonkeyPatch, preset_test_results: TestResults,
                               preset_test_results_serialized: dict):
    monkeypatch.setattr("time.time", lambda: 16001)
    preset_test_results.nemesis_data[0].complete("Something went wrong...")

    assert preset_test_results.serialize() == preset_test_results_serialized


def test_results_set_status(preset_test_results):
    preset_test_results.status = TestStatus.RUNNING

    assert preset_test_results.status == TestStatus.RUNNING


def test_results_set_status_incorrect_enum(preset_test_results):
    with pytest.raises(ValueError):
        preset_test_results.status = "ASDJKDGHKJSD"


def test_results_set_status_coercion_to_enum(preset_test_results):
    preset_test_results.status = "failed"

    assert preset_test_results.status == TestStatus.FAILED


def test_results_add_nemesis(preset_test_results):
    node_description = NodeDescription(ip="1.1.1.1", shards=10, name="example_node")
    nemesis = NemesisRunInfo("ChaosMonkey", "disrupt_delete_usr", 30, target_node=node_description,
                             status=NemesisStatus.RUNNING,
                             start_time=16000)

    preset_test_results.add_nemesis(nemesis)

    assert nemesis in preset_test_results.nemesis_data


def test_results_add_event_with_severity(preset_test_results):
    preset_test_results.add_event(event_severity="DEBUG", event_message="test_message")

    value = next(ev for ev in preset_test_results.events if ev.severity == "DEBUG")

    assert "test_message" in value.last_events and value.event_amount == 1


def test_results_add_events_with_same_severity(preset_test_results):
    preset_test_results.add_event(event_severity="DEBUG", event_message="test_message")
    value = next(ev for ev in preset_test_results.events if ev.severity == "DEBUG")
    preset_test_results.add_event(event_severity="DEBUG", event_message="test_message_2")

    assert "test_message" in value.last_events and "test_message_2" in value.last_events and value.event_amount == 2


def test_results_ctor_from_named_tuple(preset_test_results, monkeypatch):
    monkeypatch.setattr("time.time", lambda: 16001)
    preset_test_results.nemesis_data[0].complete("Something went wrong...")

    ResultsMapped = namedtuple("ResultsMapped", ["status", "events", "nemesis_data"])
    EventsMapped = namedtuple("EventsMapped", ["severity", "event_amount", "last_events"])
    NemesisRunMapped = namedtuple("NemesisRunMapped",
                                  ["class_name", "nemesis_name", "duration", "target_node", "status",
                                   "start_time", "end_time", "stack_trace"])
    NodeDescriptionMapped = namedtuple("NodeDescriptionMapped", ["ip", "shards", "name"])

    node_description = NodeDescriptionMapped(ip="1.1.1.1", shards=10, name="example_node")
    nemesis = NemesisRunMapped("Nemesis", "disrupt_everything", 100, target_node=node_description,
                               status=NemesisStatus.FAILED.value, start_time=16000, end_time=16001,
                               stack_trace="Something went wrong...")
    event = EventsMapped(severity="ERROR", event_amount=1, last_events=["Something went wrong..."])

    row = ResultsMapped(status=TestStatus.FAILED.value, events=[event], nemesis_data=[nemesis])

    new_test_result = TestResults.from_db_row(row)

    assert new_test_result.serialize() == preset_test_results.serialize()
