from time import time
from typing import Optional

from pydantic import Field

from coodie.usertype import UserType

from argus.common.enums import ResourceState


class PackageVersion(UserType):
    name: Optional[str] = None
    version: Optional[str] = None
    date: Optional[str] = None
    revision_id: Optional[str] = None
    build_id: Optional[str] = None

    class Settings:
        __type_name__ = "packageversion_v2"

    def __eq__(self, other):
        if isinstance(other, PackageVersion):
            return all(getattr(self, a) == getattr(other, a) for a in ["name", "version", "date", "revision_id", "build_id"])
        return super().__eq__(other)


class CloudInstanceDetails(UserType):
    provider: Optional[str] = None
    instance_type: Optional[str] = None
    region: Optional[str] = None
    public_ip: Optional[str] = None
    private_ip: Optional[str] = None
    dc_name: Optional[str] = None
    rack_name: Optional[str] = None
    creation_time: Optional[int] = Field(default_factory=lambda: int(time()))
    termination_time: Optional[int] = 0
    termination_reason: Optional[str] = ""
    shards_amount: Optional[int] = 0

    class Settings:
        __type_name__ = "cloudinstancedetails_v3"


class CloudNodesInfo(UserType):
    image_id: Optional[str] = None
    instance_type: Optional[str] = None
    node_amount: Optional[int] = None
    post_behaviour: Optional[str] = None

    class Settings:
        __type_name__ = "cloudnodesinfo"


class CloudSetupDetails(UserType):
    db_node: Optional[CloudNodesInfo] = None
    loader_node: Optional[CloudNodesInfo] = None
    monitor_node: Optional[CloudNodesInfo] = None
    backend: Optional[str] = None

    class Settings:
        __type_name__ = "cloudsetupdetails"


class CloudResource(UserType):
    name: Optional[str] = None
    state: Optional[str] = Field(default=ResourceState.RUNNING.value)
    resource_type: Optional[str] = None
    instance_info: Optional[CloudInstanceDetails] = None

    class Settings:
        __type_name__ = "cloudresource_v3"

    def get_instance_info(self) -> CloudInstanceDetails:
        return self.instance_info


class EventsBySeverity(UserType):
    severity: Optional[str] = None
    event_amount: Optional[int] = None
    last_events: list[str] = Field(default_factory=list)

    class Settings:
        __type_name__ = "eventsbyseverity"


class NodeDescription(UserType):
    name: Optional[str] = None
    ip: Optional[str] = None
    shards: Optional[int] = None

    class Settings:
        __type_name__ = "nodedescription"


class NemesisRunInfo(UserType):
    class_name: Optional[str] = None
    name: Optional[str] = None
    duration: Optional[int] = None
    target_node: Optional[NodeDescription] = None
    status: Optional[str] = None
    start_time: Optional[int] = None
    end_time: Optional[int] = None
    stack_trace: Optional[str] = None

    class Settings:
        __type_name__ = "nemesisruninfo"


class PerformanceHDRHistogram(UserType):
    start_time: Optional[int] = None
    percentile_90: Optional[float] = None
    percentile_50: Optional[float] = None
    percentile_99_999: Optional[float] = None
    percentile_95: Optional[float] = None
    end_time: Optional[float] = None
    percentile_99_99: Optional[float] = None
    percentile_99: Optional[float] = None
    stddev: Optional[float] = None
    percentile_99_9: Optional[float] = None

    class Settings:
        # cqlengine derived this name without the HDR/Histogram word split
        __type_name__ = "performance_hdrhistogram"
