from typing import Annotated, Optional
from uuid import UUID

from coodie import ClusteringKey, PrimaryKey
from coodie.sync import Document


class RunConfiguration(Document):
    run_id: Annotated[Optional[UUID], PrimaryKey()] = None
    name: Annotated[Optional[str], ClusteringKey()] = None
    content: Optional[str] = None

    class Settings:
        name = "run_configuration"


class RunConfigParam(Document):
    name: Annotated[Optional[str], PrimaryKey(partition_key_index=0)] = None
    value: Annotated[Optional[str], PrimaryKey(partition_key_index=1)] = None
    run_id: Annotated[Optional[str], ClusteringKey()] = None

    class Settings:
        name = "run_config_param"
