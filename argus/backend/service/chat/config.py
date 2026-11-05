import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import ClassVar
from uuid import UUID

from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from argus.backend.error_handlers import APIException
from argus.backend.models.chat import GLOBAL_SCOPE, ChatConfiguration
from argus.backend.models.web import User
from argus.backend.service.chat.llm import (
    ChatMessage,
    ChatModelClient,
    ChatModelError,
    OpenAIChatClient,
    ProbedModel,
    TextDelta,
    ToolCallsReady,
    ToolSpec,
)
from argus.backend.util.common import select_rows
from argus.backend.util.config import Config
from argus.backend.util.secrets import SecretUnreadableError, decrypt, encrypt

LOGGER = logging.getLogger(__name__)
DEFAULT_CONTEXT_WINDOW = 32768
CONNECTION_COLUMNS = ("name", "endpoint", "token_encrypted", "updated_by", "updated_at", "default_connection",
                      "default_model", "default_context_window", "default_tools", "default_vision",
                      "default_set_by", "default_set_at")
TOOL_TEST_SPEC = ToolSpec(name="get_time", description="Return the current time.",
                          parameters={"type": "object", "properties": {}})


class ChatConfigError(APIException):
    pass


class ChatNotConfiguredError(ChatConfigError):
    pass


class ConfiguredConnection(BaseModel):
    name: str = Field(min_length=1)
    endpoint: str = Field(min_length=1)
    token: str = ""
    model: str | None = None


@dataclass(slots=True, frozen=True)
class Connection:
    name: str
    endpoint: str
    source: str
    token_set: bool
    token_readable: bool
    updated_by: UUID | None = None
    updated_at: datetime | None = None


@dataclass(slots=True, frozen=True)
class DefaultModel:
    connection: str
    model: str
    context_window: int
    tools: bool
    vision: bool
    set_by: UUID | None = None
    set_at: datetime | None = None


@dataclass(slots=True, frozen=True)
class ResolvedModel:
    connection: str
    model: str
    context_window: int
    tools: bool
    vision: bool
    client: ChatModelClient


@dataclass(slots=True, frozen=True)
class ToolTestResult:
    tools: bool
    detail: str
    latency_ms: int


def make_client(endpoint: str, token: str) -> ChatModelClient:
    return OpenAIChatClient(endpoint, token)


def configured_connections() -> list[ConfiguredConnection]:
    raw = Config.load_yaml_config().get("CHAT_MODELS") or []
    try:
        return TypeAdapter(list[ConfiguredConnection]).validate_python(raw)
    except ValidationError as exception:
        raise ChatConfigError(f"CHAT_MODELS in argus_web.yaml is invalid: {exception}") from exception


def _readable(token_encrypted: str | None) -> bool:
    if not token_encrypted:
        return True
    try:
        decrypt(token_encrypted)
    except SecretUnreadableError:
        return False
    return True


