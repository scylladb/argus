import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from argus.backend.models.chat import ChatHistory
from argus.backend.models.web import User
from argus.backend.service.chat.actions import claim, execute
from argus.backend.service.chat.config import ResolvedModel
from argus.backend.service.chat.conversation import node_json, state_event
from argus.backend.service.chat.entity import ChatEntity
from argus.backend.service.chat.history import ChatHistoryService, active_path
from argus.backend.service.chat.hub import ChatHub
from argus.backend.service.chat.identity import ChatIdentityService
from argus.backend.service.chat.llm import (
    ChatMessage,
    ChatModelError,
    ReasoningDelta,
    TextDelta,
    ToolCall,
    ToolCallsReady,
    ToolSpec,
    Usage,
)
from argus.backend.service.chat.memory import ChatMemoryService
from argus.backend.service.chat.prompt import (
    COMPACT_INSTRUCTION,
    build_system_prompt,
    compact_summary,
    node_user_ids,
    results_text,
    to_messages,
)
from argus.backend.service.chat.skills import PromptSetup, SkillService
from argus.backend.service.chat.tools import (
    ToolContext,
    Toolbox,
    entity_summaries,
    mcp_tools,
    run_tool,
    to_json,
    tool_specs,
)

LOGGER = logging.getLogger(__name__)
MAX_MODEL_CALLS = 8
FLUSH_SECONDS = 0.5
LIMIT_MESSAGE = (f"I stopped after {MAX_MODEL_CALLS} model calls, the limit for one question. "
                 "Ask again to continue from here.")


class StopRequested(Exception):
    pass


@dataclass(slots=True)
class Streamed:
    text: list[str] = field(default_factory=list)
    reasoning: list[str] = field(default_factory=list)
    calls: list[ToolCall] = field(default_factory=list)
    usage: Usage | None = None

    @property
    def content(self) -> str:
        return "".join(self.text)

    @property
    def thinking(self) -> str | None:
        return "".join(self.reasoning) or None


async def load_users(user_ids: set[UUID], known: User) -> dict[UUID, User]:
    users = {known.id: known}
    wanted = [user_id for user_id in user_ids if user_id and user_id not in users]
    if wanted:
        users.update({user.id: user for user in await User.find(id__in=wanted).all()})
    return users


