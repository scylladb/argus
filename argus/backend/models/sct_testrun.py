from datetime import datetime
from time import time

from cassandra.cqlengine.models import Model
from cassandra.cqlengine.usertype import UserType
from cassandra.cqlengine import columns

from argus.backend.enums import TestStatus, TestInvestigationStatus


class PackageVersion(UserType):
    __type_name__ = "PackageVersion_v2"
    name = columns.Text()
    version = columns.Text()
    date = columns.Text()
    revision_id = columns.Text()
    build_id = columns.Text()


class CloudInstanceDetails(UserType):
    __type_name__ = "CloudInstanceDetails_v3"
    provider = columns.Text()
    region = columns.Text()
    public_ip = columns.Text()
    private_ip = columns.Text()
    creation_time = columns.Integer()
    termination_time = columns.Integer()
    termination_reason = columns.Text()
    shards_amount = columns.Integer()


class CloudNodesInfo(UserType):
    __type_name__ = "CloudNodesInfo"
    image_id = columns.Text()
    instance_type = columns.Text()
    node_amount = columns.Integer()
    post_behaviour = columns.Text()


class CloudSetupDetails(UserType):
    __type_name__ = "CloudSetupDetails"
    db_node = columns.UserDefinedType(user_type=CloudNodesInfo)
    loader_node = columns.UserDefinedType(user_type=CloudNodesInfo)
    monitor_node = columns.UserDefinedType(user_type=CloudNodesInfo)
    backend = columns.Text()


class CloudResource(UserType):
    __type_name__ = "CloudResource_v3"
    name = columns.Text()
    state = columns.Text()
    resource_type = columns.Text()
    instance_info = columns.UserDefinedType(user_type=CloudInstanceDetails)


class EventsBySeverity(UserType):
    __type_name__ = "EventsBySeverity"
    severity = columns.Text()
    event_amount = columns.Integer()
    last_events = columns.List(value_type=columns.Text())


class NodeDescription(UserType):
    __type_name__ = "NodeDescription"
    name = columns.Text()
    ip = columns.Text()
    shards = columns.Integer()


class NemesisRunInfo(UserType):
    __type_name__ = "NemesisRunInfo"

    class_name = columns.Text()
    name = columns.Text()
    duration = columns.Integer()
    target_node = columns.UserDefinedType(user_type=NodeDescription)
    status = columns.Text()
    start_time = columns.Integer()
    end_time = columns.Integer()
    stack_trace = columns.Text()


class SCTTestRun(Model):
    __table_name__ = "test_runs_v8"

    # Metadata
    build_id = columns.Text(required=True, partition_key=True)
    start_time = columns.DateTime(required=True, primary_key=True, clustering_order="DESC", default=datetime.now)
    id = columns.UUID(index=True, required=True)
    release_id = columns.UUID(index=True)
    group_id = columns.UUID(index=True)
    test_id = columns.UUID(index=True)
    assignee = columns.UUID(index=True)
    status = columns.Text(default=lambda: TestStatus.CREATED)
    investigation_status = columns.Text(default=lambda: TestInvestigationStatus.NOT_INVESTIGATED)
    heartbeat = columns.Integer(default=lambda: int(time()))

    # Test Details
    end_time = columns.DateTime(default=lambda: datetime.fromtimestamp(0))
    scm_revision_id = columns.Text()
    started_by = columns.Text()
    build_job_url = columns.Text()
    config_files = columns.List(value_type=columns.Text())
    packages = columns.List(value_type=columns.UserDefinedType(user_type=PackageVersion))
    scylla_version = columns.Text()
    yaml_test_duration = columns.Integer()

    # Test Resources
    sct_runner_host = columns.UserDefinedType(user_type=CloudInstanceDetails)
    region_name = columns.List(value_type=columns.Text())
    cloud_setup = columns.UserDefinedType(user_type=CloudSetupDetails)

    # Test Logs Collection
    logs = columns.List(value_type=columns.Tuple(columns.Text(), columns.Text()))

    # Test Resources
    allocated_resources = columns.List(value_type=columns.UserDefinedType(user_type=CloudResource))

    # Test Results
    events = columns.List(value_type=columns.UserDefinedType(user_type=EventsBySeverity))
    nemesis_data = columns.List(value_type=columns.UserDefinedType(user_type=NemesisRunInfo))
    screenshots = columns.List(value_type=columns.Text())

    @classmethod
    def table_name(cls) -> str:
        return cls.__table_name__
