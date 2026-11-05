import json
import time
from dataclasses import dataclass, field
from unittest.mock import patch

import pytest
from mcp.server.mcpserver import MCPServer
from starlette.testclient import TestClient

from argus.backend.service.chat.mcp import McpTool, SdkMcpClient, chat_tool_name
from argus.backend.tests.chat.helpers import seed_entity_release, text_turn, tool_turn

API = "/admin/api/v1/chat"
STATUS_SCHEMA = {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]}


async def test_the_sdk_client_lists_and_calls_an_in_process_server():
    server = MCPServer("issues")

    @server.tool()
    def add(a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    @server.tool()
    def broken() -> str:
        """Always fails."""
        raise ValueError("no such issue")

    client = SdkMcpClient("", "streamable_http", {}, target=server)

    tools = {tool.name: tool for tool in await client.list_tools()}
    added = await client.call_tool("add", {"a": 1, "b": 2})
    failed = await client.call_tool("broken", {})

    assert tools["add"].description == "Add two numbers."
    assert set(tools["add"].input_schema["properties"]) == {"a", "b"}
    assert added == ("3", False)
    assert failed == ("Error executing tool broken", True)


def test_chat_tool_names_fit_the_model_api():
    taken = {"mcp_jira__read_status"}

    assert chat_tool_name("jira", "read.status", set()) == "mcp_jira__read_status"
    assert chat_tool_name("jira", "read_status", taken) == "mcp_jira__read_status_2"
    assert len(chat_tool_name("server", "x" * 100, set())) == 64


@dataclass
class FakeMcp:
    tools: list[McpTool] = field(default_factory=lambda: [
        McpTool("read_status", "Read an issue's status.", STATUS_SCHEMA),
        McpTool("close_issue", "Close an issue.", STATUS_SCHEMA),
    ])
    calls: list[tuple[str, dict]] = field(default_factory=list)
    reply: tuple[str, bool] = ("open", False)
    created: list[tuple[str, str, dict]] = field(default_factory=list)

    async def list_tools(self) -> list[McpTool]:
        return self.tools

    async def call_tool(self, name: str, arguments: dict) -> tuple[str, bool]:
        self.calls.append((name, arguments))
        return self.reply


@pytest.fixture
def fake_mcp():
    fake = FakeMcp()

    def make(url: str, transport: str, headers: dict[str, str]) -> FakeMcp:
        fake.created.append((url, transport, headers))
        return fake

    with patch("argus.backend.service.chat.mcp.make_mcp_client", side_effect=make):
        yield fake


def ok(response):
    body = response.json()
    assert body["status"] == "ok", body
    return body["response"]


def register(client: TestClient, modes: dict[str, str], enabled: bool = True) -> dict:
    ok(client.post(f"{API}/mcp/server", json={"name": "jira", "url": "https://mcp.test/mcp",
                                              "headers": {"Authorization": "Bearer secret-token"},
                                              "enabled": enabled}))
    ok(client.post(f"{API}/mcp/server/jira/probe"))
    return ok(client.post(f"{API}/mcp/server/jira/tools", json={"modes": modes}))


@pytest.mark.docker_required
@pytest.mark.usefixtures("chat_model")
def test_a_probe_keeps_the_modes_and_hides_the_headers(chat_client: TestClient, fake_mcp):
    server = register(chat_client, {"read_status": "direct"})
    fake_mcp.tools = [fake_mcp.tools[0], McpTool("reopen", "Reopen an issue.", STATUS_SCHEMA)]

    probed = ok(chat_client.post(f"{API}/mcp/server/jira/probe"))
    listed = chat_client.get(f"{API}/mcp")

    assert {tool["name"]: tool["mode"] for tool in server["tools"]} == {"read_status": "direct", "close_issue": "off"}
    assert {tool["name"]: tool["mode"] for tool in probed["tools"]} == {"read_status": "direct", "reopen": "off"}
    assert ok(listed)[0]["headers"] == ["Authorization"] and "secret-token" not in listed.text
    assert fake_mcp.created[0] == ("https://mcp.test/mcp", "streamable_http",
                                   {"Authorization": "Bearer secret-token"})
    assert chat_client.post(f"{API}/mcp/server/jira/tools", json={"modes": {"gone": "direct"}}).json()["status"] == \
        "error"


def wait_idle(client: TestClient, base: str) -> dict:
    deadline = time.monotonic() + 10
    while (conversation := ok(client.get(base)))["busy"] is not None and time.monotonic() < deadline:
        time.sleep(0.05)
    return conversation


@pytest.fixture
async def base(release_manager_service) -> str:
    seeded = await seed_entity_release(release_manager_service)
    return f"/api/v1/chat/release/{seeded.release.id}"


@pytest.mark.docker_required
async def test_a_direct_tool_answers_inside_the_turn(chat_client: TestClient, chat_model, fake_mcp, base):
    register(chat_client, {"read_status": "direct"})
    fake_mcp.reply = ("issue not found", True)
    chat_model.turns = [tool_turn(("mcp_jira__read_status", {"key": "SCYLLA-1"})), text_turn("It is missing")]

    ok(chat_client.post(f"{base}/messages", json={"content": "status of SCYLLA-1?"}))
    conversation = wait_idle(chat_client, base)

    tool_node = next(node for node in conversation["nodes"] if node["role"] == "tool")
    offered = [tool.name for tool in chat_model.requests[0].tools]
    assert "mcp_jira__read_status" in offered and "mcp_jira__close_issue" not in offered
    assert fake_mcp.calls == [("read_status", {"key": "SCYLLA-1"})]
    assert tool_node["content"] == "issue not found" and tool_node["status"] == "error"


@pytest.mark.docker_required
async def test_a_confirm_tool_runs_once_from_its_card(chat_client: TestClient, chat_model, fake_mcp, base):
    register(chat_client, {"close_issue": "confirm"})
    fake_mcp.reply = ("closed", False)
    chat_model.turns = [tool_turn(("mcp_jira__close_issue", {"key": "SCYLLA-1"})), text_turn("Confirm the card")]

    ok(chat_client.post(f"{base}/messages", json={"content": "close SCYLLA-1"}))
    conversation = wait_idle(chat_client, base)
    card = next(node for node in conversation["nodes"] if node["role"] == "action")
    proposed_calls = list(fake_mcp.calls)
    ok(chat_client.post(f"{base}/actions/{card['node']}/confirm"))
    second = chat_client.post(f"{base}/actions/{card['node']}/confirm").json()
    deadline = time.monotonic() + 10
    while (done := next(node for node in ok(chat_client.get(base))["nodes"] if node["node"] == card["node"])
           )["action"]["state"] != "done" and time.monotonic() < deadline:
        time.sleep(0.05)

    assert card["action"]["kind"] == "mcp_call"
    assert card["action"]["proposal"] == {"server": "jira", "tool": "close_issue", "arguments": {"key": "SCYLLA-1"}}
    assert proposed_calls == []
    assert second["status"] == "error"
    assert fake_mcp.calls == [("close_issue", {"key": "SCYLLA-1"})]
    assert done["action"]["results"][0]["text"] == "closed"


@pytest.mark.docker_required
async def test_a_disabled_server_offers_no_tools(chat_client: TestClient, chat_model, fake_mcp, base):
    register(chat_client, {"read_status": "direct"}, enabled=False)
    chat_model.turns = [text_turn("hi")]

    ok(chat_client.post(f"{base}/messages", json={"content": "hello"}))
    wait_idle(chat_client, base)

    assert not any(tool.name.startswith("mcp_") for tool in chat_model.requests[0].tools)
    assert json.loads(json.dumps(fake_mcp.calls)) == []


@pytest.mark.docker_required
@pytest.mark.usefixtures("chat_model")
def test_a_new_url_needs_the_headers_again(chat_client: TestClient, fake_mcp):
    register(chat_client, {})

    moved = chat_client.post(f"{API}/mcp/server", json={"name": "jira", "url": "https://elsewhere.test/mcp"})
    toggled = chat_client.post(f"{API}/mcp/server", json={"name": "jira", "url": "https://mcp.test/mcp",
                                                         "enabled": False})

    assert moved.json()["status"] == "error"
    assert ok(toggled)["headers"] == ["Authorization"]
