import datetime
from cassandra.cqlengine import columns
from cassandra.cqlengine.models import Model
from cassandra.cqlengine.usertype import UserType
from cassandra.util import uuid_from_time


class ArgusReleasePlan(Model):
    id = columns.TimeUUID(partition_key=True, default=lambda: uuid_from_time(datetime.datetime.now(tz=datetime.UTC)))
    name = columns.Text(required=True)
    completed = columns.Boolean(default=lambda: False)
    description = columns.Text()
    owner = columns.UUID(required=True)
    participants = columns.List(value_type=columns.UUID)
    target_version = columns.Ascii(index=True)
    assignee_mapping = columns.Map(key_type=columns.UUID, value_type=columns.UUID)
    release_id = columns.UUID(index=True)
    tests = columns.List(value_type=columns.UUID)
    groups = columns.List(value_type=columns.UUID)
    view_id = columns.UUID(index=True)
    created_from = columns.UUID(index=True)
    creation_time = columns.DateTime(default=lambda: datetime.datetime.now(tz=datetime.UTC))
    last_updated = columns.DateTime(default=lambda: datetime.datetime.now(tz=datetime.UTC))
    ends_at = columns.DateTime()
