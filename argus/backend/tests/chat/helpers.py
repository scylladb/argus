import asyncio
import json
from dataclasses import dataclass, field

from argus.backend.models.web import ArgusTest, ArgusUserView, User
from argus.backend.service.chat.llm import (
    ChatMessage,
    Finished,
    ProbedModel,
    StreamEvent,
    TextDelta,
    ToolCall,
    ToolCallsReady,
    ToolSpec,
    Usage,
)
from argus.backend.service.release_manager import ReleaseManagerService
from argus.backend.service.views import UserViewService
from argus.backend.tests.release_summary.helpers import Seeded, seed_release, unique
from argus.backend.util.config import Config


@dataclass
class ModelRequest:
    model: str
    messages: list[ChatMessage]
    tools: list[ToolSpec] | None


@dataclass
class ScriptedClient:
    """Plays back one list of stream events per model call. An exception in a
    turn is raised at that point of the stream; an ``asyncio.Event`` pauses the
    stream until it is set."""
    turns: list[list[StreamEvent | Exception]] = field(default_factory=list)
    models: list[ProbedModel] = field(default_factory=list)
    requests: list[ModelRequest] = field(default_factory=list)
    credentials: list[tuple[str, str]] = field(default_factory=list)

    async def stream(self, model: str, messages: list[ChatMessage], tools: list[ToolSpec] | None):
        self.requests.append(ModelRequest(model, list(messages), tools))
        turn = self.turns.pop(0) if self.turns else []
        for event in turn:
            if isinstance(event, Exception):
                raise event
            if isinstance(event, asyncio.Event):
                await event.wait()
                continue
            yield event

    async def list_models(self) -> list[ProbedModel]:
        return self.models


def yaml_connections(monkeypatch, *entries: dict) -> None:
    monkeypatch.setitem(Config.CONFIG, "CHAT_MODELS", list(entries))


async def seed_entity_release(release_manager_service: ReleaseManagerService) -> Seeded:
    return await seed_release(release_manager_service, test_count=2)


async def seed_view(user: User, tests: list[ArgusTest]) -> ArgusUserView:
    name = unique("chat_view")
    return await UserViewService().create_view(name, [f"test:{test.id}" for test in tests], "[]", user,
                                               display_name=f"Chat view {name}")


def text_turn(*parts: str) -> list:
    return [*(TextDelta(part) for part in parts), Usage(120, 30), Finished("stop")]


def tool_turn(*calls: tuple[str, dict]) -> list:
    return [ToolCallsReady([ToolCall(f"call_{index}", name, json.dumps(arguments))
                            for index, (name, arguments) in enumerate(calls)]),
            Usage(100, 10), Finished("tool_calls")]
