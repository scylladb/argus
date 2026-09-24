from typing import Annotated, Optional
from uuid import UUID

from coodie import ClusteringKey, Double, PrimaryKey, Static
from coodie.aio import Document


class RunCost(Document):
    run_id: Annotated[UUID, PrimaryKey()]
    name: Annotated[str, ClusteringKey()]
    estimated_cost: Annotated[Optional[float], Double(), Static()] = None
    actual_cost: Annotated[Optional[float], Double(), Static()] = None
    cost: Annotated[Optional[float], Double()] = None
    category: Optional[str] = None
    pricing_tier: Optional[str] = None
    leaked: bool = False

    class Settings:
        name = "run_cost_v1"
