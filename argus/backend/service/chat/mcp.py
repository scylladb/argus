"""MCP servers an administrator registers: their stored tool lists, the mode of each tool, and the client that
lists and calls them."""
import asyncio
import json
import re
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

import httpx2
from mcp import Client
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamable_http_client

from argus.backend.error_handlers import APIException
from argus.backend.models.chat import GLOBAL_SCOPE, ChatMcpServer
from argus.backend.models.web import User
from argus.backend.util.common import select_rows
from argus.backend.util.secrets import SecretUnreadableError, decrypt, encrypt

MCP_TIMEOUT_SECONDS = 30
TRANSPORTS = ("streamable_http", "sse")
MODES = ("off", "direct", "confirm")
NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
TOOL_NAME_LIMIT = 64
DESCRIPTION_LIMIT = 1024
SERVER_COLUMNS = ("name", "url", "transport", "headers_encrypted", "enabled", "catalog", "tool_modes", "probed_at",
                  "updated_by", "updated_at")


class ChatMcpError(APIException):
    pass


@dataclass(slots=True, frozen=True)
class McpTool:
    name: str
    description: str
    input_schema: dict


@dataclass(slots=True, frozen=True)
class McpServerInfo:
    name: str
    url: str
    transport: str
    enabled: bool
    headers: list[str]
    tools: list[dict] = field(default_factory=list)
    probed_at: datetime | None = None
    updated_by: UUID | None = None
    updated_at: datetime | None = None


@dataclass(slots=True, frozen=True)
class EnabledTool:
    server: str
    tool: McpTool
    mode: str


class McpClient(Protocol):
    async def list_tools(self) -> list[McpTool]: ...

    async def call_tool(self, name: str, arguments: dict) -> tuple[str, bool]: ...


def _message(exception: BaseException) -> str:
    while isinstance(exception, BaseExceptionGroup) and exception.exceptions:
        exception = exception.exceptions[0]
    return f"{exception.__class__.__name__}: {exception}"


def result_text(result: Any) -> str:
    parts = []
    for block in result.content or []:
        parts.append(block.text if getattr(block, "type", None) == "text" else f"[{getattr(block, 'type', 'content')}]")
    if not any(part.strip() for part in parts) and result.structured_content is not None:
        parts.append(json.dumps(result.structured_content, ensure_ascii=False, default=str))
    return "\n".join(parts)


class SdkMcpClient:
    """The MCP SDK's client, one session per call, over streamable HTTP or SSE. ``target`` replaces the
    transport, for an in-process server in tests."""

    def __init__(self, url: str, transport: str, headers: dict[str, str], target: Any = None) -> None:
        self.url = url
        self.transport = transport
        self.headers = headers
        self.target = target

    @asynccontextmanager
    async def _client(self):
        async with AsyncExitStack() as stack:
            if self.target is not None:
                target = self.target
            elif self.transport == "sse":
                target = sse_client(self.url, headers=self.headers, timeout=MCP_TIMEOUT_SECONDS)
            else:
                http = await stack.enter_async_context(httpx2.AsyncClient(headers=self.headers,
                                                                          timeout=MCP_TIMEOUT_SECONDS))
                target = streamable_http_client(self.url, http_client=http)
            yield await stack.enter_async_context(Client(target, read_timeout_seconds=MCP_TIMEOUT_SECONDS))

    async def list_tools(self) -> list[McpTool]:
        try:
            async with asyncio.timeout(MCP_TIMEOUT_SECONDS), self._client() as client:
                tools, cursor = [], None
                while True:
                    page = await client.list_tools(cursor=cursor)
                    tools.extend(page.tools)
                    if not (cursor := page.next_cursor):
                        break
        except Exception as exception:  # noqa: BLE001 - any transport or protocol failure is the server's
            raise ChatMcpError(f"The MCP server did not list its tools: {_message(exception)}") from exception
        return [McpTool(tool.name, (tool.description or "").strip(), tool.input_schema or {}) for tool in tools]

    async def call_tool(self, name: str, arguments: dict) -> tuple[str, bool]:
        try:
            async with asyncio.timeout(MCP_TIMEOUT_SECONDS), self._client() as client:
                result = await client.call_tool(name, arguments)
        except Exception as exception:  # noqa: BLE001 - the model gets the failure as the tool's result
            return f"The MCP server failed: {_message(exception)}", True
        return result_text(result), bool(result.is_error)


def make_mcp_client(url: str, transport: str, headers: dict[str, str]) -> McpClient:
    return SdkMcpClient(url, transport, headers)


def chat_tool_name(server: str, tool: str, taken: set[str]) -> str:
    """The name the model calls an MCP tool by: unique, and within OpenAI's ``^[a-zA-Z0-9_-]{1,64}$``."""
    base = re.sub(r"[^A-Za-z0-9_-]", "_", f"mcp_{server}__{tool}")[:TOOL_NAME_LIMIT]
    name, number = base, 2
    while name in taken:
        suffix = f"_{number}"
        name, number = base[:TOOL_NAME_LIMIT - len(suffix)] + suffix, number + 1
    return name


