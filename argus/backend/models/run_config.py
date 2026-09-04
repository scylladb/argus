from typing import Annotated, Optional
from uuid import UUID

from coodie import ClusteringKey, PrimaryKey
from coodie.sync import Document


class RunConfiguration(Document):
    run_id: Annotated[UUID, PrimaryKey()]
    name: Annotated[str, ClusteringKey()]
    content: Optional[str] = None

    class Settings:
        name = "run_configuration"


class RunConfigParam(Document):
    name: Annotated[str, PrimaryKey(partition_key_index=0)]
    value: Annotated[str, PrimaryKey(partition_key_index=1)]
    run_id: Annotated[str, ClusteringKey()]

    class Settings:
        name = "run_config_param"
