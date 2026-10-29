from datetime import datetime
from typing import Annotated, Optional
from uuid import UUID

from coodie import ClusteringKey, Double, PrimaryKey
from coodie.aio import Document

UNASSIGNED_RELEASE = UUID(int=0)


class RunCostRollup(Document):
    month: Annotated[str, PrimaryKey()]
    release_id: Annotated[UUID, ClusteringKey(clustering_key_index=0)]
    start_time: Annotated[datetime, ClusteringKey(order="DESC", clustering_key_index=1)]
    run_id: Annotated[UUID, ClusteringKey(clustering_key_index=2)]
    plugin_name: str
    build_id: str
    build_number: Optional[int] = None
    group_id: Optional[UUID] = None
    test_id: Optional[UUID] = None
    status: str
    end_time: Optional[datetime] = None
    backend: Optional[str] = None
    region: Optional[str] = None
    spot_terminated: bool = False
    estimated_cost: Annotated[Optional[float], Double()] = None
    actual_cost: Annotated[Optional[float], Double()] = None
    spot_cost: Annotated[float, Double()] = 0.0
    on_demand_cost: Annotated[float, Double()] = 0.0
    untiered_cost: Annotated[float, Double()] = 0.0
    leaked_cost: Annotated[float, Double()] = 0.0
    item_count: int = 0
    spot_count: int = 0
    on_demand_count: int = 0
    untiered_count: int = 0
    leaked_count: int = 0
    resource_count: Optional[int] = None
    priced_count: Optional[int] = None
    coverage: str = "none"

    class Settings:
        name = "run_cost_by_month_v1"


class RunCostReleaseSpan(Document):
    release_id: Annotated[UUID, PrimaryKey()]
    first_start: datetime
    last_start: datetime

    class Settings:
        name = "run_cost_release_span_v1"