class McpServerService:
    @staticmethod
    async def _rows() -> list[dict]:
        rows = await select_rows(ChatMcpServer.find(scope=GLOBAL_SCOPE), *SERVER_COLUMNS)
        return [row for row in rows if row["name"] is not None]

    async def _row(self, name: str) -> dict:
        row = next((row for row in await self._rows() if row["name"] == name), None)
        if row is None:
            raise ChatMcpError(f"No MCP server named {name}")
        return row

    @staticmethod
    def _headers(row: dict) -> dict[str, str]:
        if not row["headers_encrypted"]:
            return {}
        try:
            return json.loads(decrypt(row["headers_encrypted"]))
        except SecretUnreadableError as exception:
            raise ChatMcpError(f"The headers of {row['name']} cannot be read; enter them again") from exception

    @staticmethod
    def _info(row: dict) -> McpServerInfo:
        modes = json.loads(row["tool_modes"] or "{}")
        try:
            headers = sorted(json.loads(decrypt(row["headers_encrypted"]))) if row["headers_encrypted"] else []
        except SecretUnreadableError:
            headers = ["(unreadable)"]
        tools = [{"name": tool["name"], "description": tool["description"], "mode": modes.get(tool["name"], "off")}
                 for tool in json.loads(row["catalog"] or "[]")]
        return McpServerInfo(name=row["name"], url=row["url"], transport=row["transport"] or "streamable_http",
                             enabled=bool(row["enabled"]), headers=headers, tools=tools, probed_at=row["probed_at"],
                             updated_by=row["updated_by"], updated_at=row["updated_at"])

    async def servers(self) -> list[McpServerInfo]:
        return [self._info(row) for row in await self._rows()]

    async def server(self, name: str) -> McpServerInfo:
        return self._info(await self._row(name))

    async def save(self, name: str, url: str, transport: str, headers: dict[str, str] | None, enabled: bool,
                   user: User) -> McpServerInfo:
        if not NAME_RE.match(name):
            raise ChatMcpError("A server name has 1 to 32 letters, digits, - or _")
        if not url.startswith(("http://", "https://")):
            raise ChatMcpError("The URL must be an http or https URL")
        if transport not in TRANSPORTS:
            raise ChatMcpError(f"The transport must be one of {', '.join(TRANSPORTS)}")
        fields = {"url": url.strip(), "transport": transport, "enabled": enabled, "updated_by": user.id,
                  "updated_at": datetime.now(UTC)}
        if headers is not None:
            cleaned = {key.strip(): value for key, value in headers.items() if key.strip()}
            fields["headers_encrypted"] = encrypt(json.dumps(cleaned)) if cleaned else None
        await ChatMcpServer(name=name).update(**fields)
        return await self.server(name)

    async def delete(self, name: str) -> None:
        await self._row(name)
        await ChatMcpServer(name=name).delete()

    def client_for(self, row: dict) -> McpClient:
        return make_mcp_client(row["url"], row["transport"] or "streamable_http", self._headers(row))

    async def probe(self, name: str) -> McpServerInfo:
        row = await self._row(name)
        tools = await self.client_for(row).list_tools()
        modes = json.loads(row["tool_modes"] or "{}")
        catalog = [{"name": tool.name, "description": tool.description[:DESCRIPTION_LIMIT],
                    "input_schema": tool.input_schema} for tool in tools]
        kept = {tool.name: modes.get(tool.name, "off") for tool in tools}
        await ChatMcpServer(name=name).update(catalog=json.dumps(catalog), tool_modes=json.dumps(kept),
                                              probed_at=datetime.now(UTC))
        return await self.server(name)

    async def set_modes(self, name: str, modes: dict[str, str]) -> McpServerInfo:
        row = await self._row(name)
        known = {tool["name"] for tool in json.loads(row["catalog"] or "[]")}
        if unknown := sorted(set(modes) - known):
            raise ChatMcpError(f"The server lists no tool {', '.join(unknown)}; probe it again")
        if wrong := sorted(mode for mode in modes.values() if mode not in MODES):
            raise ChatMcpError(f"A mode is one of {', '.join(MODES)}, not {', '.join(wrong)}")
        current = json.loads(row["tool_modes"] or "{}") | modes
        await ChatMcpServer(name=name).update(tool_modes=json.dumps(current))
        return await self.server(name)

    async def enabled_tools(self) -> list[EnabledTool]:
        result = []
        for row in await self._rows():
            if not row["enabled"]:
                continue
            modes = json.loads(row["tool_modes"] or "{}")
            for tool in json.loads(row["catalog"] or "[]"):
                if (mode := modes.get(tool["name"], "off")) != "off":
                    result.append(EnabledTool(row["name"], McpTool(tool["name"], tool["description"],
                                                                   tool["input_schema"]), mode))
        return result

    async def call(self, server: str, tool: str, arguments: dict) -> tuple[str, bool]:
        row = await self._row(server)
        if not row["enabled"]:
            return f"The MCP server {server} is disabled", True
        if json.loads(row["tool_modes"] or "{}").get(tool, "off") == "off":
            return f"The tool {tool} of {server} is switched off", True
        return await self.client_for(row).call_tool(tool, arguments)
