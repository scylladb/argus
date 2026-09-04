from enum import Enum, unique
from typing import Annotated, Optional
from uuid import UUID, uuid4
from datetime import UTC, datetime

from pydantic import Field
from coodie import BigInt, ClusteringKey, Indexed, PrimaryKey
from coodie.sync import Document
from coodie.usertype import UserType


class IssueLabel(UserType):
    id: Annotated[int, BigInt()]
    name: str
    color: str
    description: Optional[str] = None

    def __hash__(self) -> int:
        return hash((self.name, self.color, self.description))

    def __eq__(self, other):
        if isinstance(other, IssueLabel):
            return self.name == other.name and self.color == other.color and self.description == other.description
        return super().__eq__(other)


class IssueAssignee(UserType):
    login: str
    html_url: str


class GithubIssue(Document):
    id: Annotated[UUID, PrimaryKey()] = Field(default_factory=uuid4)
    user_id: Annotated[UUID, Indexed()]  # Internal Argus UserId
    type: str  # Can be: issues, pulls
    owner: Optional[str] = None  # Org or the user to which the repo belongs to
    repo: str
    number: int
    state: str  # Possible states: open, closed
    title: str
    labels: list[IssueLabel] = Field(default_factory=list)
    assignees: list[IssueAssignee] = Field(default_factory=list)
    url: Annotated[str, Indexed()]
    added_on: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))

    class Settings:
        name = "github_issue"

    def __hash__(self) -> int:
        return hash((self.owner, self.repo, self.number))

    def __eq__(self, other):
        if isinstance(other, GithubIssue):
            return self.owner == other.owner and self.repo == other.repo and self.number == other.number
        return super().__eq__(other)

    def __ne__(self, other):
        return not self == other


class IssueLink(Document):
    run_id: Annotated[UUID, PrimaryKey()]
    issue_id: Annotated[UUID, ClusteringKey()]
    release_id: Annotated[UUID, Indexed()]
    group_id: Annotated[UUID, Indexed()]
    test_id: Annotated[UUID, Indexed()]
    user_id: Annotated[Optional[UUID], Indexed()] = None
    event_id: Annotated[Optional[UUID], Indexed()] = None
    added_on: Optional[datetime] = Field(default_factory=lambda: datetime.now(tz=UTC))
    type: Optional[str] = None

    class Settings:
        name = "issue_link"
