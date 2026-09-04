from datetime import datetime
from typing import Annotated, Optional
from uuid import UUID

from pydantic import Field
from coodie import ClusteringKey, Frozen, PrimaryKey, Static, Vector, VectorIndex
from coodie.sync import Document


class ErrorEventEmbeddings(Document):
    run_id: Annotated[UUID, PrimaryKey()]
    event_index: Annotated[int, ClusteringKey()]
    start_time: Annotated[Optional[datetime], Static()] = None
    embedding: Annotated[Optional[list[float]], Frozen()] = None
    similars_map: Annotated[Optional[dict[UUID, int]], Frozen()] = None
    duplicates_list: Annotated[Optional[list[int]], Frozen()] = None

    class Settings:
        name = "error_event_embeddings"


class CriticalEventEmbeddings(Document):
    run_id: Annotated[UUID, PrimaryKey()]
    event_index: Annotated[int, ClusteringKey()]
    start_time: Annotated[Optional[datetime], Static()] = None
    embedding: Annotated[Optional[list[float]], Frozen()] = None
    similars_map: Annotated[Optional[dict[UUID, int]], Frozen()] = None
    duplicates_list: Annotated[Optional[list[int]], Frozen()] = None

    class Settings:
        name = "critical_event_embeddings"


class SCTErrorEventEmbedding(Document):
    """Table to store ERROR event embeddings for similarity search."""
    run_id: Annotated[UUID, PrimaryKey()]
    ts: Annotated[datetime, ClusteringKey(order="DESC")]
    embedding: Annotated[list[float], Vector(dimensions=384),
                         VectorIndex(similarity_function="COSINE")] = Field(default_factory=list)

    class Settings:
        name = "sct_error_event_embedding"
        keyspace = "argus_tablets"


class SCTCriticalEventEmbedding(Document):
    """Table to store CRITICAL event embeddings for similarity search."""
    run_id: Annotated[UUID, PrimaryKey()]
    ts: Annotated[datetime, ClusteringKey(order="DESC")]
    embedding: Annotated[list[float], Vector(dimensions=384),
                         VectorIndex(similarity_function="COSINE")] = Field(default_factory=list)

    class Settings:
        name = "sct_critical_event_embedding"
        keyspace = "argus_tablets"
