from datetime import UTC, datetime
from typing import Annotated, Optional
from uuid import UUID, uuid1

from coodie import ClusteringKey, PrimaryKey, Static, TimeUUID
from coodie.aio import Document
from pydantic import Field

GLOBAL_SCOPE = "global"


def utc_now() -> datetime:
    return datetime.now(UTC)


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


class ChatIdentity(Document):
    scope: Annotated[str, PrimaryKey()] = GLOBAL_SCOPE
    connection: Annotated[str, ClusteringKey()]
    name: Optional[str] = None
    picture: Optional[bytes] = None
    picture_type: Optional[str] = None
    updated_by: Optional[UUID] = None
    updated_at: Optional[datetime] = None
    active: Annotated[Optional[str], Static()] = None

    class Settings:
        name = "chat_identity_v1"


class ChatState(Document):
    entity_id: Annotated[UUID, PrimaryKey()]
    entity_type: Optional[str] = None
    head: Annotated[Optional[UUID], TimeUUID()] = None
    busy: Annotated[Optional[UUID], TimeUUID()] = None
    busy_user: Optional[UUID] = None
    busy_since: Optional[datetime] = None
    stop_requested: Annotated[Optional[UUID], TimeUUID()] = None
    changed_at: Optional[datetime] = None
    memory_changed_at: Optional[datetime] = None

    class Settings:
        name = "chat_state_v1"


class ChatPresence(Document):
    entity_id: Annotated[UUID, PrimaryKey()]
    user_id: Annotated[UUID, ClusteringKey()]
    seen_at: datetime = Field(default_factory=utc_now)

    class Settings:
        name = "chat_presence_v1"


class ChatHistory(Document):
    entity_id: Annotated[UUID, PrimaryKey()]
    node: Annotated[UUID, TimeUUID(), ClusteringKey()] = Field(default_factory=uuid1)
    entity_type: str
    parent: Annotated[Optional[UUID], TimeUUID()] = None
    role: str
    content: str = ""
    reasoning: Optional[str] = None
    user_id: Optional[UUID] = None
    tool_calls: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_name: Optional[str] = None
    action: Optional[str] = None
    action_state: Optional[str] = None
    model_name: Optional[str] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    memory_snapshot: Optional[str] = None
    status: str = "done"
    error: Optional[str] = None
    hidden: bool = False
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    class Settings:
        name = "chat_history_v1"


class ChatMemory(Document):
    entity_id: Annotated[UUID, PrimaryKey()]
    id: Annotated[UUID, TimeUUID(), ClusteringKey()] = Field(default_factory=uuid1)
    entity_type: str
    kind: str = "note"
    content: str = ""
    created_by: UUID
    created_at: datetime = Field(default_factory=utc_now)
    updated_by: UUID
    updated_at: datetime = Field(default_factory=utc_now)
    deleted: bool = False
    revision: Annotated[Optional[UUID], TimeUUID()] = None
    source_node: Annotated[Optional[UUID], TimeUUID()] = None

    class Settings:
        name = "chat_memory_v1"


class ChatMemoryRevision(Document):
    entity_id: Annotated[UUID, PrimaryKey()]
    revision: Annotated[UUID, TimeUUID(), ClusteringKey(order="DESC")] = Field(default_factory=uuid1)
    memory_id: Annotated[UUID, TimeUUID()]
    action: str
    before: Optional[str] = None
    after: Optional[str] = None
    kind: str = "note"
    before_kind: Optional[str] = None
    user_id: UUID
    source: str = "manual"
    source_node: Annotated[Optional[UUID], TimeUUID()] = None
    reverts: Annotated[Optional[UUID], TimeUUID()] = None
    created_at: datetime = Field(default_factory=utc_now)

    class Settings:
        name = "chat_memory_revision_v1"


CHAT_MODELS = [ChatConfiguration, ChatIdentity, ChatState, ChatPresence, ChatHistory, ChatMemory, ChatMemoryRevision]
