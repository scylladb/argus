from enum import Enum
from typing import Any, Union, Type, Tuple, TypeVar
from dataclasses import dataclass, fields, Field

T = TypeVar("T")


@dataclass
class ArgusUDTBase:
    pass


@dataclass(init=True, repr=True)
class NodeDescription(ArgusUDTBase):
    name: str
    ip: str
    shards: int

    @classmethod
    def from_db_udt(cls, udt):
        return cls(name=udt.name, ip=udt.ip, shards=udt.shards)


@dataclass(init=True, repr=True)
class PackageVersion(ArgusUDTBase):
    name: str
    version: str
    date: str
    revision_id: str

    @classmethod
    def from_db_udt(cls, udt):
        return cls(name=udt.name, version=udt.version, date=udt.date, revision_id=udt.revision_id)


class NemesisStatus(Enum):
    Started = "started"
    Running = "running"
    Failed = "failed"
    Succeeded = "succeeded"


class TestStatus(Enum):
    Created = "created"
    Failed = "failed"
    Passed = "passed"


@dataclass(init=True, repr=True)
class NemesisRunInfo(ArgusUDTBase):
    class_name: str
    nemesis_name: str
    duration: int
    target_node: NodeDescription
    status: str
    start_time: int
    end_time: int = 0
    stack_trace: str = ""

    @classmethod
    def from_db_udt(cls, udt):
        target_node = NodeDescription.from_db_udt(udt.target_node)
        return cls(class_name=udt.class_name, nemesis_name=udt.nemesis_name, duration=udt.duration,
                   target_node=target_node, status=udt.status, start_time=udt.start_time, end_time=udt.end_time,
                   stack_trace=udt.stack_trace)


@dataclass(init=True, repr=True)
class EventsBySeverity(ArgusUDTBase):
    severity: str
    event_amount: int
    last_events: list[str]

    @classmethod
    def from_db_udt(cls, udt):
        return cls(severity=udt.severity, event_amount=udt.event_amount, last_events=udt.last_events)


@dataclass(init=True, repr=True)
class CollectionHint:
    stored_type: Type


@dataclass(init=True, repr=True)
class ColumnInfo:
    name: str
    type: Type[Union[CollectionHint, int, str, T]]
    value: Any
    constraints: list[str]
