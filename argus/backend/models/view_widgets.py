from datetime import datetime, UTC
from typing import Annotated, Optional
from uuid import UUID

from pydantic import Field
from coodie import ClusteringKey, PrimaryKey, TinyInt
from coodie.sync import Document


class WidgetHighlights(Document):
    view_id: Annotated[UUID, PrimaryKey(partition_key_index=0)]
    index: Annotated[int, PrimaryKey(partition_key_index=1)]
    created_at: Annotated[datetime, ClusteringKey(order="DESC")]
    archived_at: datetime = Field(default_factory=lambda: datetime.fromtimestamp(0, tz=UTC))
    creator_id: UUID
    assignee_id: Optional[UUID] = None
    content: str
    group: Optional[str] = None
    completed: Optional[bool] = None  # None means it's highlight, not an action item
    comments_count: Annotated[int, TinyInt()]

    class Settings:
        name = "widget_highlights"


class WidgetComment(Document):
    view_id: Annotated[UUID, PrimaryKey(partition_key_index=0)]
    index: Annotated[int, PrimaryKey(partition_key_index=1)]
    highlight_at: Annotated[datetime, PrimaryKey(partition_key_index=2)]  # reference to WidgetHighlights.created_at
    created_at: Annotated[datetime, ClusteringKey()]
    creator_id: UUID
    content: str

    class Settings:
        name = "widget_comment"
