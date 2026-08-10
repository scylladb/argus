from typing import Annotated, Optional
from uuid import UUID, uuid4
from datetime import UTC, datetime

from pydantic import Field
from coodie import Indexed, PrimaryKey
from coodie.sync import Document

from argus.backend.models.github_issue import IssueLabel


class JiraIssue(Document):
    id: Annotated[UUID, PrimaryKey()] = Field(default_factory=uuid4)
    user_id: Annotated[Optional[UUID], Indexed()] = None
    summary: Optional[str] = None
    key: Optional[str] = None
    state: Optional[str] = None
    project: Optional[str] = None
    permalink: Annotated[Optional[str], Indexed()] = None
    labels: list[IssueLabel] = Field(default_factory=list)
    assignees: list[str] = Field(default_factory=list)
    added_on: Optional[datetime] = Field(default=datetime.now(tz=UTC))

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
