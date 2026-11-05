from datetime import datetime
from typing import Annotated, Optional
from uuid import UUID

from coodie import ClusteringKey, PrimaryKey, Static
from coodie.aio import Document

GLOBAL_SCOPE = "global"


class ChatConfiguration(Document):
    scope: Annotated[str, PrimaryKey()] = GLOBAL_SCOPE
    name: Annotated[str, ClusteringKey()]
    endpoint: Optional[str] = None
    token_encrypted: Optional[str] = None
    updated_by: Optional[UUID] = None
    updated_at: Optional[datetime] = None
    default_connection: Annotated[Optional[str], Static()] = None
    default_model: Annotated[Optional[str], Static()] = None
    default_context_window: Annotated[Optional[int], Static()] = None
    default_tools: Annotated[Optional[bool], Static()] = None
    default_vision: Annotated[Optional[bool], Static()] = None
    default_set_by: Annotated[Optional[UUID], Static()] = None
    default_set_at: Annotated[Optional[datetime], Static()] = None

    class Settings:
        name = "chat_configuration_v1"
