from cassandra.cluster import Session
from cassandra.cqlengine import columns, ValidationError
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
    duplicates_list = columns.List(value_type=columns.Integer())
    columns.BaseCollectionColumn._freeze_db_type(duplicates_list)


class CriticalEventEmbeddings(Model):
    __table_name__ = "critical_event_embeddings"
    run_id = columns.UUID(partition_key=True)
    event_index = columns.Integer(primary_key=True)
    start_time = columns.DateTime(static=True)
    embedding = columns.List(value_type=columns.Float())
    columns.BaseCollectionColumn._freeze_db_type(embedding)
    similars_map = columns.Map(key_type=columns.UUID(), value_type=columns.Integer())
    columns.BaseCollectionColumn._freeze_db_type(similars_map)
    duplicates_list = columns.List(value_type=columns.Integer())
    columns.BaseCollectionColumn._freeze_db_type(duplicates_list)


class Vector(columns.List):
    """
    Stores a list of ordered values

    http://www.datastax.com/documentation/cql/3.1/cql/cql_using/use_list_t.html
    """

    _python_type_hashable = False

    def __init__(self, value_type, size, default=list, **kwargs):
        """
        :param value_type: a column class indicating the types of the value
        """
        super(columns.List, self).__init__((value_type,), default=default, **kwargs)
        self.value_col = self.types[0]
        self.size = size
        self.db_type = 'vector<{0}, {1}>'.format(self.value_col.db_type, self.size)

    def validate(self, value):
        val = super(columns.List, self).validate(value)
        if val is None:
            return
        if not isinstance(val, (set, list, tuple)):
            raise ValidationError('{0} {1} is not a list object'.format(self.column_name, val))
        if None in val:
            raise ValidationError("{0} None is not allowed in a list".format(self.column_name))
        if len(val) != self.size:
            raise ValidationError(f"{self.column_name} Invalid vector size {len(val)} != {self.size}")
        return [self.value_col.validate(v) for v in val]


class SCTErrorEventEmbedding(Model):
    """Table to store ERROR event embeddings for similarity search."""
    __table_name__ = "sct_error_event_embedding"

    run_id = columns.UUID(partition_key=True)
    ts = columns.DateTime(primary_key=True, clustering_order="DESC")
    embedding = Vector(value_type=columns.Float(), size=384)

    @classmethod
    def _sync_additional_rules(cls, session: Session):
        session.execute(
            f"CREATE INDEX IF NOT EXISTS error_event_index ON {cls.__table_name__}(embedding) USING 'vector_index' WITH OPTIONS = {{ 'similarity_function': 'COSINE' }}"
        )


class SCTCriticalEventEmbedding(Model):
    """Table to store CRITICAL event embeddings for similarity search."""
    __table_name__ = "sct_critical_event_embedding"

    run_id = columns.UUID(partition_key=True)
    ts = columns.DateTime(primary_key=True, clustering_order="DESC")
    embedding = Vector(value_type=columns.Float(), size=384)

    @classmethod
    def _sync_additional_rules(cls, session: Session):
        session.execute(
            f"CREATE INDEX IF NOT EXISTS critical_event_index ON {cls.__table_name__}(embedding) USING 'vector_index' WITH OPTIONS = {{ 'similarity_function': 'COSINE' }}"
        )
