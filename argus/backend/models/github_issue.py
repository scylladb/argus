from enum import unique
from uuid import uuid4
from datetime import datetime
from cassandra.cqlengine.models import Model
from cassandra.cqlengine.usertype import UserType
from cassandra.cqlengine import columns


class IssueLabel(UserType):
    id = columns.BigInt()
    name = columns.Text()
    color = columns.Text()
    description = columns.Text()

    def __hash__(self) -> int:
        return hash((self.name, self.color, self.description))

    def __eq__(self, other):
        if isinstance(other, IssueLabel):
            return self.name == other.name and self.color == other.color and self.description == other.description
        return super().__eq__(other)


class IssueAssignee(UserType):
    login = columns.Text()
    html_url = columns.Text()


class GithubIssue(Model):
    id = columns.UUID(primary_key=True, default=uuid4, partition_key=True)
    user_id = columns.UUID(index=True)  # Internal Argus UserId
    type = columns.Text()  # Can be: issues, pulls
    owner = columns.Text()  # Org or the user to which the repo belongs to
    repo = columns.Text()
    number = columns.Integer()
    state = columns.Text()  # Possible states: open, closed
    title = columns.Text()
    labels = columns.List(value_type=columns.UserDefinedType(user_type=IssueLabel))
    assignees = columns.List(value_type=columns.UserDefinedType(user_type=IssueAssignee))
    url = columns.Text(index=True)
    added_on = columns.DateTime(default=datetime.utcnow)

    def __hash__(self) -> int:
        return hash((self.owner, self.repo, self.number))

    def __eq__(self, other):
        if isinstance(other, GithubIssue):
            return self.owner == other.owner and self.repo == other.repo and self.number == other.number
        return super().__eq__(other)

    def __ne__(self, other):
        return not self == other


class IssueLink(Model):
    run_id = columns.UUID(primary_key=True, required=True, partition_key=True)
    issue_id = columns.UUID(primary_key=True, required=True)
    release_id = columns.UUID(index=True)
    group_id = columns.UUID(index=True)
    test_id = columns.UUID(index=True)
