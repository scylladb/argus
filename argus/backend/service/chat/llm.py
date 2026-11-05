from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

import httpx2
import openai
from openai import AsyncOpenAI

MODEL_TIMEOUT_SECONDS = 300


class ChatModelError(Exception):
    pass


@dataclass(slots=True)
class ToolCall:
    id: str
    name: str
    arguments: str


@dataclass(slots=True)
class ChatMessage:
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None


@dataclass(slots=True, frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict


@dataclass(slots=True, frozen=True)
class TextDelta:
    text: str


@dataclass(slots=True, frozen=True)
class ReasoningDelta:
    text: str


@dataclass(slots=True, frozen=True)
class ToolCallsReady:
    calls: list[ToolCall]


@dataclass(slots=True, frozen=True)
class Usage:
    prompt_tokens: int
    completion_tokens: int


@dataclass(slots=True, frozen=True)
class Finished:
    reason: str


StreamEvent = TextDelta | ReasoningDelta | ToolCallsReady | Usage | Finished


@dataclass(slots=True, frozen=True)
class ProbedModel:
    id: str
    name: str
    context_window: int | None
    tools: bool | None
    vision: bool | None


class ChatModelClient(Protocol):
    def stream(self, model: str, messages: list[ChatMessage],
               tools: list[ToolSpec] | None) -> AsyncIterator[StreamEvent]: ...

    async def list_models(self) -> list[ProbedModel]: ...


def _positive_int(*values: Any) -> int | None:
    for value in values:
        if isinstance(value, bool):
            continue
        if isinstance(value, int) and value > 0:
            return value
        if isinstance(value, str) and value.isdigit() and int(value) > 0:
            return int(value)
    return None


def normalize_model(entry: dict) -> ProbedModel:
    meta = (entry.get("info") or {}).get("meta") or {}
    capabilities = meta.get("capabilities") or {}
    labels = {str(label).lower() for label in entry.get("labels") or []}
    if labels:
        tools = bool(labels & {"tool-calling", "tools"})
        vision = "vision" in labels
    else:
        tools = capabilities.get("function_calling", capabilities.get("tools"))
        vision = capabilities.get("vision")
    return ProbedModel(
        id=entry["id"],
        name=entry.get("name") or entry["id"],
        context_window=_positive_int(entry.get("context_length"), entry.get("max_model_len"),
                                     meta.get("context_length")),
        tools=tools if isinstance(tools, bool) else None,
        vision=vision if isinstance(vision, bool) else None,
    )


def _wire_message(message: ChatMessage) -> dict:
    if message.role == "tool":
        return {"role": "tool", "tool_call_id": message.tool_call_id, "content": message.content}
    if message.role == "assistant" and message.tool_calls:
        return {
            "role": "assistant",
            "content": message.content or None,
            "tool_calls": [{"id": call.id, "type": "function",
                            "function": {"name": call.name, "arguments": call.arguments}}
                           for call in message.tool_calls],
        }
    return {"role": message.role, "content": message.content}


def _wire_tool(tool: ToolSpec) -> dict:
    return {"type": "function",
            "function": {"name": tool.name, "description": tool.description, "parameters": tool.parameters}}


class OpenAIChatClient:
    def __init__(self, endpoint: str, token: str, http_client: httpx2.AsyncClient | None = None) -> None:
        self._client = AsyncOpenAI(base_url=endpoint, api_key=token or "none", timeout=MODEL_TIMEOUT_SECONDS,
                                   max_retries=1, http_client=http_client)

    async def stream(self, model: str, messages: list[ChatMessage],
                     tools: list[ToolSpec] | None) -> AsyncIterator[StreamEvent]:
        request: dict[str, Any] = {
            "model": model,
            "messages": [_wire_message(message) for message in messages],
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            request["tools"] = [_wire_tool(tool) for tool in tools]
        calls: dict[int, dict[str, str]] = {}
        finish = "stop"
        try:
            response = await self._client.chat.completions.create(**request)
            async for chunk in response:
                if chunk.usage:
                    yield Usage(chunk.usage.prompt_tokens or 0, chunk.usage.completion_tokens or 0)
                for choice in chunk.choices:
                    delta = choice.delta
                    if delta.content:
                        yield TextDelta(delta.content)
                    extra = delta.model_extra or {}
                    if reasoning := extra.get("reasoning_content") or extra.get("reasoning"):
                        yield ReasoningDelta(reasoning)
                    for call in delta.tool_calls or []:
                        entry = calls.setdefault(call.index, {"id": "", "name": "", "arguments": ""})
                        entry["id"] = call.id or entry["id"]
                        if call.function:
                            entry["name"] += call.function.name or ""
                            entry["arguments"] += call.function.arguments or ""
                    if choice.finish_reason:
                        finish = choice.finish_reason
        except openai.APIError as exception:
            raise ChatModelError(f"The model endpoint failed: {exception}") from exception
        if calls:
            yield ToolCallsReady([ToolCall(id=entry["id"] or f"call_{index}", name=entry["name"],
                                           arguments=entry["arguments"] or "{}")
                                  for index, entry in sorted(calls.items())])
        yield Finished(finish)

    async def list_models(self) -> list[ProbedModel]:
        try:
            page = await self._client.models.list()
        except openai.APIError as exception:
            raise ChatModelError(f"The model endpoint failed: {exception}") from exception
        return sorted((normalize_model(model.model_dump()) for model in page.data), key=lambda model: model.id)
