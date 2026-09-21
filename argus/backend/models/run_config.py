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


NAME_BUCKET = "all"

# ``parse_config_values`` writes ``str(value) or "null"``: JSON null lands as "None".
EMPTY_PARAM_VALUES = frozenset({"", "null", "None"})


class RunConfigParamByRun(Document):
    run_id: Annotated[UUID, PrimaryKey()]
    name: Annotated[str, ClusteringKey()]
    value: Optional[str] = None

    class Settings:
        name = "run_config_param_by_run_v1"


class RunConfigParamValueIndex(Document):
    name: Annotated[str, PrimaryKey()]
    value: Annotated[str, ClusteringKey()]

    class Settings:
        name = "run_config_param_value_index_v1"


class RunConfigParamName(Document):
    bucket: Annotated[str, PrimaryKey()]
    name: Annotated[str, ClusteringKey()]

    class Settings:
        name = "run_config_param_name_v1"
