from time import time
from cassandra.cqlengine.usertype import UserType
from cassandra.cqlengine import columns

from argus.backend.util.enums import ResourceState


class PackageVersion(UserType):
    __type_name__ = "PackageVersion_v2"
    name = columns.Text()
    version = columns.Text()
    date = columns.Text()
    revision_id = columns.Text()
    build_id = columns.Text()


    def __eq__(self, other):
        if isinstance(other, PackageVersion):
            return all(getattr(self, a) == getattr(other, a) for a in ["name", "version", "date", "revision_id", "build_id"])
        return super().__eq__(other)


class CloudInstanceDetails(UserType):
    __type_name__ = "CloudInstanceDetails_v3"
    provider = columns.Text()
    region = columns.Text()
    public_ip = columns.Text()
    private_ip = columns.Text()
    dc_name = columns.Text()
    rack_name = columns.Text()
    creation_time = columns.Integer(default=lambda: int(time()))
    termination_time = columns.Integer(default=lambda: 0)
    termination_reason = columns.Text(default=lambda: "")
    shards_amount = columns.Integer(default=lambda: 0)


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
    state = columns.Text(default=lambda: ResourceState.RUNNING)
    resource_type = columns.Text()
    instance_info = columns.UserDefinedType(user_type=CloudInstanceDetails)

    def get_instance_info(self) -> CloudInstanceDetails:
        return self.instance_info


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


class PerformanceHDRHistogram(UserType):
    start_time = columns.Integer()
    percentile_90 = columns.Float()
    percentile_50 = columns.Float()
    percentile_99_999 = columns.Float()
    percentile_95 = columns.Float()
    end_time = columns.Float()
    percentile_99_99 = columns.Float()
    percentile_99 = columns.Float()
    stddev = columns.Float()
    percentile_99_9 = columns.Float()
