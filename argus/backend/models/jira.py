from typing import Annotated
from uuid import UUID, uuid4
from datetime import UTC, datetime

from pydantic import Field
from coodie import Indexed, PrimaryKey
from coodie.sync import Document

from argus.backend.models.github_issue import IssueLabel


class JiraIssue(Document):
    id: Annotated[UUID, PrimaryKey()] = Field(default_factory=uuid4)
    user_id: Annotated[UUID, Indexed()]
    summary: str
    key: str
    state: str
    project: str
    permalink: Annotated[str, Indexed()]
    labels: list[IssueLabel] = Field(default_factory=list)
    assignees: list[str] = Field(default_factory=list)
    added_on: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))

    class Settings:
        name = "jira_issue"

    def __hash__(self) -> int:
        return hash(self.key)

    def __eq__(self, other):
        if isinstance(other, JiraIssue):
            return self.key == other.key
        return super().__eq__(other)

    def __ne__(self, other):
        return not self == other
