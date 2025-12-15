from uuid import uuid4
from datetime import UTC, datetime
from cassandra.cqlengine.models import Model
from cassandra.cqlengine import columns

from argus.backend.models.github_issue import IssueLabel


class JiraIssue(Model):
    id = columns.UUID(primary_key=True, default=uuid4, partition_key=True)
    user_id = columns.UUID(index=True)
    summary = columns.Text()
    key = columns.Text()
    state = columns.Text()
    project = columns.Text()
    permalink = columns.Text(index=True)
    labels = columns.List(value_type=columns.UserDefinedType(user_type=IssueLabel))
    assignees = columns.List(value_type=columns.Text())
    added_on = columns.DateTime(default=datetime.now(tz=UTC))

    def __hash__(self) -> int:
        return hash(self.key)

    def __eq__(self, other):
        if isinstance(other, JiraIssue):
            return self.key == other.key
        return super().__eq__(other)

    def __ne__(self, other):
        return not self == other
