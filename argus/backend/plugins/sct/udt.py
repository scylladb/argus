from cassandra.cqlengine.usertype import UserType
from cassandra.cqlengine import columns


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