class ChatConfigService:
    _fallback_probes: ClassVar[dict[tuple[str, str], ProbedModel | None]] = {}

    @staticmethod
    async def _rows() -> list[dict]:
        return await select_rows(ChatConfiguration.find(scope=GLOBAL_SCOPE), *CONNECTION_COLUMNS)

    @staticmethod
    def _default_from(rows: list[dict]) -> DefaultModel | None:
        if not rows or not rows[0]["default_connection"] or not rows[0]["default_model"]:
            return None
        row = rows[0]
        return DefaultModel(connection=row["default_connection"], model=row["default_model"],
                            context_window=row["default_context_window"] or DEFAULT_CONTEXT_WINDOW,
                            tools=bool(row["default_tools"]), vision=bool(row["default_vision"]),
                            set_by=row["default_set_by"], set_at=row["default_set_at"])

    async def connections(self) -> tuple[list[Connection], DefaultModel | None]:
        rows = await self._rows()
        connections = [Connection(name=entry.name, endpoint=entry.endpoint, source="config",
                                  token_set=bool(entry.token), token_readable=True)
                       for entry in configured_connections()]
        connections.extend(
            Connection(name=row["name"], endpoint=row["endpoint"], source="database",
                       token_set=bool(row["token_encrypted"]), token_readable=_readable(row["token_encrypted"]),
                       updated_by=row["updated_by"], updated_at=row["updated_at"])
            for row in rows if row["name"] is not None
        )
        return connections, self._default_from(rows)

    async def save_connection(self, name: str, endpoint: str, token: str | None, user: User) -> Connection:
        if any(entry.name == name for entry in configured_connections()):
            raise ChatConfigError(f"The connection {name} is defined in argus_web.yaml and cannot be edited here")
        if not endpoint.startswith(("http://", "https://")):
            raise ChatConfigError("The endpoint must be an http or https URL")
        fields = {"endpoint": endpoint.rstrip("/"), "updated_by": user.id, "updated_at": datetime.now(UTC)}
        if token:
            fields["token_encrypted"] = encrypt(token)
        await ChatConfiguration(name=name).update(**fields)
        connections, _ = await self.connections()
        return next(connection for connection in connections if connection.name == name)

    async def delete_connection(self, name: str) -> None:
        if any(entry.name == name for entry in configured_connections()):
            raise ChatConfigError(f"The connection {name} is defined in argus_web.yaml and cannot be deleted here")
        rows = await self._rows()
        if not any(row["name"] == name for row in rows):
            raise ChatConfigError(f"No connection named {name}")
        await ChatConfiguration(name=name).delete()
        if rows[0]["default_connection"] == name:
            await ChatConfiguration.find(scope=GLOBAL_SCOPE).update(
                default_connection=None, default_model=None, default_context_window=None, default_tools=None,
                default_vision=None, default_set_by=None, default_set_at=None)

    async def _credentials(self, name: str, rows: list[dict] | None = None) -> tuple[str, str]:
        for entry in configured_connections():
            if entry.name == name:
                return entry.endpoint, entry.token
        rows = rows if rows is not None else await self._rows()
        row = next((row for row in rows if row["name"] == name), None)
        if row is None:
            raise ChatConfigError(f"No connection named {name}")
        try:
            return row["endpoint"], decrypt(row["token_encrypted"]) if row["token_encrypted"] else ""
        except SecretUnreadableError as exception:
            raise ChatConfigError(f"The token of {name} cannot be read; enter it again") from exception

    async def client_for(self, name: str) -> ChatModelClient:
        return make_client(*await self._credentials(name))

    async def probe(self, name: str) -> list[ProbedModel]:
        client = await self.client_for(name)
        try:
            return await client.list_models()
        except ChatModelError as exception:
            raise ChatConfigError(str(exception)) from exception

    async def test_tools(self, name: str, model: str) -> ToolTestResult:
        client = await self.client_for(name)
        messages = [ChatMessage(role="system", content="Answer by calling the get_time tool."),
                    ChatMessage(role="user", content="What time is it?")]
        started = time.monotonic()
        text = []
        called = False
        try:
            async for event in client.stream(model, messages, [TOOL_TEST_SPEC]):
                if isinstance(event, ToolCallsReady):
                    called = called or any(call.name == TOOL_TEST_SPEC.name for call in event.calls)
                elif isinstance(event, TextDelta):
                    text.append(event.text)
        except ChatModelError as exception:
            return ToolTestResult(tools=False, detail=str(exception),
                                  latency_ms=int((time.monotonic() - started) * 1000))
        latency_ms = int((time.monotonic() - started) * 1000)
        if called:
            return ToolTestResult(tools=True, detail="The model called the get_time tool", latency_ms=latency_ms)
        answer = "".join(text).strip()[:160]
        return ToolTestResult(tools=False, detail=f"The model answered without calling the tool: {answer}",
                              latency_ms=latency_ms)

    async def set_default(self, choice: DefaultModel, user: User) -> DefaultModel:
        connections, _ = await self.connections()
        if not any(connection.name == choice.connection for connection in connections):
            raise ChatConfigError(f"No connection named {choice.connection}")
        if choice.context_window <= 0:
            raise ChatConfigError("The context window must be positive")
        now = datetime.now(UTC)
        await ChatConfiguration.find(scope=GLOBAL_SCOPE).update(
            default_connection=choice.connection, default_model=choice.model,
            default_context_window=choice.context_window, default_tools=choice.tools, default_vision=choice.vision,
            default_set_by=user.id, default_set_at=now)
        _, default = await self.connections()
        return default

    async def _fallback(self) -> DefaultModel | None:
        entry = next((entry for entry in configured_connections() if entry.model), None)
        if entry is None:
            return None
        key = (entry.name, entry.model)
        if key not in self._fallback_probes:
            try:
                models = await make_client(entry.endpoint, entry.token).list_models()
                self._fallback_probes[key] = next((model for model in models if model.id == entry.model), None)
            except ChatModelError:
                LOGGER.warning("Could not probe the models of %s", entry.name, exc_info=True)
                return DefaultModel(connection=entry.name, model=entry.model,
                                    context_window=DEFAULT_CONTEXT_WINDOW, tools=True, vision=False)
        probed = self._fallback_probes[key]
        return DefaultModel(connection=entry.name, model=entry.model,
                            context_window=(probed and probed.context_window) or DEFAULT_CONTEXT_WINDOW,
                            tools=probed.tools is not False if probed else True,
                            vision=bool(probed and probed.vision))

    async def resolve(self) -> ResolvedModel | None:
        rows = await self._rows()
        default = self._default_from(rows) or await self._fallback()
        if default is None:
            return None
        try:
            endpoint, token = await self._credentials(default.connection, rows)
        except ChatConfigError:
            LOGGER.warning("The default chat connection %s is not usable", default.connection, exc_info=True)
            return None
        return ResolvedModel(connection=default.connection, model=default.model,
                             context_window=default.context_window, tools=default.tools, vision=default.vision,
                             client=make_client(endpoint, token))
