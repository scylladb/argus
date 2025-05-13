from datetime import datetime, UTC

from cassandra.cqlengine import columns
from cassandra.cqlengine.models import Model


class WidgetHighlights(Model):
    view_id = columns.UUID(partition_key=True, required=True)
    index = columns.Integer(partition_key=True, required=True)
    created_at = columns.DateTime(primary_key=True, clustering_order="DESC")
    archived_at = columns.DateTime(default=datetime.fromtimestamp(0, tz=UTC))
    creator_id = columns.UUID()
    assignee_id = columns.UUID()
    content = columns.Text()
    completed = columns.Boolean(default=lambda: None)  # None means it's highlight, not an action item
    comments_count = columns.TinyInt()


class WidgetComment(Model):
    view_id = columns.UUID(partition_key=True, required=True)
    index = columns.Integer(partition_key=True, required=True)
    highlight_at = columns.DateTime(partition_key=True, required=True)  # reference to WidgetHighlights.created_at
    created_at = columns.DateTime(primary_key=True)
    creator_id = columns.UUID()
    content = columns.Text()
