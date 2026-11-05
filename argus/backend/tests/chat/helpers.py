from dataclasses import dataclass, field

from argus.backend.service.chat.llm import ChatMessage, ProbedModel, StreamEvent, ToolSpec
from argus.backend.util.config import Config


@dataclass
class ModelRequest:
    model: str
    messages: list[ChatMessage]
    tools: list[ToolSpec] | None


@dataclass
class ScriptedClient:
    """Plays back one list of stream events per model call. An exception in a
    turn is raised at that point of the stream."""
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
            yield event

    async def list_models(self) -> list[ProbedModel]:
        return self.models


def yaml_connections(monkeypatch, *entries: dict) -> None:
    monkeypatch.setitem(Config.CONFIG, "CHAT_MODELS", list(entries))