class ChatAgent:
    def __init__(self, entity: ChatEntity, user: User, model: ResolvedModel, hub: ChatHub) -> None:
        self.entity = entity
        self.user = user
        self.model = model
        self.hub = hub
        self.history = ChatHistoryService(entity)
        self.box = Toolbox()
        self.auto = False

    def _publish(self, event: dict) -> None:
        self.hub.publish(self.entity.id, event)

    def _publish_node(self, node: ChatHistory) -> None:
        self._publish({"type": "node", "node": node_json(node)})

    async def _publish_state(self) -> None:
        state, nodes = await self.history.read()
        self._publish(state_event(state, nodes, self.model))

    async def _append(self, head: UUID, **fields) -> ChatHistory:
        node = await self.history.append(**fields)
        await self.history.move_head(head, node.node)
        self._publish_node(node)
        return node

    async def _stop_requested(self) -> bool:
        state = await self.history.state()
        return state.stop_requested is not None and state.stop_requested == self.busy_node

    async def _finish(self, node: ChatHistory, status: str, streamed: Streamed | None = None,
                      error: str | None = None) -> None:
        if status == "done" and await self._stop_requested():
            status = "stopped"
        fields = {"status": status, "error": error}
        if streamed is not None:
            fields.update(content=streamed.content, reasoning=streamed.thinking)
            if streamed.usage:
                fields.update(prompt_tokens=streamed.usage.prompt_tokens,
                              completion_tokens=streamed.usage.completion_tokens)
        await self.history.flush(node, **fields)
        self._publish_node(node)

    async def _stream(self, node: ChatHistory, messages: list[ChatMessage], tools: list[ToolSpec] | None,
                      streamed: Streamed) -> None:
        flushed_at = time.monotonic()
        async for event in self.model.client.stream(self.model.model, messages, tools):
            match event:
                case TextDelta(text=text):
                    streamed.text.append(text)
                    self._publish({"type": "delta", "node": node.node, "content": text, "reasoning": ""})
                case ReasoningDelta(text=text):
                    streamed.reasoning.append(text)
                    self._publish({"type": "delta", "node": node.node, "content": "", "reasoning": text})
                case ToolCallsReady(calls=calls):
                    streamed.calls = calls
                case Usage():
                    streamed.usage = event
            if time.monotonic() - flushed_at >= FLUSH_SECONDS:
                flushed_at = time.monotonic()
                await self.history.flush(node, content=streamed.content, reasoning=streamed.thinking)
                self._publish_node(node)
                if await self._stop_requested():
                    raise StopRequested

    @staticmethod
    async def _mcp_tools() -> tuple:
        try:
            return await mcp_tools()
        except Exception:  # noqa: BLE001 - an answer without MCP tools beats no answer
            LOGGER.exception("The MCP tools are unavailable for the chat")
            return ()

    async def _context(self, path: list[ChatHistory],
                       setup: PromptSetup | None = None) -> tuple[str, list[ChatMessage], list[dict]]:
        setup = setup or await SkillService().prompt_setup()
        memories = await ChatMemoryService().list(self.entity)
        users = await load_users(node_user_ids(path) | {memory["updated_by"] for memory in memories}, self.user)
        try:
            summary = compact_summary(await entity_summaries(self.entity))
        except Exception:  # noqa: BLE001 - an answer without numbers beats no answer
            LOGGER.exception("The summary of %s is unavailable for the chat", self.entity.id)
            summary = "The release summary is unavailable right now."
        identity = await ChatIdentityService().active()
        system = build_system_prompt(self.entity, memories, summary, users, datetime.now(UTC), self.model.tools,
                                     assistant_name=identity.name if identity else None, template=setup.template,
                                     skills=setup.skills_text(), auto=self.auto)
        messages = to_messages(path, users)
        if messages and messages[0].role == "system":
            system = f"{system}\n\n{messages.pop(0).content}"
        snapshot = [{"memory_id": memory["id"], "revision": memory["revision"]} for memory in memories]
        return system, messages, snapshot

    async def answer(self, assistant: ChatHistory, compact_first: ChatHistory | None = None) -> None:
        self.busy_node = assistant.node
        self.auto = bool(assistant.auto)
        current = assistant

        async def work(streamed: Streamed) -> None:
            nonlocal current
            if compact_first is not None:
                await self._compact_first(compact_first)
            _, nodes = await self.history.read()
            setup = await SkillService().prompt_setup()
            self.box = Toolbox(hidden=frozenset() if setup.on_demand else frozenset({"load_skill"}),
                               external=await self._mcp_tools() if self.model.tools else ())
            system, messages, snapshot = await self._context(active_path(nodes, assistant.parent), setup)
            messages.insert(0, ChatMessage("system", system))
            tools = tool_specs(self.box) if self.model.tools else None
            snapshot_json = to_json(snapshot)
            await self.history.flush(current, memory_snapshot=snapshot_json)
            for call_number in range(1, MAX_MODEL_CALLS + 1):
                await self._stream(current, messages, tools, streamed)
                if not streamed.calls:
                    await self._finish(current, "done", streamed)
                    return
                calls = streamed.calls
                await self.history.flush(current, tool_calls=to_json([
                    {"id": call.id, "name": call.name, "arguments": call.arguments} for call in calls]))
                await self._finish(current, "done", streamed)
                messages.append(ChatMessage("assistant", streamed.content, tool_calls=calls))
                head = current.node
                for call in calls:
                    head = await self._run_call(current, call, head, messages)
                fields = {"role": "assistant", "parent": head, "user_id": self.user.id,
                          "model_name": self.model.model, "memory_snapshot": snapshot_json}
                if call_number == MAX_MODEL_CALLS:
                    current = await self._append(head, content=LIMIT_MESSAGE, status="done", **fields)
                    return
                current = await self._append(head, status="streaming", **fields)
                streamed.text, streamed.reasoning, streamed.calls, streamed.usage = [], [], [], None

        await self._guard(lambda: current, work)

    async def _guard(self, current, work) -> None:
        streamed = Streamed()
        try:
            await work(streamed)
        except StopRequested:
            await self._finish(current(), "stopped", streamed)
        except asyncio.CancelledError:
            await self._finish(current(), "stopped", streamed, error="The server stopped while answering")
            raise
        except ChatModelError as exception:
            await self._finish(current(), "error", streamed, error=str(exception))
        except Exception as exception:  # noqa: BLE001 - the user sees the failure on the answer
            LOGGER.exception("The chat answer of %s failed", self.entity.id)
            await self._finish(current(), "error", streamed, error=f"{exception.__class__.__name__}: {exception}")
        finally:
            await self.history.release(self.busy_node)
            await self._publish_state()

    async def _run_call(self, caller: ChatHistory, call: ToolCall, head: UUID,
                        messages: list[ChatMessage]) -> UUID:
        self._publish({"type": "tool", "node": caller.node, "name": call.name, "state": "running"})
        outcome = await run_tool(ToolContext(self.entity, self.user, caller.node), call, self.box)
        tool_node = await self._append(head, role="tool", parent=head, content=outcome.content,
                                       tool_call_id=call.id, tool_name=call.name, user_id=self.user.id,
                                       status="error" if outcome.error else "done")
        self._publish({"type": "tool", "node": caller.node, "name": call.name,
                       "state": "error" if outcome.error else "done"})
        messages.append(ChatMessage("tool", outcome.content, tool_call_id=call.id))
        if outcome.action is None:
            return tool_node.node
        action = await self._append(tool_node.node, role="action", parent=tool_node.node, user_id=self.user.id,
                                    action=to_json(outcome.action), action_state=outcome.card_state)
        if self.auto and outcome.card_state == "pending":
            note = await self._confirm_automatically(action)
            messages[-1] = ChatMessage("tool", note, tool_call_id=call.id)
            await self.history.flush(tool_node, content=note)
        return action.node

    async def _confirm_automatically(self, card: ChatHistory) -> str:
        """Auto mode: confirm the card as the asker and run it inside the answer; the outcome is the tool
        result the model sees."""
        card, action = await claim(self.entity, card.node, self.user, "running", auto=True)
        self._publish_node(card)
        action = await execute(self.entity, card, action, self.user)
        self._publish_node(card)
        return to_json({"status": "confirmed automatically (Auto mode) and done", "kind": action["kind"],
                        "outcome": results_text(action["kind"], action["results"])})

    async def _summarize(self, summary: ChatHistory, streamed: Streamed) -> None:
        _, nodes = await self.history.read()
        path = active_path(nodes, summary.parent)
        users = await load_users(node_user_ids(path), self.user)
        messages = to_messages(path, users)
        instruction = COMPACT_INSTRUCTION
        if messages and messages[0].role == "system":
            instruction = f"{instruction}\n\n{messages.pop(0).content}"
        messages = [ChatMessage("system", instruction), *messages,
                    ChatMessage("user", "Summarize the conversation so far.")]
        await self._stream(summary, messages, None, streamed)
        await self._finish(summary, "done", streamed)

    async def compact(self, summary: ChatHistory) -> None:
        self.busy_node = summary.node
        await self._guard(lambda: summary, lambda streamed: self._summarize(summary, streamed))

    async def _compact_first(self, summary: ChatHistory) -> None:
        """The automatic compaction before an answer: a failure is recorded on the summary, which the prompt then
        ignores, and the answer goes ahead."""
        streamed = Streamed()
        try:
            await self._summarize(summary, streamed)
        except (StopRequested, asyncio.CancelledError):
            await self._finish(summary, "stopped", streamed)
            raise
        except Exception as exception:  # noqa: BLE001 - the answer still runs on the uncompacted conversation
            LOGGER.warning("The automatic compaction of %s failed", self.entity.id, exc_info=True)
            await self._finish(summary, "error", streamed, error=f"{exception.__class__.__name__}: {exception}")
