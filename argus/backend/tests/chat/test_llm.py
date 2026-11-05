import json

import httpx2
import pytest

from argus.backend.service.chat.llm import (
    ChatMessage,
    ChatModelError,
    Finished,
    OpenAIChatClient,
    ReasoningDelta,
    TextDelta,
    ToolCall,
    ToolCallsReady,
    ToolSpec,
    Usage,
    normalize_model,
)


def chunk(delta: dict | None = None, finish: str | None = None, usage: dict | None = None) -> str:
    body = {"id": "c1", "object": "chat.completion.chunk", "created": 1, "model": "m",
            "choices": [] if delta is None else [{"index": 0, "delta": delta, "finish_reason": finish}]}
    if usage:
        body["usage"] = usage
    return f"data: {json.dumps(body)}\n\n"


def client_for(handler) -> OpenAIChatClient:
    return OpenAIChatClient("http://model.test/api", "sk-test",
                            http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)))


def test_the_lemonade_shape_reads_context_and_labels():
    model = normalize_model({"id": "Gemma-4-12B-it-GGUF", "name": "Gemma-4-12B-it-GGUF", "context_length": 65536,
                             "max_context_window": 262144, "labels": ["chat", "tool-calling", "vision"]})

    assert (model.context_window, model.tools, model.vision) == (65536, True, True)


def test_labels_without_tool_calling_mean_no_tools():
    model = normalize_model({"id": "Gemma-3-4b-it-GGUF", "context_length": 65536, "labels": ["chat", "vision"]})

    assert (model.tools, model.vision) == (False, True)


def test_a_plain_openai_entry_leaves_everything_unknown():
    model = normalize_model({"id": "gpt-x", "object": "model", "owned_by": "openai"})

    assert (model.name, model.context_window, model.tools, model.vision) == ("gpt-x", None, None, None)


def test_vllm_max_model_len_is_the_context_window():
    assert normalize_model({"id": "qwen", "max_model_len": 32768}).context_window == 32768


def test_openwebui_capabilities_give_vision():
    model = normalize_model({"id": "g", "info": {"meta": {"capabilities": {"vision": True}}}})

    assert (model.tools, model.vision) == (None, True)


async def test_the_stream_yields_text_reasoning_tool_calls_and_usage():
    seen = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["body"] = json.loads(request.content)
        seen["auth"] = request.headers["authorization"]
        body = "".join([
            chunk({"role": "assistant"}),
            chunk({"reasoning_content": "Think"}),
            chunk({"content": "Look"}),
            chunk({"tool_calls": [{"index": 0, "id": "call_a", "type": "function",
                                   "function": {"name": "read_run", "arguments": "{\"run"}}]}),
            chunk({"tool_calls": [{"index": 0, "function": {"arguments": "_id\": \"42\"}"}}]}),
            chunk({}, finish="tool_calls"),
            chunk(usage={"prompt_tokens": 70, "completion_tokens": 7, "total_tokens": 77}),
            "data: [DONE]\n\n",
        ])
        return httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=body.encode())

    tools = [ToolSpec("read_run", "Read a run", {"type": "object", "properties": {"run_id": {"type": "string"}}})]
    history = [ChatMessage("user", "status?"),
               ChatMessage("assistant", "", tool_calls=[ToolCall("call_0", "get_summary", "{}")]),
               ChatMessage("tool", "{\"ok\": true}", tool_call_id="call_0")]

    events = [event async for event in client_for(handler).stream("m", history, tools)]

    assert events == [
        ReasoningDelta("Think"),
        TextDelta("Look"),
        Usage(70, 7),
        ToolCallsReady([ToolCall("call_a", "read_run", "{\"run_id\": \"42\"}")]),
        Finished("tool_calls"),
    ]
    assert seen["auth"] == "Bearer sk-test"
    assert seen["body"]["stream_options"] == {"include_usage": True}
    assert seen["body"]["tools"][0]["function"]["name"] == "read_run"
    assert seen["body"]["messages"][1] == {"role": "assistant", "content": None, "tool_calls": [
        {"id": "call_0", "type": "function", "function": {"name": "get_summary", "arguments": "{}"}}]}
    assert seen["body"]["messages"][2] == {"role": "tool", "tool_call_id": "call_0", "content": "{\"ok\": true}"}


async def test_an_endpoint_error_is_a_chat_model_error():
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(401, json={"detail": "bad key"})

    with pytest.raises(ChatModelError):
        [event async for event in client_for(handler).stream("m", [ChatMessage("user", "hi")], None)]


async def test_list_models_keeps_the_extra_fields():
    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.url.path == "/api/models"
        return httpx2.Response(200, json={"object": "list", "data": [
            {"id": "b", "object": "model", "created": 1, "owned_by": "x", "context_length": 4096,
             "labels": ["tool-calling"]},
            {"id": "a", "object": "model", "created": 1, "owned_by": "x"},
        ]})

    models = await client_for(handler).list_models()

    assert [(model.id, model.context_window, model.tools) for model in models] == [("a", None, None),
                                                                                    ("b", 4096, True)]
