from cassandra.cqlengine import columns
from cassandra.cqlengine.models import Model


class ErrorEventEmbeddings(Model):
    __table_name__ = "error_event_embeddings"
    run_id = columns.UUID(partition_key=True)
    event_index = columns.Integer(primary_key=True)
    start_time = columns.DateTime(static=True)
    embedding = columns.List(value_type=columns.Float())
    columns.BaseCollectionColumn._freeze_db_type(embedding)
    similars_map = columns.Map(key_type=columns.UUID(), value_type=columns.Integer())
    columns.BaseCollectionColumn._freeze_db_type(similars_map)


class CriticalEventEmbeddings(Model):
    __table_name__ = "critical_event_embeddings"
    run_id = columns.UUID(partition_key=True)
    event_index = columns.Integer(primary_key=True)
    start_time = columns.DateTime(static=True)
    embedding = columns.List(value_type=columns.Float())
    columns.BaseCollectionColumn._freeze_db_type(embedding)
    similars_map = columns.Map(key_type=columns.UUID(), value_type=columns.Integer())
    columns.BaseCollectionColumn._freeze_db_type(similars_map)
