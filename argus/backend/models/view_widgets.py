from datetime import datetime, UTC
from typing import Annotated, Optional
from uuid import UUID

from pydantic import Field
from coodie import ClusteringKey, PrimaryKey, TinyInt
from coodie.sync import Document


class WidgetHighlights(Document):
    view_id: Annotated[Optional[UUID], PrimaryKey(partition_key_index=0)] = None
    index: Annotated[Optional[int], PrimaryKey(partition_key_index=1)] = None
    created_at: Annotated[Optional[datetime], ClusteringKey(order="DESC")] = None
    archived_at: Optional[datetime] = Field(default_factory=lambda: datetime.fromtimestamp(0, tz=UTC))
    creator_id: Optional[UUID] = None
    assignee_id: Optional[UUID] = None
    content: Optional[str] = None
    group: Optional[str] = None
    completed: Optional[bool] = None  # None means it's highlight, not an action item
    comments_count: Annotated[Optional[int], TinyInt()] = None

    class Settings:
        name = "widget_highlights"


class WidgetComment(Document):
    view_id: Annotated[Optional[UUID], PrimaryKey(partition_key_index=0)] = None
    index: Annotated[Optional[int], PrimaryKey(partition_key_index=1)] = None
    highlight_at: Annotated[Optional[datetime], PrimaryKey(partition_key_index=2)] = None  # reference to WidgetHighlights.created_at
    created_at: Annotated[Optional[datetime], ClusteringKey()] = None
    creator_id: Optional[UUID] = None
    content: Optional[str] = None

    class Settings:
        name = "widget_comment"
