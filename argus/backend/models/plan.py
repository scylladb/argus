import datetime
from typing import Annotated, Optional
from uuid import UUID

from pydantic import Field
from cassandra.util import uuid_from_time
from coodie import Ascii, Indexed, PrimaryKey, TimeUUID
from coodie.sync import Document


class ArgusReleasePlan(Document):
    id: Annotated[UUID, TimeUUID(), PrimaryKey()] = Field(
        default_factory=lambda: uuid_from_time(datetime.datetime.now(tz=datetime.UTC)))
    name: str
    completed: bool = False
    description: str
    owner: UUID
    participants: list[UUID] = Field(default_factory=list)
    target_version: Annotated[str, Ascii(), Indexed()]
    assignee_mapping: dict[UUID, UUID] = Field(default_factory=dict)
    release_id: Annotated[UUID, Indexed()]
    tests: list[UUID] = Field(default_factory=list)
    groups: list[UUID] = Field(default_factory=list)
    view_id: Annotated[Optional[UUID], Indexed()] = None
    created_from: Annotated[Optional[UUID], Indexed()] = None
    creation_time: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(tz=datetime.UTC))
    last_updated: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(tz=datetime.UTC))
    ends_at: Optional[datetime.datetime] = None
    key: Optional[str] = None
    # JSON-serialized per-entity options keyed by test/group UUID, e.g.
    # {"<test-or-group-uuid>": {"labels": ["label-a", "label-b"]}}
    options: Optional[str] = None

    class Settings:
        name = "argus_release_plan"

    def __eq__(self, other):
        if isinstance(other, ArgusReleasePlan):
            return self.id == other.id
        else:
            return super().__eq__(other)

    def __hash__(self):
        return hash(self.id)
